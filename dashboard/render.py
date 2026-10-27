"""
Draws the dashboard SVG (dark) from the numbers in metrics.build().

Layout: 12 columns of 56px with 16px gutters and 24px margins (896px wide). Cards use 16px corners and 20px padding.
Two themes follow GitHub's own dark and light palettes. The interface is monochrome and brightness marks emphasis;
green, red and amber carry meaning only (added, pass/fail, activity status). Language and commit-type hues identify
a language or a type of change and nothing else.
"""
import math
from datetime import datetime, timedelta

from . import charts as ch
from . import metrics

M, G, COL = 24, 16, 56
W = M * 2 + 12 * COL + 11 * G  # 896
P = 20  # card padding
R = 16  # card radius; inner elements use 8

SANS = "'Geist','SF Pro Text','Segoe UI Variable Text','Segoe UI',system-ui,sans-serif"
THEMES = {
    'dark': dict(  # GitHub dark: canvas #0d1117, overlays #161b22, borders #30363d
        bg='#0d1117', card='#161b22', line='#30363d', inset='#0d1117', grid='#21262d',
        text='#e6edf3', text2='#9198a1', muted='#7d8590', faint='#21262d', mid='#6e7681', dim='#3d444d',
        green='#3fb950', red='#f85149', amber='#d29922',
        lang={'Python': '#f5d547', 'Svelte': '#f0661f', 'TypeScript': '#4a8fe0', 'HTML': '#cc2f5a', 'CSS': '#c4a1ff',
              'JavaScript': '#e8c547', 'Go': '#3fc1d9', 'Rust': '#d9875a', 'Shell': '#89e051', 'Other': '#6e7681'},
        types={'Feature': '#3fb950', 'Fix': '#4493f8', 'Refactor': '#f0883e', 'Test': '#ab7df8', 'Docs': '#39c5cf',
               'Maintenance': '#6e7681'},
    ),
    'light': dict(  # GitHub light: canvas #ffffff, muted surfaces #f6f8fa, borders #d1d9e0
        bg='#ffffff', card='#f6f8fa', line='#d1d9e0', inset='#ffffff', grid='#e6eaef',
        text='#1f2328', text2='#59636e', muted='#6e7781', faint='#e6eaef', mid='#8c959f', dim='#c8d1da',
        green='#1a7f37', red='#d1242f', amber='#9a6700',
        lang={'Python': '#9a6700', 'Svelte': '#f0781f', 'TypeScript': '#0969da', 'HTML': '#a0114a', 'CSS': '#c49cf7',
              'JavaScript': '#bf8700', 'Go': '#1b7c83', 'Rust': '#bc4c00', 'Shell': '#4d8a1f', 'Other': '#8c959f'},
        types={'Feature': '#1a7f37', 'Fix': '#0969da', 'Refactor': '#bc4c00', 'Test': '#8250df', 'Docs': '#1b7c83',
               'Maintenance': '#8c959f'},
    ),
}
T, LANG, TYPE = THEMES['dark'], THEMES['dark']['lang'], THEMES['dark']['types']


def col(i):
    return M + i * (COL + G)


def span(n):
    return n * COL + (n - 1) * G


def tw(s, size):
    """Approximate rendered width of sans text; numbers are tabular so this is stable."""
    return len(s) * size * 0.56


class D(ch.Svg):
    def tx(self, x, y, s, size=12, fill=None, weight=None, anchor=None):
        self.o.append('<text x="{}" y="{}" font-size="{}" fill="{}"{}{}>{}</text>'.format(
            ch._num(x), ch._num(y), size, fill or T['text'], ' font-weight="{}"'.format(weight) if weight else '',
            ' text-anchor="{}"'.format(anchor) if anchor else '', ch.esc(s)))

    def card(self, x, y, w, h, title, sub=None):
        self.el('rect', x=x + 0.5, y=y + 0.5, width=w - 1, height=h - 1, rx=R, fill=T['card'], stroke=T['line'])
        self.tx(x + P, y + 32, title, 14, T['text'], 600)
        if sub:
            self.tx(x + P, y + 50, sub, 11.5, T['muted'])

    def pill(self, x, y, label, tone=None, anchor='start'):
        """Rounded chip; tone tints it (green/red/amber), otherwise neutral."""
        w = tw(label, 11) + 18
        x0 = x - w if anchor == 'end' else x
        fill = tone or T['text2']
        self.el('rect', x=x0, y=y, width=w, height=22, rx=11, fill=fill, fill_opacity=0.12 if tone else 0.06,
                stroke=fill, stroke_opacity=0.25 if tone else 0.12)
        self.tx(x0 + w / 2, y + 15, label, 11, tone or T['text2'], 500, 'middle')
        return w

    def legend(self, x_right, y, items):
        x = x_right
        for label, color, dashed in reversed(items):
            x -= tw(label, 11)
            self.tx(x, y, label, 11, T['text2'])
            x -= 14
            if dashed:
                self.el('line', x1=x, y1=y - 4, x2=x + 10, y2=y - 4, stroke=color, stroke_width=1.5, stroke_dasharray='3 2')
            else:
                self.el('circle', cx=x + 4, cy=y - 4, r=4, fill=color)
            x -= 16


