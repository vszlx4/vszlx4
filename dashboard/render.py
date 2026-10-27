"""
Draws the dashboard SVG (dark) from the numbers in metrics.build().

Layout: 12 columns of 56px with 16px gutters and 24px margins (896px wide). Cards use 16px corners and 20px padding.
Two themes follow GitHub's own dark and light palettes. The interface is monochrome and brightness marks emphasis;
green, red and amber carry meaning only (added, pass/fail, activity status). Language and commit-type hues identify
a language or a type of change and nothing else.
"""
import math

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
TYPE_LABEL = {'Docs': 'Documentation'}


def col(i):
    return M + i * (COL + G)


def span(n):
    return n * COL + (n - 1) * G


def tw(s, size):
    """Approximate rendered width of sans text; numbers are tabular so this is stable."""
    return len(s) * size * 0.56


class D(ch.Svg):
    def tx(self, x, y, s, size=12, fill=None, weight=None, anchor=None, cls=None):
        self.o.append('<text x="{}" y="{}" font-size="{}" fill="{}"{}{}{}>{}</text>'.format(
            ch._num(x), ch._num(y), size, fill or T['text'], ' font-weight="{}"'.format(weight) if weight else '',
            ' text-anchor="{}"'.format(anchor) if anchor else '', ' class="{}"'.format(cls) if cls else '', ch.esc(s)))

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


def day(d):
    """'3 Oct' style date, no leading zero."""
    return '{} {}'.format(d.day, d.strftime('%b'))


def stamp(d):
    return '{} {} {}, {}'.format(d.day, d.strftime('%b'), d.year, d.strftime('%H:%M'))


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


