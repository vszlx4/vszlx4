"""
Turns raw data into the numbers the dashboard shows. Pure functions, no drawing.

Inputs (a data directory written by fetch.py; never committed, because it holds private repository names):
  commits.json                  one record per authored commit: repo, date (ISO, with offset), subject, files [path, +, -]
  repos.json                    repositories the token can see (REST)
  runs_<repo>.json, iss_<repo>.json, tests.json   Actions runs, issues/PRs and test-file counts per owned public repository
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
SIZE_BUCKETS = [('1-10', 1, 10), ('11-50', 11, 50), ('51-200', 51, 200), ('201-1k', 201, 1000), ('1k-5k', 1001, 5000), ('5k+', 5001, None)]
AUTOMATED_RUN = ('Graph Update', 'pip in', 'npm in', 'github_actions in', 'Dependabot')
TYPES = ['Feature', 'Fix', 'Refactor', 'Test', 'Docs', 'Maintenance']
_PREFIX = {'feat': 'Feature', 'feature': 'Feature', 'fix': 'Fix', 'bugfix': 'Fix', 'hotfix': 'Fix', 'refactor': 'Refactor',
           'perf': 'Refactor', 'style': 'Refactor', 'test': 'Test', 'tests': 'Test', 'docs': 'Docs', 'doc': 'Docs',
           'chore': 'Maintenance', 'ci': 'Maintenance', 'build': 'Maintenance', 'deps': 'Maintenance', 'release': 'Maintenance',
           'revert': 'Maintenance'}
_KEYWORDS = [  # first match wins, for messages without a conventional prefix
    ('Fix', r'\b(fix(e[sd])?|bug|hot ?fix|patch|repair|resolve[sd]?|correct)\b'),
    ('Test', r'\b(tests?|testing|spec|coverage|e2e|pytest|vitest)\b'),
    ('Refactor', r'\b(refactor\w*|clean ?up|rename[sd]?|move[sd]?|extract|simplif\w*|restructur\w*|reorgani[sz]\w*|tidy)\b'),
    ('Docs', r'\b(docs?|readme|documentation|changelog|comments?|licen[cs]e)\b'),
    ('Maintenance', r'\b(chore|ci|workflow|deps?|dependenc\w*|bump|upgrade|config\w*|setup|release|version|merge)\b'),
]


def commit_type(subject):
    """Conventional-commit prefix if present, else keywords; anything else is a feature-sized change."""
    m = re.match(r'^\s*(\w+)(\([^)]*\))?!?:', subject or '')
    if m and m.group(1).lower() in _PREFIX:
        return _PREFIX[m.group(1).lower()]
    low = (subject or '').lower()
    for kind, pat in _KEYWORDS:
        if re.search(pat, low):
            return kind
    return 'Feature'


def _load(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _time(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00'))


def _lines(c):
    if not c['files'] and 'additions' in c:  # file list not fetched yet: totals only, no language split
        return c['additions'], c['deletions'], []
    files = [f for f in c['files'] if not EXCLUDE.search(f[0])]
    return sum(f[1] for f in files), sum(f[2] for f in files), files


def _months(first, last):
    k, end, out = first.year * 12 + first.month - 1, last.year * 12 + last.month - 1, []
    while k <= end:
        out.append((k // 12, k % 12 + 1))
        k += 1
    return out


def build(data_dir, now=None):
    repos = [r for r in _load(os.path.join(data_dir, 'repos.json'), []) if not r.get('fork')]
    public = {r['name']: r for r in repos if not r.get('private')}
    commits = _load(os.path.join(data_dir, 'commits.json'), [])
    for c in commits:
        c['dt'] = datetime.fromisoformat(c['date'])
        c['add'], c['del'], c['code'] = _lines(c)
    commits.sort(key=lambda c: c['dt'])
    now = now or datetime.now(commits[-1]['dt'].tzinfo if commits else None)
    first = commits[0]['dt'] if commits else now
    m = {'now': now, 'first': first}

    offsets = Counter(c['dt'].strftime('%z') for c in commits)
    off = offsets.most_common(1)[0][0] if offsets else '+0000'
    m['tz_label'] = 'UTC{}{}'.format(off[0], int(off[1:3])) + (':' + off[3:] if off[3:] != '00' else '')

    # ---- totals
    sizes = sorted(c['add'] + c['del'] for c in commits)
    repo_names = sorted({c['repo'] for c in commits})
    t = m['totals'] = dict(
        commits=len(commits), added=sum(c['add'] for c in commits), removed=sum(c['del'] for c in commits),
        active_days=len({c['dt'].date() for c in commits}), span_days=(now.date() - first.date()).days + 1,
        median_size=sizes[len(sizes) // 2] if sizes else 0, p90_size=sizes[int(len(sizes) * 0.9)] if sizes else 0,
        largest=sizes[-1] if sizes else 0)
    t['changed'] = t['added'] + t['removed']
    m['sizes'] = [(label, sum(1 for s in sizes if s >= lo and (hi is None or s <= hi))) for label, lo, hi in SIZE_BUCKETS]

    # ---- months: commits, commit types and lines added per language
    per = defaultdict(lambda: dict(commits=0, langs=Counter(), types=Counter()))
    for c in commits:
        p = per[(c['dt'].year, c['dt'].month)]
        p['commits'] += 1
        p['types'][commit_type(c['subject'])] += 1
        for f, a, _ in c['code']:
            ext = f.rsplit('.', 1)[-1].lower() if '.' in f.rsplit('/', 1)[-1] else ''
            if ext in LANG_BY_EXT:
                p['langs'][LANG_BY_EXT[ext]] += a
    m['periods'] = [dict(key=k, label=datetime(k[0], k[1], 1).strftime('%b'), year=k[0], **per[k]) for k in _months(first, now)]
    m['types'] = sum((p['types'] for p in m['periods']), Counter())
    lang_total = sum((p['langs'] for p in m['periods']), Counter())
    top = [l for l, _ in lang_total.most_common(5)]
    m['languages'] = dict(order=top + (['Other'] if len(lang_total) > len(top) else []), totals=lang_total, top=top)

    # ---- weekly series (Monday-start weeks) from the first commit's week to this week
    wk0 = (first - timedelta(days=first.weekday())).date()
    weekly = [0] * ((now.date() - wk0).days // 7 + 1)
    for c in commits:
        weekly[(c['dt'].date() - wk0).days // 7] += 1
    m['weekly'] = [(wk0 + timedelta(weeks=i), v) for i, v in enumerate(weekly)]

    # ---- last 30 days against the average 30-day window
    recent = [c for c in commits if c['dt'] >= now - timedelta(days=30)]
    windows = max(1, t['span_days'] / 30)
    m['momentum'] = dict(
        last=dict(commits=len(recent), changed=sum(c['add'] + c['del'] for c in recent), days=len({c['dt'].date() for c in recent})),
        avg=dict(commits=t['commits'] / windows, changed=t['changed'] / windows, days=t['active_days'] / windows))

    # ---- repositories: public ones by name, private ones pooled
    rows = []
    for name in repo_names:
        cs = [c for c in commits if c['repo'] == name]
        rows.append(dict(name=name, commits=len(cs), added=sum(c['add'] for c in cs), last=max(c['dt'] for c in cs)))
    private = [r for r in rows if r['name'] not in public]
    m['repo_private'] = dict(count=len(private), commits=sum(r['commits'] for r in private), added=sum(r['added'] for r in private),
                             last=max((r['last'] for r in private), default=None))
    tests = _load(os.path.join(data_dir, 'tests.json'), {}) or {}
    m['repo_table'], m['ci_runs'], m['prs'] = [], [], []
    durations = []
    concl = Counter()
    for r in (r for r in rows if r['name'] in public):
        runs = [x for x in (_load(os.path.join(data_dir, 'runs_{}.json'.format(r['name'])), {}) or {}).get('workflow_runs', [])
                if x.get('event') != 'dynamic' and not x.get('name', '').startswith(AUTOMATED_RUN)]  # repo-defined workflows only
        concl.update(x.get('conclusion') for x in runs)
        m['ci_runs'] += [(_time(x['created_at']), x.get('conclusion')) for x in runs]
        durations += [(_time(x['updated_at']) - _time(x['run_started_at'])).total_seconds()
                      for x in runs if x.get('run_started_at') and x.get('conclusion') in ('success', 'failure')]
        for x in _load(os.path.join(data_dir, 'iss_{}.json'.format(r['name'])), []) or []:
            if 'pull_request' in x:
                merged = x['pull_request'].get('merged_at')
                m['prs'].append(dict(repo=r['name'], state=x['state'], merged=_time(merged) if merged else None))
        m['repo_table'].append(dict(r, language=public[r['name']].get('language') or '-', test_files=tests.get(r['name'])))
    durations.sort()
    m['runs'] = dict(success=concl['success'], failure=concl['failure'], skipped=concl['skipped'],
                     median=durations[len(durations) // 2] if durations else None)
    return m
