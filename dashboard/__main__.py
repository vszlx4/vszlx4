"""
python -m dashboard   (env: ACCESS_TOKEN, USER_NAME)

Fetches GitHub data into .cache/data, computes the metrics and writes dashboard-dark.svg and dashboard-light.svg.
If anything fails, the previous images are left untouched, so a bad run never publishes a broken one. When only the
"Last updated" time would change, nothing is written, so the hourly schedule commits only when the data changes.
"""
import os
import re
import sys

from . import fetch, metrics, render

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, '.cache', 'data')
FILES_CACHE = os.path.join(ROOT, '.cache', 'commit-files.json')
OUTPUT = os.path.join(ROOT, 'dashboard-{}.svg')
STAMP = re.compile(r'(class="stamp">)[^<]*(</text>)')


def _read(path):
    try:
        with open(path, encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return None


def main():
    token, login = os.environ.get('ACCESS_TOKEN'), os.environ.get('USER_NAME')
    if not token or not login:
        sys.exit('ACCESS_TOKEN and USER_NAME must be set.')
    fetch.collect(token, login, DATA, FILES_CACHE)
    data = metrics.build(DATA)
    svgs = {theme: render.render(data, theme) for theme in render.THEMES}  # render both before writing either
    if all(STAMP.sub(r'\1\2', svg) == STAMP.sub(r'\1\2', _read(OUTPUT.format(theme)) or '') for theme, svg in svgs.items()):
        print('No data changes; images left as they are.')
        return
    for theme, svg in svgs.items():
        path = OUTPUT.format(theme)
        with open(path + '.tmp', 'w', encoding='utf-8') as f:
            f.write(svg)
        os.replace(path + '.tmp', path)
        print('wrote {} ({:,} bytes)'.format(os.path.basename(path), len(svg.encode())))


if __name__ == '__main__':
    main()
