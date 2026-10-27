"""
python -m dashboard   (env: ACCESS_TOKEN, USER_NAME)

Fetches GitHub data into .cache/data, computes the metrics and writes dashboard.svg. If anything fails, the
previous dashboard.svg is left untouched, so a bad run never publishes a broken image.
"""
import os
import sys

from . import fetch, metrics, render

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, '.cache', 'data')
FILES_CACHE = os.path.join(ROOT, '.cache', 'commit-files.json')
OUTPUT = os.path.join(ROOT, 'dashboard.svg')


def main():
    token, login = os.environ.get('ACCESS_TOKEN'), os.environ.get('USER_NAME')
    if not token or not login:
        sys.exit('ACCESS_TOKEN and USER_NAME must be set.')
    fetch.collect(token, login, DATA, FILES_CACHE)
    svg = render.render(metrics.build(DATA))
    tmp = OUTPUT + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(svg)
    os.replace(tmp, OUTPUT)
    print('wrote dashboard.svg ({:,} bytes)'.format(len(svg.encode())))


if __name__ == '__main__':
    main()
