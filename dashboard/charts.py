"""
Minimal SVG helpers: number formats, nice axis ticks, a linear scale and a small SVG writer.
Every chart draws into an explicit plot box, so alignment comes from the layout grid, never from guesses.
"""
import math



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