def monotone(points):
    """Monotone cubic (Fritsch-Carlson) path: smooth, never overshoots the data."""
    n = len(points)
    if n < 2:
        return ''
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
    m = [d[0]] + [0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2 for i in range(1, n - 1)] + [d[-1]]
    for i in range(n - 1):
        if d[i] == 0:
            m[i] = m[i + 1] = 0
        else:
            a, b = m[i] / d[i], m[i + 1] / d[i]
            s = a * a + b * b
            if s > 9:
                k = 3 / math.sqrt(s)
                m[i], m[i + 1] = k * a * d[i], k * b * d[i]
    out = 'M {:.1f} {:.1f}'.format(xs[0], ys[0])
    for i in range(n - 1):
        h = xs[i + 1] - xs[i]
        out += ' C {:.1f} {:.1f} {:.1f} {:.1f} {:.1f} {:.1f}'.format(xs[i] + h / 3, ys[i] + m[i] * h / 3,
                                                                    xs[i + 1] - h / 3, ys[i + 1] - m[i + 1] * h / 3, xs[i + 1], ys[i + 1])
    return out


def change(now, base):
    """Pill text and tone for now vs a baseline."""
    if base <= 0:
        return ('New', T['green']) if now else ('No change', None)
    r = now / base - 1
    if abs(r) < 0.005:
        return 'No change', None
    txt = ('+' if r > 0 else '−') + ('{:.1f}×'.format(now / base) if r >= 1 else '{:.0f}%'.format(abs(r) * 100))
    return txt, T['green'] if r > 0 else T['red']


