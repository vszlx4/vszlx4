"""
Turns raw data into the numbers the dashboard shows. Pure functions, no drawing.

Inputs (a data directory written by fetch.py; never committed, because it holds private repository names):
  commits.json            one record per authored commit: repo, date (ISO, with offset), subject, files [path, +, -]
  user.json, repos.json   GitHub REST profile and owned repositories
  runs_<repo>.json, rel_<repo>.json, iss_<repo>.json, root_<repo>.json   per public repository
"""
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

EXCLUDE = re.compile(r'(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|Cargo\.lock|uv\.lock)$'
                     r'|(^|/)meta/\d+_snapshot\.json$|\.min\.(js|css)$|\.map$')
LANG_BY_EXT = {
    'py': 'Python', 'svelte': 'Svelte', 'ts': 'TypeScript', 'tsx': 'TypeScript', 'js': 'JavaScript', 'mjs': 'JavaScript',
    'cjs': 'JavaScript', 'jsx': 'JavaScript', 'html': 'HTML', 'css': 'CSS', 'scss': 'CSS', 'astro': 'Astro', 'sh': 'Shell',
    'sql': 'SQL', 'c': 'C', 'h': 'C', 'cs': 'C#', 'go': 'Go', 'rs': 'Rust', 'java': 'Java', 'kt': 'Kotlin', 'lua': 'Lua',
}
TEST_PATH = re.compile(r'(^|/)(tests?|e2e|__tests__)/|(_test|\.test|\.spec)\.\w+$|(^|/)test_\w+\.py$')
SIZE_BUCKETS = [('1-10', 1, 10), ('11-50', 11, 50), ('51-200', 51, 200), ('201-1k', 201, 1000), ('1k-5k', 1001, 5000), ('5k+', 5001, None)]
AUTOMATED_RUN = ('Graph Update', 'pip in', 'npm in', 'github_actions in', 'Dependabot')
WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


