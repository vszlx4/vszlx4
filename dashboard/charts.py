"""
Minimal SVG charting: scales, nice ticks, number formats and the marks the card uses.
Every chart draws into an explicit plot box, so alignment comes from the layout grid, never from guesses.
"""
import math

SANS = "'Geist','SF Pro Text','Segoe UI Variable Text','Segoe UI',system-ui,sans-serif"
MONO = "'Geist Mono','SF Mono','Cascadia Mono',Consolas,monospace"


# ------------------------------------------------------------------ formatting
def fmt_int(v):
    return '{:,}'.format(int(round(v)))


def fmt_compact(v):
    a = abs(v)
    if a >= 1e6:
        s = '{:.1f}M'.format(a / 1e6)
    elif a >= 1e4:
        s = '{:.0f}k'.format(a / 1e3)
    elif a >= 1e3:
        s = '{:.1f}k'.format(a / 1e3)
    else:
        s = str(int(round(a)))
    s = s.replace('.0k', 'k').replace('.0M', 'M')
    return ('−' if v < 0 else '') + s


def fmt_pct(v, digits=0):
    return '{:.{}f}%'.format(v * 100, digits)


def fmt_delta(now, before):
    if before == 0:
        return 'new' if now else '0%'
    d = now / before - 1
    return ('+' if d >= 0 else '−') + '{:.0f}%'.format(abs(d) * 100)


# ------------------------------------------------------------------ scales
def nice_step(raw):
    """Smallest of 1, 2, 2.5, 5 x 10^k that is >= raw."""
    if raw <= 0:
        return 1
    p = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if m * p >= raw - 1e-9:
            return m * p
    return 10 * p


def nice_ticks(vmax, count=4, integer=True):
    """Ticks from 0 to a round top that covers vmax, with `count` intervals or fewer."""
    vmax = max(vmax, 1 if integer else 1e-9)
    step = nice_step(vmax / count)
    if integer:
        step = max(1, math.ceil(step))
    top = math.ceil(vmax / step - 1e-9) * step
    n = int(round(top / step))
    return [i * step for i in range(n + 1)]


class Linear:
    def __init__(self, d0, d1, r0, r1):
        self.d0, self.d1, self.r0, self.r1 = d0, d1, r0, r1

    def __call__(self, v):
        if self.d1 == self.d0:
            return self.r0
        return self.r0 + (v - self.d0) / (self.d1 - self.d0) * (self.r1 - self.r0)


class Band:
    """n equal bands across [r0, r1]; mark width is a share of the band, capped."""
    def __init__(self, n, r0, r1, fill=0.62, cap=28):
        self.n, self.r0, self.r1 = n, r0, r1
        self.step = (r1 - r0) / max(1, n)
        self.width = min(cap, self.step * fill)

    def center(self, i):
        return self.r0 + self.step * (i + 0.5)

    def left(self, i):
        return self.center(i) - self.width / 2


# ------------------------------------------------------------------ svg writer
def _num(v):
    if isinstance(v, float):
        return ('{:.2f}'.format(v)).rstrip('0').rstrip('.')
    return str(v)


def _attrs(a):
    return ' '.join('{}="{}"'.format(k.rstrip('_').replace('_', '-'), _num(v)) for k, v in a.items() if v is not None)


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


class Svg:
    def __init__(self, w, h, theme):
        self.w, self.h, self.t, self.o = w, h, theme, []

    def el(self, tag, **a):
        self.o.append('<{} {}/>'.format(tag, _attrs(a)))

    def text(self, x, y, s, size=11, fill=None, weight=None, mono=False, anchor=None, ls=None):
        self.o.append('<text {}>{}</text>'.format(_attrs(dict(
            x=x, y=y, font_size=size, fill=fill or self.t['text'], font_weight=weight,
            font_family=MONO if mono else SANS, text_anchor=anchor, letter_spacing=ls)), esc(s)))

    def rect(self, x, y, w, h, fill, rx=0, **a):
        if w <= 0 or h <= 0:
            return
        self.el('rect', x=x, y=y, width=w, height=h, rx=min(rx, w / 2, h / 2), fill=fill, **a)

    def hline(self, x0, x1, y, stroke, dash=None):
        y = math.floor(y) + 0.5  # crisp 1px
        self.el('line', x1=x0, y1=y, x2=x1, y2=y, stroke=stroke, stroke_dasharray=dash)

    def vline(self, x, y0, y1, stroke):
        x = math.floor(x) + 0.5
        self.el('line', x1=x, y1=y0, x2=x, y2=y1, stroke=stroke)

    def render(self, title):
        return ('<svg xmlns="http://www.w3.org/2000/svg" width="{0}" height="{1}" viewBox="0 0 {0} {1}" '
                'role="img" aria-label="{2}">\n{3}\n</svg>\n').format(self.w, self.h, esc(title), '\n'.join(self.o))


# ------------------------------------------------------------------ marks
def y_axis(s, ticks, scale, x0, x1, fmt=fmt_compact, label_x=None):
    """Horizontal gridlines at each tick, labels right-aligned left of the plot."""
    t = s.t
    for v in ticks:
        y = scale(v)
        s.hline(x0, x1, y, t['grid'] if v else t['axis'])
        s.text(label_x if label_x is not None else x0 - 8, y + 3.5, fmt(v), 9.5, t['muted'], mono=True, anchor='end')


def columns(s, band, values, scale, color, base_y, labels=None, label_fmt=fmt_compact, label_color=None, highlight=None):
    """Vertical bars from base_y; optional value label above each bar."""
    t = s.t
    for i, v in enumerate(values):
        if v is None:
            continue
        top = scale(v)
        c = color(i) if callable(color) else color
        if highlight is not None and i not in highlight:
            c = t['bar_dim']
        s.rect(band.left(i), top, band.width, base_y - top, c, rx=2)
        if labels and v and (labels is True or i in labels):
            s.text(band.center(i), top - 5, label_fmt(v), 9.5, label_color or t['text2'], mono=True, anchor='middle')


def hbar_rows(s, rows, x_label, x_bar0, x_bar1, x_value, y0, row_h, color, max_value=None, value_fmt=fmt_int,
              share=None, bar_h=8, label_mono=False):
    """Label | bar | value rows, all baselines on the same grid."""
    t = s.t
    mx = max_value or max([v for _, v in rows] + [1])
    for i, (label, v) in enumerate(rows):
        cy = y0 + i * row_h
        s.text(x_label, cy + 4, label, 11, t['text2'], mono=label_mono)
        s.rect(x_bar0, cy - bar_h / 2, x_bar1 - x_bar0, bar_h, t['track'], rx=2)
        s.rect(x_bar0, cy - bar_h / 2, (x_bar1 - x_bar0) * (v / mx if mx else 0), bar_h, color(i) if callable(color) else color, rx=2)
        s.text(x_value, cy + 4, value_fmt(v), 11, t['text'], mono=True, anchor='end')
        if share is not None:
            s.text(share[0], cy + 4, share[1](v), 10, t['muted'], mono=True, anchor='end')