def ago(now, then):
    sec = max(0, (now - then).total_seconds())
    if sec < 3600:
        return '{}m ago'.format(max(1, int(sec // 60)))
    if sec < 86400:
        return '{}h ago'.format(int(sec // 3600))
    return '{}d ago'.format(int(sec // 86400))


def duration(sec):
    if sec is None:
        return '-'
    if sec < 90:
        return '{:.0f}s'.format(sec)
    if sec < 5400:
        return '{:.0f}m'.format(sec / 60)
    if sec < 172800:
        return '{:.1f}h'.format(sec / 3600)
    return '{:.1f}d'.format(sec / 86400)


def draw(m):
    H = 1000
    s = D(W, H, T)
    s.o.append('<style>text{{font-family:{};font-variant-numeric:tabular-nums}}</style>'.format(SANS))
    s.rect(0, 0, W, H, T['bg'])
    tot, runs, mo, now = m['totals'], m['runs'], m['momentum'], m['now']
    ci_runs = m.get('ci_runs', [])
    done_runs = [(d, c) for d, c in ci_runs if c in ('success', 'failure')]

    # ---------------------------------------------------------------- KPI cards
    y, h = M, 88
    cutoff = now - timedelta(days=30)
    recent = [c for d, c in done_runs if d >= cutoff]
    rate_recent = recent.count('success') / len(recent) if recent else None
    rate_all = sum(1 for _, c in done_runs if c == 'success') / len(done_runs) if done_runs else None
    kpis = [
        ('Commits', ch.fmt_int(tot['commits']), change(mo['last']['commits'], mo['avg']['commits'])),
        ('Lines Changed', ch.fmt_compact(tot['changed']), change(mo['last']['changed'], mo['avg']['changed'])),
        ('Active Days', ch.fmt_int(tot['active_days']), change(mo['last']['days'], mo['avg']['days'])),
        ('CI Pass Rate', ch.fmt_pct(rate_all, 1) if rate_all is not None else '-',
         change(rate_recent, rate_all) if rate_recent is not None and rate_all else ('No change', None)),
    ]
    for i, (label, value, (delta, tone)) in enumerate(kpis):
        x = col(3 * i)
        s.el('rect', x=x + 0.5, y=y + 0.5, width=span(3) - 1, height=h - 1, rx=R, fill=T['card'], stroke=T['line'])
        s.tx(x + P, y + 30, label, 12, T['text2'])
        s.tx(x + P, y + 66, value, 28, T['text'], 600)
        arrow = '↗ ' if tone == T['green'] else '↘ ' if tone == T['red'] else ''
        s.pill(x + span(3) - P, y + 48, arrow + delta, tone, 'end')
        s.tx(x + span(3) - P, y + 30, 'last 30d vs avg', 11, T['muted'], anchor='end')

    # ---------------------------------------------------------------- commit activity (hero)
    y, h = 128, 248
    x, w = col(0), span(8)
    weekly = m['weekly']
    by_month = len(weekly) > 70  # long histories read better per month
    if by_month:
        series = [(datetime(p['key'][0], p['key'][1], 1).date(), p['commits']) for p in m['periods']]
    else:
        series = weekly
    vals = [v for _, v in series]
    avg = sum(vals) / len(vals)
    unit = 'month' if by_month else 'week'
    s.card(x, y, w, h, 'Commit Activity', 'Commits per {}'.format(unit))
    s.legend(x + w - P, y + 36, [('Commits', T['text'], False), ('Average', T['mid'], True)])
    gx0, gx1, gt, gb = x + P + 28, x + w - P, y + 76, y + h - 36
    ticks = ch.nice_ticks(max(vals + [1]), 4)
    sc = ch.Linear(0, ticks[-1], gb, gt)
    for v in ticks:
        s.hline(gx0, gx1, sc(v), T['grid'], dash=None if v == 0 else '2 4')
        s.tx(gx0 - 10, sc(v) + 4, ch.fmt_int(v), 10.5, T['muted'], anchor='end')
    n = len(vals)
    xs = lambda i: gx0 + (i / (n - 1) if n > 1 else 0.5) * (gx1 - gx0)
    pts = [(xs(i), sc(v)) for i, v in enumerate(vals)]
    s.o.append('<defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{c}" stop-opacity="0.16"/>'
               '<stop offset="1" stop-color="{c}" stop-opacity="0"/></linearGradient></defs>'.format(c=T['text']))
    line = monotone(pts) if n > 1 else ''
    if line:
        s.el('path', d='{} L {:.1f} {:.1f} L {:.1f} {:.1f} Z'.format(line, gx1, gb, gx0, gb), fill='url(#area)')
    s.hline(gx0, gx1, sc(avg), T['mid'], dash='3 3')
    if line:
        s.el('path', d=line, fill='none', stroke=T['text'], stroke_width=2, stroke_linejoin='round', stroke_linecap='round')
    # x labels: month names, or years once the span is long; never closer than 36px
    marks, last_key = [], None
    for i, (d, _) in enumerate(series):
        key = d.year if n > 36 and by_month else (d.year, d.month)
        if key != last_key:
            last_key = key
            marks.append((i, str(d.year) if n > 36 and by_month else d.strftime('%b')))
    last_x = -1e9
    for i, lab in marks:
        if xs(i) - last_x >= 36 and xs(i) <= gx1 - 12:
            s.tx(xs(i), gb + 22, lab, 10.5, T['muted'], anchor='middle')
            last_x = xs(i)
    if vals and max(vals) > 0:
        pk = vals.index(max(vals))
        px, py = pts[pk]
        s.el('line', x1=px, y1=gt - 4, x2=px, y2=gb, stroke=T['mid'], stroke_dasharray='3 3')
        s.el('circle', cx=px, cy=py, r=5, fill=T['card'], stroke=T['text'], stroke_width=2)
        d0 = series[pk][0]
        l1 = d0.strftime('%B %Y') if by_month else 'Week of {} {}'.format(d0.day, d0.strftime('%b'))
        l2 = '{} commits'.format(vals[pk])
        bw = max(tw(l1, 11), tw(l2, 13)) + 24
        bx = px + 12 if px + 12 + bw < gx1 else px - 12 - bw
        by = max(gt, py - 18)
        s.el('rect', x=bx, y=by, width=bw, height=44, rx=8, fill=T['inset'], stroke=T['line'])
        s.tx(bx + 12, by + 18, l1, 11, T['text2'])
        s.tx(bx + 12, by + 35, l2, 13, T['text'], 600)

    # ---------------------------------------------------------------- languages (donut)
    x, w = col(8), span(4)
    langs = m['languages']
    vals_l = [(l, langs['totals'][l] if l != 'Other' else sum(v for k, v in langs['totals'].items() if k not in langs['top']))
              for l in langs['order']]
    grand = sum(v for _, v in vals_l) or 1
    s.card(x, y, w, h, 'Languages', '{} lines added in source files'.format(ch.fmt_compact(grand)))
    cx, cy, r = x + P + 52, y + 148, 50
    a = -math.pi / 2
    for l, v in vals_l:
        sw = 2 * math.pi * v / grand
        if sw > 0.04:
            s.el('path', d=_arc(cx, cy, r, a + 0.02, a + sw - 0.02), fill='none', stroke=LANG.get(l, LANG['Other']), stroke_width=16)
        a += sw
    if vals_l:
        top_l, top_v = vals_l[0]
        s.tx(cx, cy - 4, top_l, 11.5, T['text2'], anchor='middle')
        s.tx(cx, cy + 16, ch.fmt_pct(top_v / grand), 20, T['text'], 600, anchor='middle')
    lx0, lx1 = x + P + 122, x + w - P
    for i, (l, v) in enumerate(vals_l):
        ry = y + 92 + i * 22
        s.el('circle', cx=lx0 + 4, cy=ry - 4, r=4, fill=LANG.get(l, LANG['Other']))
        s.tx(lx0 + 14, ry, l, 12, T['text'])
        s.tx(lx1, ry, ch.fmt_pct(v / grand), 12, T['text2'], anchor='end')

    # ---------------------------------------------------------------- commit types: ranked list + monthly stacked columns
    y, h = 392, 280
    x, w = col(0), span(8)
    types = m['types']
    total_t = sum(types.values()) or 1
    s.card(x, y, w, h, 'Commit Types', 'Classified from commit messages')
    lx0, lx1 = x + P, x + P + 196
    ranked = sorted((t_ for t_ in metrics.TYPES if types.get(t_)), key=lambda k: -types[k])
    top_n = max(types.values()) if types else 1
    for i, t_ in enumerate(ranked):
        ry = y + 84 + i * 30
        s.rect(lx0, ry - 9, 10, 10, TYPE[t_], rx=3)
        s.tx(lx0 + 18, ry, t_, 12.5, T['text'], 500)
        s.tx(lx1 - 44, ry, ch.fmt_int(types[t_]), 12.5, T['text'], 600, 'end')
        s.tx(lx1, ry, ch.fmt_pct(types[t_] / total_t), 12, T['muted'], anchor='end')
        s.rect(lx0 + 18, ry + 7, (lx1 - lx0 - 18) * types[t_] / top_n, 3, TYPE[t_], rx=1.5)
    s.vline(lx1 + 20, y + 72, y + h - 20, T['line'])
    periods = m['periods']
    gx0, gx1, gt, gb = lx1 + 64, x + w - P, y + 80, y + h - 44
    ticks = ch.nice_ticks(max([p['commits'] for p in periods] + [1]), 3)
    sc = ch.Linear(0, ticks[-1], gb, gt)
    for v in ticks:
        s.hline(gx0, gx1, sc(v), T['grid'], dash=None if v == 0 else '2 4')
        s.tx(gx0 - 8, sc(v) + 4, ch.fmt_int(v), 10.5, T['muted'], anchor='end')
    band = (gx1 - gx0) / len(periods)
    bw = max(2, min(22, band * 0.62))
    for i, p in enumerate(periods):
        cx = gx0 + band * (i + 0.5)
        acc = 0
        for t_ in metrics.TYPES:  # Feature at the bottom, same order as the palette
            v = p['types'].get(t_, 0)
            if not v:
                continue
            y_top, y_bot = sc(acc + v), sc(acc)
            s.rect(cx - bw / 2, y_top, bw, max(1, y_bot - y_top - (1.5 if acc else 0)), TYPE[t_], rx=2)
            acc += v
        if not p['commits']:
            s.rect(cx - bw / 2, gb - 2, bw, 2, T['faint'], rx=1)
    long_span = len(periods) > 24
    last_x = -1e9
    for i, p in enumerate(periods):
        if long_span and not (i == 0 or p['key'][1] == 1):
            continue
        cx = gx0 + band * (i + 0.5)
        if cx - last_x < 30:
            continue
        s.tx(cx, gb + 22, str(p['year']) if long_span else p['label'], 10.5, T['muted'], anchor='middle')
        last_x = cx

    # ---------------------------------------------------------------- CI health, with data status
    x, w = col(8), span(4)
    s.card(x, y, w, h, 'CI Health', 'Repository workflows')
    done_n = runs['success'] + runs['failure']
    rate = runs['success'] / done_n if done_n else 0
    cx, cy, r = x + P + 46, y + 114, 40
    a0, a1 = math.radians(135), math.radians(405)
    s.el('path', d=_arc(cx, cy, r, a0, a1), fill='none', stroke=T['faint'], stroke_width=8, stroke_linecap='round')
    if done_n:
        s.el('path', d=_arc(cx, cy, r, a0, a0 + (a1 - a0) * rate), fill='none', stroke=T['green'] if rate >= 0.9 else T['amber'],
             stroke_width=8, stroke_linecap='round')
    s.tx(cx, cy + 4, ch.fmt_pct(rate, 1) if done_n else '-', 15, T['text'], 600, 'middle')
    s.tx(cx, cy + 36, 'pass rate', 10.5, T['muted'], anchor='middle')
    rx0, rx1 = x + P + 108, x + w - P
    for i, (lab, val, c) in enumerate((('Passed', ch.fmt_int(runs['success']), T['green']), ('Failed', ch.fmt_int(runs['failure']), T['red']),
                                       ('Skipped', ch.fmt_int(runs['skipped']), T['mid']), ('Median run', duration(runs['median']), None))):
        ry = y + 86 + i * 22
        if c:
            s.el('circle', cx=rx0 + 4, cy=ry - 4, r=3.5, fill=c)
        s.tx(rx0 + (13 if c else 0), ry, lab, 12, T['text2'])
        s.tx(rx1, ry, val, 12, T['text'], 500, 'end')
    s.hline(x + P, x + w - P, y + 180, T['line'])
    last = max(done_runs, key=lambda t: t[0]) if done_runs else None  # latest run that passed or failed
    status = [
        ('Last run', ('Passed' if last[1] == 'success' else 'Failed' if last[1] == 'failure' else 'Skipped') + ', ' + ago(now, last[0])
         if last else 'None', T['green'] if last and last[1] == 'success' else T['red'] if last and last[1] == 'failure' else None),
        ('Data from', '{} - {}'.format(m['first'].strftime('%b %Y'), now.strftime('%b %Y')), None),
        ('Updated', '{} {}'.format(now.strftime('%d %b %Y, %H:%M'), m['tz_label']), T['green']),
    ]
    for i, (lab, val, c) in enumerate(status):
        ry = y + 206 + i * 24
        s.tx(x + P, ry, lab, 12, T['muted'])
        s.tx(x + w - P, ry, val, 12, T['text'], anchor='end')
        if c:
            s.el('circle', cx=x + w - P - tw(val, 12) - 10, cy=ry - 4, r=3.5, fill=c)

    # ---------------------------------------------------------------- repositories (table with status pills)
    y = 688
    rows = sorted(m['repo_table'], key=lambda r: -r['commits'])[:6]
    pv = m['repo_private']
    if pv['count']:
        rows.append(dict(pv, name='{} private repos'.format(pv['count']), language=None, private=True))
    h = max(288, 96 + len(rows) * 30 + 8)
    x, w = col(0), span(8)
    s.card(x, y, w, h, 'Repositories', 'Ranked by commits')
    X = dict(name=x + P, status=x + 140, lang=x + 214, commits=x + 330, added=x + 392, prs=x + 434, tests=x + 480, last=x + w - P)
    hy = y + 80
    for k, lab, anc in (('name', 'Repository', None), ('status', 'Status', None), ('lang', 'Language', None),
                        ('commits', 'Commits', 'end'), ('added', 'Lines', 'end'), ('prs', 'PRs', 'end'), ('tests', 'Tests', 'end'),
                        ('last', 'Last Commit', 'end')):
        s.tx(X[k], hy, lab, 11, T['muted'], anchor=anc)
    s.hline(x + P, x + w - P, hy + 10, T['line'])
    for i, r in enumerate(rows):
        ry = hy + 34 + i * 30
        if i:
            s.hline(x + P, x + w - P, ry - 19, T['grid'])
        days = (now - r['last']).days
        status, tone = ('Active', T['green']) if days <= 14 else ('Idle', T['amber']) if days <= 60 else ('Dormant', None)
        name = r['name'] if len(r['name']) <= 18 else r['name'][:17] + '…'
        s.tx(X['name'], ry, name, 12, T['text2'] if r.get('private') else T['text'], None if r.get('private') else 500)
        s.pill(X['status'], ry - 15, status, tone)
        if r.get('language'):
            s.el('circle', cx=X['lang'] + 4, cy=ry - 4, r=4, fill=LANG.get(r['language'], LANG['Other']))
            s.tx(X['lang'] + 14, ry, r['language'], 12, T['text2'])
        else:
            s.tx(X['lang'], ry, 'Mixed', 12, T['muted'])
        s.tx(X['commits'], ry, ch.fmt_int(r['commits']), 12, T['text'], 500, 'end')
        s.tx(X['added'], ry, '+' + ch.fmt_compact(r['added']), 12, T['green'], anchor='end')
        merged = None if r.get('private') else sum(1 for p_ in m.get('prs', []) if p_['repo'] == r['name'] and p_['merged'])
        for key, v in (('prs', merged), ('tests', None if r.get('private') else r.get('test_files'))):
            s.tx(X[key], ry, '-' if v is None else ch.fmt_int(v), 12, T['muted'] if v is None else T['text2'], anchor='end')
        s.tx(X['last'], ry, 'Today' if days == 0 else '{}d ago'.format(days), 12, T['text2'], anchor='end')

    # ---------------------------------------------------------------- commit size: figures + histogram
    x, w = col(8), span(4)
    s.card(x, y, w, h, 'Commit Size', 'Lines changed per commit')
    figs = [('Median', ch.fmt_int(tot['median_size'])), ('90th pct.', ch.fmt_compact(tot['p90_size'])),
            ('Largest', ch.fmt_compact(tot['largest']))]
    cw = (w - 2 * P) / 3
    for i, (lab, val) in enumerate(figs):
        fx = x + P + i * cw
        if i:
            s.vline(fx - 10, y + 64, y + 106, T['line'])
        s.tx(fx, y + 78, lab, 11, T['muted'])
        s.tx(fx, y + 100, val, 18, T['text'], 600)
    s.hline(x + P, x + w - P, y + 122, T['line'])
    sizes = m['sizes']
    mx = max(v for _, v in sizes) or 1
    med = tot['median_size']
    med_i = next((i for i, b in enumerate(metrics.SIZE_BUCKETS) if med >= b[1] and (b[2] is None or med <= b[2])), None)
    gx0, gx1, gt, gb = x + P, x + w - P, y + 156, y + h - 38
    s.hline(gx0, gx1, gb, T['grid'])
    band = (gx1 - gx0) / len(sizes)
    for i, (lab, v) in enumerate(sizes):
        cxb = gx0 + band * (i + 0.5)
        hh = max(2, (gb - gt) * v / mx) if v else 2
        s.rect(cxb - 11, gb - hh, 22, hh, T['text'] if i == med_i else T['dim'] if v else T['faint'], rx=3)
        s.tx(cxb, gb - hh - 7, ch.fmt_int(v), 11, T['text'] if i == med_i else T['text2'], 600 if i == med_i else None, 'middle')
        s.tx(cxb, gb + 20, lab, 10.5, T['muted'], anchor='middle')

    final_h = y + h + M
    s.o[1] = s.o[1].replace('height="{}"'.format(H), 'height="{}"'.format(final_h))
    s.h = final_h
    return s


def _arc(cx, cy, r, a0, a1):
    x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
    x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
    return 'M {:.2f} {:.2f} A {} {} 0 {} 1 {:.2f} {:.2f}'.format(x0, y0, r, r, 1 if a1 - a0 > math.pi else 0, x1, y1)


def render(m, theme='dark'):
    global T, LANG, TYPE
    T, LANG, TYPE = THEMES[theme], THEMES[theme]['lang'], THEMES[theme]['types']
    svg = draw(m).render('Development activity dashboard')
    return svg.replace('role="img"', 'role="img" style="color-scheme:{}"'.format(theme), 1)