def _load(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _lines(c):
    if not c['files'] and 'additions' in c:  # file list not fetched yet: totals only, no language split
        return c['additions'], c['deletions'], []
    files = [f for f in c['files'] if not EXCLUDE.search(f[0])]
    return sum(f[1] for f in files), sum(f[2] for f in files), files


def _month_key(d):
    return d.year * 12 + d.month - 1


def _months(first, last):
    out = []
    k = _month_key(first)
    while k <= _month_key(last):
        out.append((k // 12, k % 12 + 1))
        k += 1
    return out


def build(data_dir, now=None):
    user = _load(os.path.join(data_dir, 'user.json'), {})
    repos = [r for r in _load(os.path.join(data_dir, 'repos.json'), []) if not r.get('fork')]
    public = {r['name']: r for r in repos if not r.get('private')}
    commits = _load(os.path.join(data_dir, 'commits.json'), [])
    for c in commits:
        c['dt'] = datetime.fromisoformat(c['date'])
        c['add'], c['del'], c['code'] = _lines(c)
    commits.sort(key=lambda c: c['dt'])
    tz = commits[-1]['dt'].tzinfo if commits else None
    now = now or datetime.now(tz)
    first = commits[0]['dt'] if commits else now

    m = {'now': now, 'first': first}
    # ---- profile
    m['profile'] = dict(name=user.get('name') or user.get('login'), login=user.get('login'),
                        bio=(user.get('bio') or '').splitlines()[0].strip().rstrip('.'), location=user.get('location'),
                        site=user.get('blog'), joined=datetime.fromisoformat(user['created_at'].replace('Z', '+00:00')) if user.get('created_at') else None)
    offsets = Counter(c['dt'].strftime('%z') for c in commits)
    off = offsets.most_common(1)[0][0] if offsets else '+0000'
    m['tz_label'] = 'UTC{}{}'.format(off[0], int(off[1:3])) + (':' + off[3:] if off[3:] != '00' else '')

    # ---- totals
    days = {c['dt'].date() for c in commits}
    repo_names = sorted({c['repo'] for c in commits})
    sizes = sorted(c['add'] + c['del'] for c in commits)
    m['totals'] = dict(
        commits=len(commits), added=sum(c['add'] for c in commits), removed=sum(c['del'] for c in commits),
        active_days=len(days), span_days=(now.date() - first.date()).days + 1,
        median_size=sizes[len(sizes) // 2] if sizes else 0, p90_size=sizes[int(len(sizes) * 0.9)] if sizes else 0,
        repos=len(repo_names), public_repos=sum(1 for r in repo_names if r in public),
        test_lines=sum(f[1] + f[2] for c in commits for f in c['code'] if TEST_PATH.search(f[0])),
    )
    t = m['totals']
    t['private_repos'] = t['repos'] - t['public_repos']
    t['changed'] = t['added'] + t['removed']

    # ---- per period (months, or quarters past 18 months)
    months = _months(first, now)
    per = defaultdict(lambda: dict(commits=0, added=0, removed=0, langs=Counter(), days=set(), repos=Counter()))
    for c in commits:
        p = per[(c['dt'].year, c['dt'].month)]
        p['commits'] += 1
        p['days'].add(c['dt'].date())
        p['repos'][c['repo']] += 1
        p['added'] += c['add']
        p['removed'] += c['del']
        for f, a, _ in c['code']:
            ext = f.rsplit('.', 1)[-1].lower() if '.' in f.rsplit('/', 1)[-1] else ''
            if ext in LANG_BY_EXT:
                p['langs'][LANG_BY_EXT[ext]] += a
    m['periods'] = [dict(key=k, label=datetime(k[0], k[1], 1).strftime('%b'), year=k[0], **per[k]) for k in months]
    for p in m['periods']:
        p['days'] = len(p['days'])

    # ---- languages (lines added in source files)
    lang_total = Counter()
    for p in m['periods']:
        lang_total.update(p['langs'])
    top = [l for l, _ in lang_total.most_common(5)]
    m['languages'] = dict(order=top + (['Other'] if len(lang_total) > len(top) else []), totals=lang_total, top=top)

    # ---- comparison windows
    def window(a, b):
        cs = [c for c in commits if a <= c['dt'] < b]
        return dict(commits=len(cs), changed=sum(c['add'] + c['del'] for c in cs), days=len({c['dt'].date() for c in cs}),
                    repos=Counter(c['repo'] for c in cs))
    w1 = window(now - timedelta(days=30), now + timedelta(seconds=1))
    w0 = window(now - timedelta(days=60), now - timedelta(days=30))
    span_windows = max(1, t['span_days'] / 30)
    m['momentum'] = dict(last=w1, prev=w0, avg=dict(commits=t['commits'] / span_windows, changed=t['changed'] / span_windows,
                                                     days=t['active_days'] / span_windows))
    focus = Counter()
    for r, n in w1['repos'].items():
        focus[r if r in public else 'Private repositories'] += n
    m['focus'] = focus.most_common()

    # ---- distributions
    m['hours'] = [0] * 24
    m['weekdays'] = [0] * 7
    m['heat'] = [[0] * 24 for _ in range(7)]
    for c in commits:
        m['hours'][c['dt'].hour] += 1
        m['weekdays'][c['dt'].weekday()] += 1
        m['heat'][c['dt'].weekday()][c['dt'].hour] += 1
    # weekly series (Monday-start weeks) from the first commit's week to the current week
    wk0 = (first - timedelta(days=first.weekday())).date()
    n_weeks = (now.date() - wk0).days // 7 + 1
    weekly = [0] * n_weeks
    for c in commits:
        weekly[(c['dt'].date() - wk0).days // 7] += 1
    m['weekly'] = [(wk0 + timedelta(weeks=i), v) for i, v in enumerate(weekly)]
    # daily series for the two 30-day windows, oldest first
    today = now.date()
    by_day = Counter(c['dt'].date() for c in commits)
    m['daily_last'] = [by_day[today - timedelta(days=29 - i)] for i in range(30)]
    m['daily_prev'] = [by_day[today - timedelta(days=59 - i)] for i in range(30)]
    # commit sizes per repository (private repositories pooled), for distribution plots
    m['size_by_repo'] = defaultdict(list)
    for c in commits:
        m['size_by_repo'][c['repo'] if c['repo'] in public else None].append(c['add'] + c['del'])
    m['sizes'] = []
    for label, lo, hi in SIZE_BUCKETS:
        m['sizes'].append((label, sum(1 for s in sizes if s >= lo and (hi is None or s <= hi))))

    # ---- repositories
    rows = []
    for name in repo_names:
        cs = [c for c in commits if c['repo'] == name]
        rows.append(dict(name=name, public=name in public, commits=len(cs), monthly=[p['repos'][name] for p in m['periods']],
                         added=sum(c['add'] for c in cs),
                         removed=sum(c['del'] for c in cs), last=max(c['dt'] for c in cs)))
    table = []
    for r in sorted((r for r in rows if r['public']), key=lambda r: -r['commits']):
        meta = public[r['name']]
        runs = [x for x in (_load(os.path.join(data_dir, 'runs_{}.json'.format(r['name'])), {}) or {}).get('workflow_runs', [])
                if x.get('event') != 'dynamic' and not x.get('name', '').startswith(AUTOMATED_RUN)]  # repo-defined workflows only
        concl = Counter(x.get('conclusion') for x in runs)
        issues = _load(os.path.join(data_dir, 'iss_{}.json'.format(r['name'])), []) or []
        durs = sorted((datetime.fromisoformat(x['updated_at'].replace('Z', '+00:00')) -
                       datetime.fromisoformat(x['run_started_at'].replace('Z', '+00:00'))).total_seconds()
                      for x in runs if x.get('run_started_at') and x.get('conclusion') in ('success', 'failure'))
        root = {x['name'] for x in (_load(os.path.join(data_dir, 'root_{}.json'.format(r['name'])), []) or [])}
        rels = _load(os.path.join(data_dir, 'rel_{}.json'.format(r['name'])), []) or []
        done = concl['success'] + concl['failure']
        for x in runs:
            started, ended = x.get('run_started_at'), x.get('updated_at')
            dur = ((datetime.fromisoformat(ended.replace('Z', '+00:00')) - datetime.fromisoformat(started.replace('Z', '+00:00'))).total_seconds()
                   if started and ended else None)
            m.setdefault('workflows', defaultdict(list))[(r['name'], x['name'])].append(
                (datetime.fromisoformat(x['created_at'].replace('Z', '+00:00')), x.get('conclusion'), dur))
        for x in issues:
            if 'pull_request' in x:
                merged = x['pull_request'].get('merged_at')
                m.setdefault('prs', []).append(dict(
                    repo=r['name'], state=x['state'], bot=x['user']['type'] == 'Bot' or x['user']['login'].endswith('[bot]'),
                    created=datetime.fromisoformat(x['created_at'].replace('Z', '+00:00')),
                    merged=datetime.fromisoformat(merged.replace('Z', '+00:00')) if merged else None))
        m.setdefault('ci_runs', []).extend((datetime.fromisoformat(x['created_at'].replace('Z', '+00:00')), x.get('conclusion')) for x in runs)
        table.append(dict(r, language=meta.get('language') or '—', stars=meta.get('stargazers_count', 0),
                          runs=sum(concl.values()), success=concl['success'], failure=concl['failure'], skipped=concl['skipped'],
                          pass_rate=concl['success'] / done if done else None, ci_median=durs[len(durs) // 2] if durs else None,
                          prs=sum(1 for x in issues if 'pull_request' in x),
                          issues_open=sum(1 for x in issues if 'pull_request' not in x and x['state'] == 'open'),
                          issues_closed=sum(1 for x in issues if 'pull_request' not in x and x['state'] == 'closed'),
                          practices=dict(
                              ci=bool(runs),
                              tests=bool(root & {'tests', 'test', 'e2e'}) or any(n.startswith(('vitest.config', 'jest.config', 'pytest.ini')) for n in root),
                              licence=bool(meta.get('license')),
                              manifest=bool(root & {'pyproject.toml', 'package.json', 'Cargo.toml', 'go.mod', 'setup.py'}),
                              release=bool(rels)),
                          releases=len(rels)))
    tests = _load(os.path.join(data_dir, 'tests.json'), {}) or {}
    for r in table:
        r['test_files'] = tests.get(r['name'])
    m['tests'] = dict(files=sum(v for v in tests.values() if v), repos=sum(1 for v in tests.values() if v), of=len(table))
    private = [r for r in rows if not r['public']]
    m['repo_table'] = table
    m['repo_private'] = dict(count=len(private), commits=sum(r['commits'] for r in private),
                             monthly=[sum(r['monthly'][i] for r in private) for i in range(len(m['periods']))], added=sum(r['added'] for r in private),
                             removed=sum(r['removed'] for r in private), last=max((r['last'] for r in private), default=None))
    n = len(table)
    m['practices'] = [(label, sum(1 for r in table if r['practices'][k]), n) for k, label in
                      (('ci', 'CI workflow'), ('tests', 'Test suite'), ('licence', 'Licence'), ('manifest', 'Package manifest'), ('release', 'Published release'))]
    m['runs'] = dict(success=sum(r['success'] for r in table), failure=sum(r['failure'] for r in table),
                     skipped=sum(r['skipped'] for r in table))
    meds = [r['ci_median'] for r in table if r['ci_median'] is not None]
    m['runs']['median'] = sorted(meds)[len(meds) // 2] if meds else None
    m['runs']['prs'] = sum(r['prs'] for r in table)
    m['runs']['issues_open'] = sum(r['issues_open'] for r in table)
    m['runs']['issues_closed'] = sum(r['issues_closed'] for r in table)
    m['runs']['releases'] = sum(r['releases'] for r in table)
    return m



def quantiles(values, qs=(0.1, 0.25, 0.5, 0.75, 0.9)):
    v = sorted(values)
    if not v:
        return [0] * len(qs)
    out = []
    for q in qs:
        pos = q * (len(v) - 1)
        lo = int(pos)
        hi = min(lo + 1, len(v) - 1)
        out.append(v[lo] + (v[hi] - v[lo]) * (pos - lo))
    return out
