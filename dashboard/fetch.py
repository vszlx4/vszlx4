"""
Collects everything the dashboard needs from the GitHub API into a data directory (see metrics.py for the layout).

Commits come from GraphQL (the author date keeps its original timezone offset); the file list of each commit comes
from REST and is cached by commit id in `files_cache`, so after the first run only new commits cost a request.
Standard library only.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = 'https://api.github.com'
TEST_PATH = re.compile(r'(^|/)(tests?|e2e|__tests__)/|(_test|\.test|\.spec)\.\w+$|(^|/)test_\w+\.py$')
FILES_PER_RUN = 1500  # REST budget for uncached commits in one run; the rest are fetched next run

HISTORY = '''
query($owner: String!, $name: String!, $id: ID!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef {
      target {
        ... on Commit {
          history(first: 100, after: $cursor, author: {id: $id}) {
            pageInfo { hasNextPage endCursor }
            nodes { oid messageHeadline additions deletions author { date } parents { totalCount } }
          }
        }
      }
    }
  }
}'''


def redact(url):
    """Logs of a public repository are public: never print which repository a request was for."""
    return re.sub(r'/repos/[^/?]+/[^/?]+', '/repos/<repo>', url)


class GitHub:
    def __init__(self, token):
        self.token = token
        self.calls = 0

    def _request(self, url, body=None):
        headers = {'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'profile-dashboard'}
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(5):
            self.calls += 1
            req = urllib.request.Request(url, data=data, headers=headers, method='POST' if data else 'GET')
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.loads(resp.read() or b'null'), resp.headers
            except urllib.error.HTTPError as e:
                retry = e.code in (502, 503, 504) or (e.code in (403, 429) and (e.headers.get('Retry-After') or
                                                                             e.headers.get('X-RateLimit-Remaining') == '0'))
                if e.code == 409:  # empty repository
                    return None, e.headers
                if not retry or attempt == 4:
                    raise RuntimeError('{} {} for {}'.format(e.code, e.reason, redact(url))) from None
                wait = int(e.headers.get('Retry-After') or 0) or min(60, 2 ** attempt * 5)
                print('  retrying {} in {}s ({})'.format(redact(url), wait, e.code), flush=True)
                time.sleep(wait)
            except urllib.error.URLError:
                if attempt == 4:
                    raise
                time.sleep(2 ** attempt * 3)

    def rest(self, path):
        return self._request(path if path.startswith('http') else API + path)[0]

    def pages(self, path):
        url, out = API + path, []
        while url:
            data, headers = self._request(url)
            out += data or []
            m = re.search(r'<([^>]+)>;\s*rel="next"', headers.get('Link') or '')
            url = m.group(1) if m else None
        return out

    def graphql(self, query, variables):
        data, _ = self._request(API + '/graphql', {'query': query, 'variables': variables})
        if data.get('errors'):
            raise RuntimeError('GraphQL: ' + ', '.join(sorted({e.get('type', 'error') for e in data['errors']})))  # messages can name repos
        return data['data']


def _dump(path, obj):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f)


def collect(token, login, out_dir, files_cache):
    os.makedirs(out_dir, exist_ok=True)
    gh = GitHub(token)
    try:
        with open(files_cache, encoding='utf-8') as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {}

    user_id = gh.graphql('query($l: String!) { user(login: $l) { id } }', {'l': login})['user']['id']
    repos = [r for r in gh.pages('/user/repos?affiliation=owner,collaborator,organization_member&per_page=100') if not r.get('fork')]
    _dump(os.path.join(out_dir, 'repos.json'), repos)
    print('{} repositories'.format(len(repos)), flush=True)

    commits, budget = [], FILES_PER_RUN
    for r in repos:
        owner, name = r['full_name'].split('/', 1)
        cursor, n = None, 0
        while True:
            try:
                data = gh.graphql(HISTORY, {'owner': owner, 'name': name, 'id': user_id, 'cursor': cursor})
            except RuntimeError as e:
                print('  skipped a repository: {}'.format(e), flush=True)
                break
            ref = (data.get('repository') or {}).get('defaultBranchRef')
            if not ref:
                break
            hist = ref['target']['history']
            for c in hist['nodes']:
                if c['parents']['totalCount'] > 1:
                    continue  # merge commits repeat work already counted
                oid = c['oid']
                if oid not in cache and budget > 0:
                    try:
                        detail = gh.rest('/repos/{}/commits/{}'.format(r['full_name'], oid)) or {}
                    except RuntimeError as e:
                        print('  commit details unavailable: {}'.format(e), flush=True)
                        detail = {}
                    cache[oid] = [[f['filename'], f.get('additions', 0), f.get('deletions', 0)] for f in detail.get('files', [])]
                    budget -= 1
                commits.append(dict(repo=name, sha=oid, date=c['author']['date'], subject=c['messageHeadline'], signed=False,
                                    additions=c['additions'], deletions=c['deletions'], files=cache.get(oid, [])))
                n += 1
            if not hist['pageInfo']['hasNextPage']:
                break
            cursor = hist['pageInfo']['endCursor']
        if n:
            print('  {}: {} commits'.format('private' if r.get('private') else r['full_name'], n), flush=True)
    _dump(os.path.join(out_dir, 'commits.json'), commits)
    os.makedirs(os.path.dirname(files_cache) or '.', exist_ok=True)
    _dump(files_cache, cache)
    if budget <= 0:
        print('File-list budget reached; remaining commits are fetched on the next run.', flush=True)

    # Actions runs, issues/PRs and test files for owned public repositories with commits
    mine = {c['repo'] for c in commits}
    tests = {}
    for r in repos:
        if r.get('private') or r['owner']['login'].lower() != login.lower() or r['name'] not in mine:
            continue
        full, name = r['full_name'], r['name']
        _dump(os.path.join(out_dir, 'runs_{}.json'.format(name)), gh.rest('/repos/{}/actions/runs?per_page=100'.format(full)) or {})
        _dump(os.path.join(out_dir, 'iss_{}.json'.format(name)), gh.rest('/repos/{}/issues?state=all&per_page=100'.format(full)) or [])
        tree = gh.rest('/repos/{}/git/trees/{}?recursive=1'.format(full, urllib.parse.quote(r.get('default_branch') or 'main'))) or {}
        tests[name] = sum(1 for t in tree.get('tree', []) if t.get('type') == 'blob' and TEST_PATH.search(t['path']))
    _dump(os.path.join(out_dir, 'tests.json'), tests)
    print('{} commits, {} API calls'.format(len(commits), gh.calls), flush=True)


if __name__ == '__main__':
    collect(os.environ['ACCESS_TOKEN'], os.environ['USER_NAME'], sys.argv[1], sys.argv[2])