def age(joined, now):
    months = (now.year - joined.year) * 12 + now.month - joined.month - (1 if now.day < joined.day else 0)
    return '{}y {}m'.format(months // 12, months % 12)


def draw(m):
    H = 1000
    s = D(W, H, T)
    s.o.append('<style>text{{font-family:{};font-variant-numeric:tabular-nums}}</style>'.format(SANS))
    s.rect(0, 0, W, H, T['bg'])
    tot, runs, mo, now = m['totals'], m['runs'], m['momentum'], m['now']
    done_runs = [(d, c) for d, c in m.get('ci_runs', []) if c in ('success', 'failure')]

    # ---------------------------------------------------------------- lifetime totals + two 30-day cards
    y, h = M, 88
    x, w = col(0), span(6)
    s.el('rect', x=x + 0.5, y=y + 0.5, width=w - 1, height=h - 1, rx=R, fill=T['card'], stroke=T['line'])
    figs = [('Total Commits', ch.fmt_int(tot['commits'])), ('Lines Added', ch.fmt_compact(tot['added'])),
            ('Lines Deleted', ch.fmt_compact(tot['removed'])), ('Account Age', age(m['joined'], now) if m.get('joined') else '-')]
    cw = (w - 2 * P) / len(figs)
    for i, (lab, val) in enumerate(figs):
        fx = x + P + i * cw
        if i:
            s.vline(fx - 12, y + 18, y + h - 18, T['line'])
        s.tx(fx, y + 30, lab, 12, T['text2'])
        s.tx(fx, y + 66, val, 24, T['text'], 600)
    for i, (label, key) in enumerate((('Commits', 'commits'), ('Active Days', 'days'))):
        x = col(6 + 3 * i)
        s.el('rect', x=x + 0.5, y=y + 0.5, width=span(3) - 1, height=h - 1, rx=R, fill=T['card'], stroke=T['line'])
        s.tx(x + P, y + 30, label, 12, T['text2'])
        s.tx(x + span(3) - P, y + 30, 'Last 30 days', 11, T['muted'], anchor='end')
        s.tx(x + P, y + 66, ch.fmt_int(mo['last'][key]), 28, T['text'], 600)
        delta, tone = change(mo['last'][key], mo['prev'][key])
        arrow = '↗ ' if tone == T['green'] else '↘ ' if tone == T['red'] else ''
        s.pill(x + span(3) - P, y + 48, arrow + delta, tone, 'end')

    # ---------------------------------------------------------------- commit activity: last 30 days, daily
    y, h = 128, 248
    x, w = col(0), span(8)
    days = m['days_last']
    vals = [v for _, v in days]
    prev_avg = sum(v for _, v in m['days_prev']) / 30
    s.card(x, y, w, h, 'Commit Activity', 'Daily commits over the last 30 days')
    s.legend(x + w - P, y + 36, [('Daily commits', T['text'], False), ('Prior 30-day average', T['mid'], True)])
    gx0, gx1, gt, gb = x + P + 28, x + w - P, y + 76, y + h - 36
    ticks = ch.nice_ticks(max(vals + [prev_avg, 1]), 4)
    sc = ch.Linear(0, ticks[-1], gb, gt)
    for v in ticks:
        s.hline(gx0, gx1, sc(v), T['grid'], dash=None if v == 0 else '2 4')
        s.tx(gx0 - 10, sc(v) + 4, ch.fmt_int(v), 10.5, T['muted'], anchor='end')
    xs = lambda i: gx0 + i / 29 * (gx1 - gx0)
    pts = [(xs(i), sc(v)) for i, v in enumerate(vals)]
    s.o.append('<defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{c}" stop-opacity="0.16"/>'
               '<stop offset="1" stop-color="{c}" stop-opacity="0"/></linearGradient></defs>'.format(c=T['text']))
    line = monotone(pts)
    s.el('path', d='{} L {:.1f} {:.1f} L {:.1f} {:.1f} Z'.format(line, gx1, gb, gx0, gb), fill='url(#area)')
    s.el('line', x1=gx0, y1=sc(prev_avg), x2=gx1, y2=sc(prev_avg), stroke=T['mid'], stroke_width=1.5, stroke_dasharray='4 3')
    s.el('path', d=line, fill='none', stroke=T['text'], stroke_width=2, stroke_linejoin='round', stroke_linecap='round')
    for i in range(0, 30, 5):
        s.tx(xs(i), gb + 22, day(days[i][0]), 10.5, T['muted'], anchor='middle')
    s.tx(gx1, gb + 22, 'Today', 10.5, T['muted'], anchor='end')
    if max(vals) > 0:
        pk = max(range(30), key=lambda i: (vals[i], i))
        px, py = pts[pk]
        s.el('line', x1=px, y1=gt - 4, x2=px, y2=gb, stroke=T['mid'], stroke_dasharray='3 3')
        s.el('circle', cx=px, cy=py, r=5, fill=T['card'], stroke=T['text'], stroke_width=2)
        l1, l2 = day(days[pk][0]) + ' ' + str(days[pk][0].year), '{} commits'.format(vals[pk])
        bw = max(tw(l1, 11), tw(l2, 13)) + 24
        bx = px + 12 if px + 12 + bw < gx1 else px - 12 - bw
        by = max(gt, py - 18)
        s.el('rect', x=bx, y=by, width=bw, height=44, rx=8, fill=T['inset'], stroke=T['line'])
        s.tx(bx + 12, by + 18, l1, 11, T['text2'])
        s.tx(bx + 12, by + 35, l2, 13, T['text'], 600)
    else:
        s.tx((gx0 + gx1) / 2, (gt + gb) / 2, 'No commits in the last 30 days', 12, T['muted'], anchor='middle')

    # ---------------------------------------------------------------- language distribution (donut)
    x, w = col(8), span(4)
    langs = m['languages']
    vals_l = [(l, langs['totals'][l] if l != 'Other' else sum(v for k, v in langs['totals'].items() if k not in langs['top']))
              for l in langs['order']]
    grand = sum(v for _, v in vals_l) or 1
    s.card(x, y, w, h, 'Language Distribution', 'Share of {} lines added in source files'.format(ch.fmt_compact(grand)))
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

    # ---------------------------------------------------------------- commit categories: ranked list + monthly stacked columns
    y, h = 392, 280
    x, w = col(0), span(8)
    types = m['types']
    total_t = sum(types.values()) or 1
    s.card(x, y, w, h, 'Commit Categories', 'Classified by commit message prefix and keywords')
    lx0, lx1 = x + P, x + P + 196
    ranked = sorted((t_ for t_ in metrics.TYPES if types.get(t_)), key=lambda k: -types[k])
    top_n = max(types.values()) if types else 1
    for i, t_ in enumerate(ranked):
        ry = y + 84 + i * 30
        s.rect(lx0, ry - 9, 10, 10, TYPE[t_], rx=3)
        s.tx(lx0 + 18, ry, TYPE_LABEL.get(t_, t_), 12.5, T['text'], 500)
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
        cxb = gx0 + band * (i + 0.5)
        acc = 0
        for t_ in metrics.TYPES:  # Feature at the bottom, same order as the list colours
            v = p['types'].get(t_, 0)
            if not v:
                continue
            y_top, y_bot = sc(acc + v), sc(acc)
            s.rect(cxb - bw / 2, y_top, bw, max(1, y_bot - y_top - (1.5 if acc else 0)), TYPE[t_], rx=2)
            acc += v
        if not p['commits']:
            s.rect(cxb - bw / 2, gb - 2, bw, 2, T['faint'], rx=1)
    long_span = len(periods) > 24
    last_x = -1e9
    for i, p in enumerate(periods):
        if long_span and not (i == 0 or p['key'][1] == 1):
            continue
        cxb = gx0 + band * (i + 0.5)
        if cxb - last_x >= 30:
            s.tx(cxb, gb + 22, str(p['year']) if long_span else p['label'], 10.5, T['muted'], anchor='middle')
            last_x = cxb

    # ---------------------------------------------------------------- continuous integration
    x, w = col(8), span(4)
    s.card(x, y, w, h, 'Continuous Integration', 'Workflow runs in public repositories')
    done_n = runs['success'] + runs['failure']
    rate = runs['success'] / done_n if done_n else 0
    cx, cy, r = x + P + 46, y + 114, 40
    a0, a1 = math.radians(135), math.radians(405)
    s.el('path', d=_arc(cx, cy, r, a0, a1), fill='none', stroke=T['faint'], stroke_width=8, stroke_linecap='round')
    if done_n:
        s.el('path', d=_arc(cx, cy, r, a0, a0 + (a1 - a0) * rate), fill='none', stroke=T['green'] if rate >= 0.9 else T['amber'],
             stroke_width=8, stroke_linecap='round')
    s.tx(cx, cy + 4, ch.fmt_pct(rate, 1) if done_n else '-', 15, T['text'], 600, 'middle')
    s.tx(cx, cy + 36, 'success rate', 10.5, T['muted'], anchor='middle')
    # every row has the same dot column, so labels and dots line up whether or not a row has a dot
    rx0, rx1 = x + P + 108, x + w - P
    for i, (lab, val, c) in enumerate((('Succeeded', ch.fmt_int(runs['success']), T['green']),
                                       ('Failed', ch.fmt_int(runs['failure']), T['red']),
                                       ('Skipped', ch.fmt_int(runs['skipped']), T['mid']),
                                       ('Median time', duration(runs['median']), None))):
        ry = y + 86 + i * 22
        if c:
            s.el('circle', cx=rx0 + 4, cy=ry - 4, r=3.5, fill=c)
        s.tx(rx0 + 14, ry, lab, 12, T['text2'])
        s.tx(rx1, ry, val, 12, T['text'], 500, 'end')
    s.hline(x + P, x + w - P, y + 180, T['line'])
    last = max(done_runs, key=lambda t_: t_[0]) if done_runs else None
    status = [
        ('Latest run', ('Succeeded' if last[1] == 'success' else 'Failed') + ', ' + day(last[0].astimezone(now.tzinfo))
         if last else 'None', T['green'] if last and last[1] == 'success' else T['red'] if last else None, None),
        ('Reporting period', '{} - {}'.format(m['first'].strftime('%b %Y'), now.strftime('%b %Y')), None, None),
        ('Last updated', '{} {}'.format(stamp(now), m['tz_label']), T['green'], 'stamp'),
    ]
    for i, (lab, val, c, cls) in enumerate(status):
        ry = y + 206 + i * 24
        if c:
            s.el('circle', cx=x + P + 4, cy=ry - 4, r=3.5, fill=c)
        s.tx(x + P + 14, ry, lab, 12, T['muted'])
        s.tx(x + w - P, ry, val, 12, T['text'], anchor='end', cls=cls)

    # ---------------------------------------------------------------- repositories
    y = 688
    rows = sorted(m['repo_table'], key=lambda r_: -r_['commits'])[:6]
    pv = m['repo_private']
    if pv['count']:
        rows.append(dict(pv, name='Private ({})'.format(pv['count']), language=None, private=True))
    h = max(288, 96 + len(rows) * 30 + 8)
    x, w = col(0), span(8)
    s.card(x, y, w, h, 'Repositories', 'Ranked by commit count')
    X = dict(name=x + P, status=x + 132, lang=x + 206, commits=x + 322, added=x + 384, prs=x + 432, tests=x + 466, last=x + w - P)
    hy = y + 80
    for k, lab, anc in (('name', 'Repository', None), ('status', 'Status', None), ('lang', 'Language', None),
                        ('commits', 'Commits', 'end'), ('added', 'Lines', 'end'), ('prs', 'PRs', 'end'), ('tests', 'Tests', 'end'),
                        ('last', 'Last Commit', 'end')):
        s.tx(X[k], hy, lab, 11, T['muted'], anchor=anc)
    s.hline(x + P, x + w - P, hy + 10, T['line'])
    for i, r_ in enumerate(rows):
        ry = hy + 34 + i * 30
        if i:
            s.hline(x + P, x + w - P, ry - 19, T['grid'])
        idle = (now - r_['last']).days
        status, tone = ('Active', T['green']) if idle <= 14 else ('Idle', T['amber']) if idle <= 60 else ('Inactive', None)
        name = r_['name'] if len(r_['name']) <= 15 else r_['name'][:14] + '…'
        s.tx(X['name'], ry, name, 12, T['text2'] if r_.get('private') else T['text'], None if r_.get('private') else 500)
        s.pill(X['status'], ry - 15, status, tone)
        if r_.get('language'):
            s.el('circle', cx=X['lang'] + 4, cy=ry - 4, r=4, fill=LANG.get(r_['language'], LANG['Other']))
            s.tx(X['lang'] + 14, ry, r_['language'], 12, T['text2'])
        else:
            s.tx(X['lang'], ry, 'Multiple', 12, T['muted'])
        s.tx(X['commits'], ry, ch.fmt_int(r_['commits']), 12, T['text'], 500, 'end')
        s.tx(X['added'], ry, '+' + ch.fmt_compact(r_['added']), 12, T['green'], anchor='end')
        merged = None if r_.get('private') else sum(1 for p_ in m.get('prs', []) if p_['repo'] == r_['name'] and p_['merged'])
        for key, v in (('prs', merged), ('tests', None if r_.get('private') else r_.get('test_files'))):
            s.tx(X[key], ry, '-' if v is None else ch.fmt_int(v), 12, T['muted'] if v is None else T['text2'], anchor='end')
        last_d = r_['last'].astimezone(now.tzinfo)
        s.tx(X['last'], ry, day(last_d) + ('' if last_d.year == now.year else ' ' + str(last_d.year)), 12, T['text2'], anchor='end')

    # ---------------------------------------------------------------- activity records
    x, w = col(8), span(4)
    s.card(x, y, w, h, 'Activity Records', 'Streaks and peak activity')
    rec = m['records']
    lg = rec['longest']
    wd = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    tiles = [
        ('Current Streak', '{} day{}'.format(rec['current_streak'], '' if rec['current_streak'] == 1 else 's'),
         'Since ' + day(rec['current_since']) if rec['current_since'] else
         'Last commit ' + day(rec['last_active']) if rec['last_active'] else ''),
        ('Longest Streak', '{} days'.format(lg[2]) if lg[2] else '-', '{} - {}'.format(day(lg[0]), day(lg[1])) if lg[2] else ''),
        ('Busiest Day', '{} commits'.format(rec['busiest_day'][1]) if rec['busiest_day'] else '-',
         day(rec['busiest_day'][0]) + ' ' + str(rec['busiest_day'][0].year) if rec['busiest_day'] else ''),
        ('Busiest Month', '{} commits'.format(rec['busiest_month']['commits']) if rec['busiest_month'] else '-',
         '{} {}'.format(rec['busiest_month']['label'], rec['busiest_month']['year']) if rec['busiest_month'] else ''),
        ('Top Weekday', wd[rec['weekday'][0]] if rec['weekday'] else '-',
         '{} of commits'.format(ch.fmt_pct(rec['weekday'][1] / tot['commits'])) if rec['weekday'] else ''),
        ('Peak Hour', '{:02d}:00'.format(rec['hour'][0]) if rec['hour'] else '-', 'Local time, {}'.format(m['tz_label'])),
    ]
    tw_ = (w - 2 * P) / 2
    for i, (lab, val, sub) in enumerate(tiles):
        tx_, ty = x + P + (i % 2) * tw_, y + 86 + (i // 2) * 70
        if i % 2:
            s.vline(tx_ - 12, ty - 14, ty + 34, T['line'])
        if i >= 2 and i % 2 == 0:
            s.hline(x + P, x + w - P, ty - 21, T['line'])
        s.tx(tx_, ty, lab, 11, T['muted'])
        s.tx(tx_, ty + 20, val, 15, T['text'], 600)
        s.tx(tx_, ty + 36, sub, 10.5, T['muted'])

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
