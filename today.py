# Adapted from Andrew Grant's (Andrew6rant) GitHub profile stats script.
# Original repository: https://github.com/Andrew6rant/Andrew6rant

import datetime
from dateutil import relativedelta
import requests
import os
from lxml import etree
import time
import hashlib
import math

# Fine-grained personal access token with All Repositories access:
# Account permissions: read:Followers, read:Starring, read:Watching
# Repository permissions: read:Commit statuses, read:Contents, read:Issues, read:Metadata, read:Pull Requests
# Issues and pull requests permissions not needed at the moment, but may be used in the future
HEADERS = {'authorization': 'token '+ os.environ['ACCESS_TOKEN']}
USER_NAME = os.environ['USER_NAME']
QUERY_COUNT = {'user_getter': 0, 'follower_getter': 0, 'graph_repos_stars': 0, 'recursive_loc': 0, 'graph_commits': 0, 'loc_query': 0, 'graph_languages': 0, 'daily_activity': 0}


def account_uptime(created_at):
    """
    Returns the length of time since this GitHub account was created
    e.g. 'XX years, XX months, XX days'
    """
    created = datetime.datetime.strptime(created_at, '%Y-%m-%dT%H:%M:%SZ')
    diff = relativedelta.relativedelta(datetime.datetime.today(), created)
    return '{} {}, {} {}, {} {}'.format(
        diff.years, 'year' + format_plural(diff.years),
        diff.months, 'month' + format_plural(diff.months),
        diff.days, 'day' + format_plural(diff.days))


def format_plural(unit):
    """
    Returns a properly formatted number
    e.g.
    'day' + format_plural(diff.days) == 5
    >>> '5 days'
    'day' + format_plural(diff.days) == 1
    >>> '1 day'
    """
    return 's' if unit != 1 else ''


def relative_time(iso_date):
    """
    Returns a single-unit relative time string for a timestamp, e.g. '10 days ago', '1 month ago', '2 years ago'
    """
    then = datetime.datetime.strptime(iso_date, '%Y-%m-%dT%H:%M:%SZ')
    diff = relativedelta.relativedelta(datetime.datetime.today(), then)
    for value, unit in ((diff.years, 'year'), (diff.months, 'month'), (diff.days, 'day')):
        if value > 0:
            return '{} {}{} ago'.format(value, unit, format_plural(value))
    return 'today'


def simple_request(func_name, query, variables):
    """
    Returns a request, or raises an Exception if the response does not succeed.
    """
    request = requests.post('https://api.github.com/graphql', json={'query': query, 'variables':variables}, headers=HEADERS)
    if request.status_code == 200:
        return request
    raise Exception(func_name, ' has failed with a', request.status_code, request.text, QUERY_COUNT)


def graph_commits(start_date, end_date):
    """
    Uses GitHub's GraphQL v4 API to return my total commit count
    """
    query_count('graph_commits')
    query = '''
    query($start_date: DateTime!, $end_date: DateTime!, $login: String!) {
        user(login: $login) {
            contributionsCollection(from: $start_date, to: $end_date) {
                contributionCalendar {
                    totalContributions
                }
            }
        }
    }'''
    variables = {'start_date': start_date,'end_date': end_date, 'login': USER_NAME}
    request = simple_request(graph_commits.__name__, query, variables)
    return int(request.json()['data']['user']['contributionsCollection']['contributionCalendar']['totalContributions'])


def daily_activity(days=30):
    """
    Returns [(date_str, contribution_count), ...] for the last `days` days, oldest first, today last
    """
    query_count('daily_activity')
    end = datetime.datetime.now(datetime.timezone.utc)
    start = end - datetime.timedelta(days=days - 1)
    query = '''
    query($login: String!, $start_date: DateTime!, $end_date: DateTime!) {
        user(login: $login) {
            contributionsCollection(from: $start_date, to: $end_date) {
                contributionCalendar {
                    weeks {
                        contributionDays {
                            date
                            contributionCount
                        }
                    }
                }
            }
        }
    }'''
    variables = {
        'login': USER_NAME,
        'start_date': start.strftime('%Y-%m-%dT00:00:00Z'),
        'end_date': end.strftime('%Y-%m-%dT23:59:59Z'),
    }
    request = simple_request(daily_activity.__name__, query, variables)
    weeks = request.json()['data']['user']['contributionsCollection']['contributionCalendar']['weeks']
    cutoff = start.strftime('%Y-%m-%d')
    result = [(d['date'], d['contributionCount']) for week in weeks for d in week['contributionDays'] if d['date'] >= cutoff]
    result.sort(key=lambda d: d[0])
    return result[-days:]


def graph_repos_stars(count_type, owner_affiliation, cursor=None, add_loc=0, del_loc=0):
    """
    Uses GitHub's GraphQL v4 API to return my total repository, star, or lines of code count.
    """
    query_count('graph_repos_stars')
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
                totalCount
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            stargazers {
                                totalCount
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    request = simple_request(graph_repos_stars.__name__, query, variables)
    if request.status_code == 200:
        if count_type == 'repos':
            return request.json()['data']['user']['repositories']['totalCount']
        elif count_type == 'stars':
            return stars_counter(request.json()['data']['user']['repositories']['edges'])


def graph_languages(owner_affiliation, cursor=None, edges=[]):
    """
    Uses GitHub's GraphQL v4 API to fetch each repository's language breakdown (bytes per language)
    """
    query_count('graph_languages')
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 60, after: $cursor, ownerAffiliations: $owner_affiliation) {
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
                                edges {
                                    size
                                    node {
                                        name
                                        color
                                    }
                                }
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    request = simple_request(graph_languages.__name__, query, variables)
    repositories = request.json()['data']['user']['repositories']
    edges = edges + repositories['edges']
    if repositories['pageInfo']['hasNextPage']:
        return graph_languages(owner_affiliation, repositories['pageInfo']['endCursor'], edges)
    return edges


def aggregate_languages(edges, top_n=6):
    """
    Sums language byte totals across every repository and returns the top_n by size,
    each as (name, color, byte_size, fraction_of_all_bytes_used)
    """
    totals = {}
    colors = {}
    for edge in edges:
        if edge['node'] is None:  # GitHub can return a null node for a repo edge that's become inaccessible
            continue
        for lang_edge in edge['node']['languages']['edges']:
            name = lang_edge['node']['name']
            totals[name] = totals.get(name, 0) + lang_edge['size']
            colors.setdefault(name, lang_edge['node']['color'] or '#858585')
    grand_total = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:top_n]
    return [(name, colors[name], size, size / grand_total) for name, size in ranked]


def repo_language_map(edges):
    """
    Maps nameWithOwner -> [(language_name, color, fraction_of_that_repo's_bytes), ...] for the same
    edges aggregate_languages() consumes, so each repo's own composition can be drawn as a bar.
    """
    by_repo = {}
    for edge in edges:
        if edge['node'] is None:
            continue
        lang_edges = edge['node']['languages']['edges']
        total = sum(le['size'] for le in lang_edges) or 1
        by_repo[edge['node']['nameWithOwner']] = [
            (le['node']['name'], le['node']['color'] or '#858585', le['size'] / total) for le in lang_edges
        ]
    return by_repo


def latest_repos(edges, cache_data, top_n=6):
    """
    Repositories I've committed to, newest pushedAt first, each as (name, my_commits, pushedAt).
    ISO 8601 timestamps sort correctly as plain strings, so no parsing is needed here.
    Excludes this profile-readme repo itself: every run pushes an "Updated README" commit to it,
    which would otherwise keep bumping its own pushedAt and pin it at the top forever as "today".
    """
    self_repo = USER_NAME + '/' + USER_NAME
    ranked = []
    for index, edge in enumerate(edges):
        if edge['node']['nameWithOwner'] == self_repo:
            continue
        my_commits = int(cache_data[index].split()[2])
        if my_commits > 0:
            ranked.append((edge['node']['nameWithOwner'], my_commits, edge['node']['pushedAt']))
    ranked.sort(key=lambda item: item[2], reverse=True)
    return ranked[:top_n]


def last_update_timestamp():
    """
    Returns the current time formatted as 'YYYY/MM/DD HH:MM:SS GMT+3' (Saudi Arabia time)
    """
    now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)
    return now.strftime('%Y/%m/%d %H:%M:%S GMT+3')


def recursive_loc(owner, repo_name, data, cache_comment, addition_total=0, deletion_total=0, my_commits=0, cursor=None):
    """
    Uses GitHub's GraphQL v4 API and cursor pagination to fetch 100 commits from a repository at a time
    """
    query_count('recursive_loc')
    query = '''
    query ($repo_name: String!, $owner: String!, $cursor: String) {
        repository(name: $repo_name, owner: $owner) {
            defaultBranchRef {
                target {
                    ... on Commit {
                        history(first: 100, after: $cursor) {
                            totalCount
                            edges {
                                node {
                                    ... on Commit {
                                        committedDate
                                    }
                                    author {
                                        user {
                                            id
                                        }
                                    }
                                    deletions
                                    additions
                                }
                            }
                            pageInfo {
                                endCursor
                                hasNextPage
                            }
                        }
                    }
                }
            }
        }
    }'''
    variables = {'repo_name': repo_name, 'owner': owner, 'cursor': cursor}
    request = requests.post('https://api.github.com/graphql', json={'query': query, 'variables':variables}, headers=HEADERS) # I cannot use simple_request(), because I want to save the file before raising Exception
    if request.status_code == 200:
        if request.json()['data']['repository']['defaultBranchRef'] != None: # Only count commits if repo isn't empty
            return loc_counter_one_repo(owner, repo_name, data, cache_comment, request.json()['data']['repository']['defaultBranchRef']['target']['history'], addition_total, deletion_total, my_commits)
        else: return 0
    force_close_file(data, cache_comment) # saves what is currently in the file before this program crashes
    if request.status_code == 403:
        raise Exception('Too many requests in a short amount of time!\nYou\'ve hit the non-documented anti-abuse limit!')
    raise Exception('recursive_loc() has failed with a', request.status_code, request.text, QUERY_COUNT)


def loc_counter_one_repo(owner, repo_name, data, cache_comment, history, addition_total, deletion_total, my_commits):
    """
    Recursively call recursive_loc (since GraphQL can only search 100 commits at a time) 
    only adds the LOC value of commits authored by me
    """
    for node in history['edges']:
        if node['node']['author']['user'] == OWNER_ID:
            my_commits += 1
            addition_total += node['node']['additions']
            deletion_total += node['node']['deletions']

    if history['edges'] == [] or not history['pageInfo']['hasNextPage']:
        return addition_total, deletion_total, my_commits
    else: return recursive_loc(owner, repo_name, data, cache_comment, addition_total, deletion_total, my_commits, history['pageInfo']['endCursor'])


def loc_query(owner_affiliation, comment_size=0, force_cache=False, cursor=None, edges=[]):
    """
    Uses GitHub's GraphQL v4 API to query all the repositories I have access to (with respect to owner_affiliation)
    Queries 60 repos at a time, because larger queries give a 502 timeout error and smaller queries send too many
    requests and also give a 502 error.
    Returns the total number of lines of code in all repositories
    """
    query_count('loc_query')
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 60, after: $cursor, ownerAffiliations: $owner_affiliation) {
            edges {
                node {
                    ... on Repository {
                        nameWithOwner
                        pushedAt
                        defaultBranchRef {
                            target {
                                ... on Commit {
                                    history {
                                        totalCount
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    request = simple_request(loc_query.__name__, query, variables)
    if request.json()['data']['user']['repositories']['pageInfo']['hasNextPage']:   # If repository data has another page
        edges += request.json()['data']['user']['repositories']['edges']            # Add on to the LoC count
        return loc_query(owner_affiliation, comment_size, force_cache, request.json()['data']['user']['repositories']['pageInfo']['endCursor'], edges)
    else:
        all_edges = edges + request.json()['data']['user']['repositories']['edges']
        # GitHub can return a null node for a repo edge that's become inaccessible (deleted, transferred, etc.)
        all_edges = [edge for edge in all_edges if edge['node'] is not None]
        return cache_builder(all_edges, comment_size, force_cache)


def cache_builder(edges, comment_size, force_cache, loc_add=0, loc_del=0):
    """
    Checks each repository in edges to see if it has been updated since the last time it was cached
    If it has, run recursive_loc on that repository to update the LOC count
    """
    cached = True # Assume all repositories are cached
    filename = 'cache/'+hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest()+'.txt' # Create a unique filename for each user
    try:
        with open(filename, 'r') as f:
            data = f.readlines()
    except FileNotFoundError: # If the cache file doesn't exist, create it
        data = []
        if comment_size > 0:
            for _ in range(comment_size): data.append('This line is a comment block. Write whatever you want here.\n')
        with open(filename, 'w') as f:
            f.writelines(data)

    if len(data)-comment_size != len(edges) or force_cache: # If the number of repos has changed, or force_cache is True
        cached = False
        flush_cache(edges, filename, comment_size)
        with open(filename, 'r') as f:
            data = f.readlines()

    cache_comment = data[:comment_size] # save the comment block
    data = data[comment_size:] # remove those lines
    for index in range(len(edges)):
        repo_hash, commit_count, *__ = data[index].split()
        if repo_hash == hashlib.sha256(edges[index]['node']['nameWithOwner'].encode('utf-8')).hexdigest():
            try:
                if int(commit_count) != edges[index]['node']['defaultBranchRef']['target']['history']['totalCount']:
                    # if commit count has changed, update loc for that repo
                    owner, repo_name = edges[index]['node']['nameWithOwner'].split('/')
                    loc = recursive_loc(owner, repo_name, data, cache_comment)
                    data[index] = repo_hash + ' ' + str(edges[index]['node']['defaultBranchRef']['target']['history']['totalCount']) + ' ' + str(loc[2]) + ' ' + str(loc[0]) + ' ' + str(loc[1]) + '\n'
            except TypeError: # If the repo is empty
                data[index] = repo_hash + ' 0 0 0 0\n'
    with open(filename, 'w') as f:
        f.writelines(cache_comment)
        f.writelines(data)
    for line in data:
        loc = line.split()
        loc_add += int(loc[3])
        loc_del += int(loc[4])
    return [loc_add, loc_del, loc_add - loc_del, cached, edges, data]


def flush_cache(edges, filename, comment_size):
    """
    Wipes the cache file
    This is called when the number of repositories changes or when the file is first created
    """
    with open(filename, 'r') as f:
        data = []
        if comment_size > 0:
            data = f.readlines()[:comment_size] # only save the comment
    with open(filename, 'w') as f:
        f.writelines(data)
        for node in edges:
            f.write(hashlib.sha256(node['node']['nameWithOwner'].encode('utf-8')).hexdigest() + ' 0 0 0 0\n')


def force_close_file(data, cache_comment):
    """
    Forces the file to close, preserving whatever data was written to it
    This is needed because if this function is called, the program would've crashed before the file is properly saved and closed
    """
    filename = 'cache/'+hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest()+'.txt'
    with open(filename, 'w') as f:
        f.writelines(cache_comment)
        f.writelines(data)
    print('There was an error while writing to the cache file. The file,', filename, 'has had the partial data saved and closed.')


def stars_counter(data):
    """
    Count total stars in repositories owned by me
    """
    total_stars = 0
    for node in data:
        if node['node'] is not None:  # GitHub can return a null node for a repo edge that's become inaccessible
            total_stars += node['node']['stargazers']['totalCount']
    return total_stars


def build_left_panel(root, repos, langs, repo_langs):
    """
    Renders the top-repositories bar list and the top-languages donut+legend into the <g id="left_panel">
    placeholder, fully replacing whatever it held from the previous run. Section headers sit on the same
    row as "ahmed@mughram" would repeat on (grid-aligned, 34px cadence) so the whole card reads as one grid.
    """
    container = root.find(".//*[@id='left_panel']")
    if container is None:
        return
    for child in list(container):
        container.remove(child)

    PANEL_X = 20
    PANEL_W = 355
    ROW_H = 34
    REPO_BAR_H = 3  # thin -- the language mix is the point, not the bar's bulk
    BAR_GAP = 10  # distance from a row's text baseline down to the top of its bar
    NAME_LIMIT = 34

    def add_text(x, y, text, cls, anchor=None):
        el = etree.SubElement(container, 'text')
        el.set('x', str(x))
        el.set('y', str(y))
        el.set('class', cls)
        if anchor:
            el.set('text-anchor', anchor)
        el.text = text

    def add_language_bar(x, y, w, h, segments):
        """
        A fully-filled, rounded bar split into one segment per language, sized by that language's
        share of the repo -- same idea as the languages donut, just laid out as a strip. Segments are
        drawn into a clip-pathed group so only the composite bar's outer edge is rounded, not each piece.
        """
        clip_id = 'lb-clip-{}'.format(int(y))
        clip = etree.SubElement(container, 'clipPath', {'id': clip_id})
        etree.SubElement(clip, 'rect', {'x': str(x), 'y': str(y), 'width': str(w), 'height': str(h), 'rx': str(h / 2)})
        group = etree.SubElement(container, 'g', {'clip-path': 'url(#{})'.format(clip_id)})
        if not segments:
            etree.SubElement(group, 'rect', {'x': str(x), 'y': str(y), 'width': str(w), 'height': str(h), 'class': 'track'})
            return
        offset = 0.0
        last = len(segments) - 1
        for i, (name, color, fraction) in enumerate(segments):
            seg_w = (w - offset) if i == last else w * fraction
            seg_w = max(0.0, seg_w)
            etree.SubElement(group, 'rect', {
                'x': '{:.2f}'.format(x + offset), 'y': str(y), 'width': '{:.2f}'.format(seg_w), 'height': str(h),
                'fill': color,
            })
            offset += seg_w

    def truncate(name, limit=NAME_LIMIT):
        return name if len(name) <= limit else name[:limit - 1] + '…'

    def strip_owner(name):
        prefix = USER_NAME + '/'
        return name[len(prefix):] if name.startswith(prefix) else name

    COUNT_COL_W = 45  # reserved width for the right-aligned commit count

    y = 30
    add_text(PANEL_X, y, '- Latest Repositories', 'panelTitle')
    if repos:
        for name, commits, pushed_at in repos:
            y += ROW_H
            add_text(PANEL_X, y, truncate(strip_owner(name)), 'panelLabel')
            add_text(PANEL_X + PANEL_W - COUNT_COL_W, y, relative_time(pushed_at), 'panelMuted', anchor='end')
            add_text(PANEL_X + PANEL_W, y, '{:,}'.format(commits), 'cc', anchor='end')
            add_language_bar(PANEL_X, y + BAR_GAP, PANEL_W, REPO_BAR_H, repo_langs.get(name, []))
    else:
        y += ROW_H
        add_text(PANEL_X, y, 'No repositories yet', 'panelValue')

    y += ROW_H + 20
    lang_title_y = y
    add_text(PANEL_X, lang_title_y, '- Languages', 'panelTitle')

    if langs:
        LEGEND_RIGHT = 190
        SWATCH = 8
        legend_top = lang_title_y + ROW_H
        legend_bottom = legend_top + (len(langs) - 1) * ROW_H
        for i, (name, color, size, fraction) in enumerate(langs):
            row_y = legend_top + i * ROW_H
            etree.SubElement(container, 'rect', {
                'x': str(PANEL_X), 'y': str(row_y - SWATCH), 'width': str(SWATCH), 'height': str(SWATCH),
                'rx': '2', 'fill': color,
            })
            add_text(PANEL_X + SWATCH + 8, row_y, truncate(name, 18), 'panelLabel')
            add_text(LEGEND_RIGHT, row_y, '{:.1f}%'.format(fraction * 100), 'panelValue', anchor='end')

        cx = 285
        cy = round((legend_top + legend_bottom) / 2) - 6
        r = 68
        stroke_w = 26
        circumference = 2 * math.pi * r
        offset = 0.0
        for name, color, size, fraction in langs:
            arc_len = fraction * circumference
            etree.SubElement(container, 'circle', {
                'cx': str(cx), 'cy': str(cy), 'r': str(r), 'fill': 'none',
                'stroke': color, 'stroke-width': str(stroke_w),
                'stroke-dasharray': '{:.2f} {:.2f}'.format(arc_len, circumference - arc_len),
                'stroke-dashoffset': '{:.2f}'.format(-offset),
                'transform': 'rotate(-90 {} {})'.format(cx, cy),
            })
            offset += arc_len
    else:
        add_text(PANEL_X, lang_title_y + ROW_H, 'No language data yet', 'panelValue')


def smooth_path(points):
    """
    Returns an SVG path 'd' string tracing a smooth Catmull-Rom-to-Bezier spline through points.
    """
    if len(points) < 2:
        return ''
    d = ['M {:.2f} {:.2f}'.format(*points[0])]
    for i in range(len(points) - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[i + 2] if i + 2 < len(points) else p2
        c1x = p1[0] + (p2[0] - p0[0]) / 6
        c1y = p1[1] + (p2[1] - p0[1]) / 6
        c2x = p2[0] - (p3[0] - p1[0]) / 6
        c2y = p2[1] - (p3[1] - p1[1]) / 6
        # clamp the control points' y to the segment's own [p1.y, p2.y] range -- unclamped Catmull-Rom
        # tangents can be pulled by a distant neighbor and overshoot past a local min/max, which visibly
        # draws the line past the data (e.g. dipping below zero right before a spike)
        y_lo, y_hi = (p1[1], p2[1]) if p1[1] <= p2[1] else (p2[1], p1[1])
        c1y = min(max(c1y, y_lo), y_hi)
        c2y = min(max(c2y, y_lo), y_hi)
        d.append('C {:.2f} {:.2f} {:.2f} {:.2f} {:.2f} {:.2f}'.format(c1x, c1y, c2x, c2y, *p2))
    return ' '.join(d)


def build_activity_graph(root, daily_data, prev_daily_data=None):
    """
    Renders a 30-day contribution chart into the <g id="activity_graph"> placeholder: a gradient-filled
    area under a smoothed line, a dashed 30-day-average reference line, a dot at every real data point
    (so the smoothing never obscures where the actual data is), soft-haloed peak/trough markers, a fine
    labeled grid on both axes, and a faded previous-month line rendered behind it all for comparison.
    Reuses the card's own green/red/blue accents (the same ones the repo bars and LOC ++/-- use) rather
    than new colors.

    The box spans the exact same column the key:value rows above and below it use (x=390 to the T=60
    right edge), and the plotted data starts and ends flush with that same left/right edge -- inset only
    by the halo radius of a peak/trough marker, so it never visually clips the box. Top/bottom get a
    larger inset so a peak or trough marker's halo and label always stay inside the box. Every text label
    is drawn last, on top of everything else (with a solid background chip behind floating value labels),
    so the line can never render over a legend, a number, or a date.
    """
    container = root.find(".//*[@id='activity_graph']")
    if container is None:
        return
    for child in list(container):
        container.remove(child)

    CHART_X = 390
    CHART_TOP = 258
    CHART_W = 576  # matches the T=60 column width (60 chars * 9.6px) the rows above/below align to
    CHART_H = 126
    LEGEND_Y = CHART_TOP - 10

    PAD_X = 8  # just enough for a peak/trough halo (r=7) to clear the box edge -- the line otherwise
               # starts and ends flush with the same left/right column the key:value rows above use
    PLOT_X0 = CHART_X + PAD_X
    PLOT_X1 = CHART_X + CHART_W - PAD_X

    PAD_TOP = 25     # room for a peak's halo + label to stay fully inside the box
    PAD_BOTTOM = 14  # room for a trough's halo to clear the box's bottom edge
    PLOT_TOP = CHART_TOP + PAD_TOP
    PLOT_BOTTOM = CHART_TOP + CHART_H - PAD_BOTTOM

    if not daily_data:
        el = etree.SubElement(container, 'text')
        el.set('x', str(CHART_X))
        el.set('y', str(CHART_TOP + 20))
        el.set('class', 'panelValue')
        el.text = 'No activity data yet'
        return

    dates = [d for d, _ in daily_data]
    counts = [c for _, c in daily_data]
    n = len(counts)
    prev_counts = [c for _, c in prev_daily_data] if prev_daily_data else []
    max_v = max(counts + prev_counts) or 1
    avg_v = sum(counts) / n

    def mk_xy(count):
        def xy(i, v):
            x = PLOT_X0 + ((i / (count - 1)) if count > 1 else 0) * (PLOT_X1 - PLOT_X0)
            y = PLOT_BOTTOM - (v / max_v) * (PLOT_BOTTOM - PLOT_TOP)
            return (x, y)
        return xy

    xy = mk_xy(n)

    def chip_label(x, y, text, cls, anchor='middle', font_size=10):
        """A small background-backed label: always legible even if the line passes behind it."""
        w = len(text) * font_size * 0.62 + 6
        if anchor == 'end':
            rx = x - w + 2
        elif anchor == 'start':
            rx = x - 2
        else:
            rx = x - w / 2
        etree.SubElement(container, 'rect', {
            'x': '{:.2f}'.format(rx), 'y': '{:.2f}'.format(y - font_size - 1),
            'width': '{:.2f}'.format(w), 'height': '{:.2f}'.format(font_size + 5),
            'rx': '3', 'class': 'chipBg',
        })
        t = etree.SubElement(container, 'text')
        t.set('x', '{:.2f}'.format(x))
        t.set('y', '{:.2f}'.format(y))
        t.set('class', cls + ' chartLabel')
        t.set('text-anchor', anchor)
        t.text = text

    # legend: a swatch of each line style above the chart, so each one's meaning reads immediately
    etree.SubElement(container, 'line', {
        'x1': str(CHART_X), 'y1': str(LEGEND_Y), 'x2': str(CHART_X + 18), 'y2': str(LEGEND_Y),
        'class': 'lineStroke', 'stroke-width': '2.5', 'stroke-linecap': 'round',
    })
    legend1 = etree.SubElement(container, 'text')
    legend1.set('x', str(CHART_X + 24)); legend1.set('y', str(LEGEND_Y + 3)); legend1.set('class', 'panelMuted')
    legend1.text = 'Daily activity'
    legend2_x = CHART_X + 150
    etree.SubElement(container, 'line', {
        'x1': str(legend2_x), 'y1': str(LEGEND_Y), 'x2': str(legend2_x + 18), 'y2': str(LEGEND_Y),
        'class': 'avgStroke', 'stroke-width': '1.5', 'stroke-dasharray': '5 4',
    })
    legend2 = etree.SubElement(container, 'text')
    legend2.set('x', str(legend2_x + 24)); legend2.set('y', str(LEGEND_Y + 3)); legend2.set('class', 'panelMuted')
    legend2.text = '30-day average'
    if len(prev_counts) >= 2:
        legend3_x = CHART_X + 300
        etree.SubElement(container, 'line', {
            'x1': str(legend3_x), 'y1': str(LEGEND_Y), 'x2': str(legend3_x + 18), 'y2': str(LEGEND_Y),
            'class': 'prevStroke', 'stroke-width': '2', 'stroke-linecap': 'round',
        })
        legend3 = etree.SubElement(container, 'text')
        legend3.set('x', str(legend3_x + 24)); legend3.set('y', str(LEGEND_Y + 3)); legend3.set('class', 'panelMuted')
        legend3.text = 'Previous month activity'

    # soft panel behind the whole chart -- same box the grid and data both sit inside
    etree.SubElement(container, 'rect', {
        'x': str(CHART_X), 'y': str(CHART_TOP), 'width': str(CHART_W), 'height': str(CHART_H),
        'rx': '6', 'class': 'track', 'fill-opacity': '0.35',
    })

    # gradients the area fills fade into, defined once per render
    defs = etree.SubElement(container, 'defs')
    grad = etree.SubElement(defs, 'linearGradient', {'id': 'activityFill', 'x1': '0', 'y1': '0', 'x2': '0', 'y2': '1'})
    etree.SubElement(grad, 'stop', {'offset': '0%', 'class': 'gradStop1'})
    etree.SubElement(grad, 'stop', {'offset': '100%', 'class': 'gradStop2'})
    prev_grad = etree.SubElement(defs, 'linearGradient', {'id': 'prevActivityFill', 'x1': '0', 'y1': '0', 'x2': '0', 'y2': '1'})
    etree.SubElement(prev_grad, 'stop', {'offset': '0%', 'class': 'prevGradStop1'})
    etree.SubElement(prev_grad, 'stop', {'offset': '100%', 'class': 'prevGradStop2'})

    # horizontal grid: 6 evenly spaced lines across the padded plot range -- matches where data actually plots
    GRID_ROWS = 5
    grid_y = []
    for step in range(GRID_ROWS + 1):
        frac = step / GRID_ROWS
        gy = PLOT_BOTTOM - frac * (PLOT_BOTTOM - PLOT_TOP)
        grid_y.append((gy, round(frac * max_v)))
        etree.SubElement(container, 'line', {
            'x1': str(CHART_X), 'y1': '{:.2f}'.format(gy), 'x2': str(CHART_X + CHART_W), 'y2': '{:.2f}'.format(gy),
            'class': 'gridStroke', 'stroke-width': '0.75',
        })

    # vertical grid: every 5 days across the padded plot range -- smaller cells than a weekly grid
    STEP_DAYS = 5
    grid_x = []
    for i in range(0, n, STEP_DAYS):
        gx, _ = xy(i, 0)
        grid_x.append((gx, dates[i][5:].replace('-', '/')))
        etree.SubElement(container, 'line', {
            'x1': '{:.2f}'.format(gx), 'y1': str(CHART_TOP), 'x2': '{:.2f}'.format(gx), 'y2': str(CHART_TOP + CHART_H),
            'class': 'gridStroke', 'stroke-width': '0.75',
        })

    # previous month's activity, faded and drawn first so it always sits behind the current month --
    # regardless of which of the two reaches higher on the (shared) scale
    if len(prev_counts) >= 2:
        prev_xy = mk_xy(len(prev_counts))
        prev_points = [prev_xy(i, v) for i, v in enumerate(prev_counts)]
        prev_line_d = smooth_path(prev_points)
        prev_area = etree.SubElement(container, 'path')
        prev_area.set('d', '{} L {:.2f} {:.2f} L {:.2f} {:.2f} Z'.format(
            prev_line_d, prev_points[-1][0], PLOT_BOTTOM, prev_points[0][0], PLOT_BOTTOM))
        prev_area.set('fill', 'url(#prevActivityFill)')
        prev_area.set('stroke', 'none')
        prev_path = etree.SubElement(container, 'path')
        prev_path.set('d', prev_line_d)
        prev_path.set('class', 'prevStroke')
        prev_path.set('stroke-width', '1.75')
        prev_path.set('stroke-linecap', 'round')

    points = [xy(i, v) for i, v in enumerate(counts)]
    line_d = smooth_path(points)

    # gradient-filled area under the smoothed line
    area = etree.SubElement(container, 'path')
    area.set('d', '{} L {:.2f} {:.2f} L {:.2f} {:.2f} Z'.format(
        line_d, points[-1][0], PLOT_BOTTOM, points[0][0], PLOT_BOTTOM))
    area.set('fill', 'url(#activityFill)')
    area.set('stroke', 'none')

    # dashed reference line for the 30-day average, so any given day reads as above/below trend
    avg_y = xy(0, avg_v)[1]
    etree.SubElement(container, 'line', {
        'x1': str(CHART_X), 'y1': '{:.2f}'.format(avg_y), 'x2': str(CHART_X + CHART_W), 'y2': '{:.2f}'.format(avg_y),
        'class': 'avgStroke', 'stroke-width': '1.5', 'stroke-dasharray': '5 4',
    })

    # the smoothed activity line itself, drawn over the fill and average line
    path = etree.SubElement(container, 'path')
    path.set('d', line_d)
    path.set('class', 'lineStroke')
    path.set('stroke-width', '2.25')
    path.set('stroke-linecap', 'round')

    # a small dot at every real day, so the eye can always find the actual data under the smoothing
    for px, py in points:
        etree.SubElement(container, 'circle', {'cx': '{:.2f}'.format(px), 'cy': '{:.2f}'.format(py), 'r': '1.6', 'class': 'addColor'})

    # highest/lowest days: a soft halo behind a solid dot; their value label is added below with the rest
    peak_i = max(range(n), key=lambda i: counts[i])
    trough_i = min(range(n), key=lambda i: counts[i])
    for i, cls in ((peak_i, 'addColor'), (trough_i, 'delColor')):
        px, py = points[i]
        etree.SubElement(container, 'circle', {'cx': '{:.2f}'.format(px), 'cy': '{:.2f}'.format(py), 'r': '7', 'class': cls, 'fill-opacity': '0.22'})
        etree.SubElement(container, 'circle', {'cx': '{:.2f}'.format(px), 'cy': '{:.2f}'.format(py), 'r': '3.5', 'class': cls})

    # every text label is drawn last so nothing -- the line, the fill, the dots -- can ever render over it
    for gy, value in grid_y:
        label = etree.SubElement(container, 'text')
        label.set('x', str(CHART_X + 4))
        label.set('y', '{:.2f}'.format(gy - 2))
        label.set('class', 'panelMuted chartLabel')
        label.text = str(value)

    for gx, text in grid_x:
        label = etree.SubElement(container, 'text')
        label.set('x', '{:.2f}'.format(gx))
        label.set('y', str(CHART_TOP + CHART_H + 16))
        label.set('class', 'panelMuted chartLabel')
        label.set('text-anchor', 'middle')
        label.text = text
    end_label = etree.SubElement(container, 'text')
    end_label.set('x', str(PLOT_X1))
    end_label.set('y', str(CHART_TOP + CHART_H + 16))
    end_label.set('class', 'panelMuted chartLabel')
    end_label.set('text-anchor', 'end')
    end_label.text = 'Today'

    for i, cls in ((peak_i, 'addColor'), (trough_i, 'delColor')):
        px, py = points[i]
        chip_label(px, py - 12, str(counts[i]), cls)


def svg_overwrite(filename, uptime_data, commit_data, star_data, repo_data, contrib_data, follower_data, loc_data, top_repos, top_langs, repo_langs, activity_data, prev_activity_data=None):
    """
    Parse SVG files and update elements with my uptime, commits, stars, repositories, and lines written
    Every row's rightmost character lands on the same column (ROW_WIDTH) as the system-info block above it.
    The '|' separating Repos/Stars from Commits/Followers is kept at the same column on both rows by
    sizing commit_data's leader dots off however wide the Repos side actually is that run.
    """
    tree = etree.parse(filename)
    root = tree.getroot()
    ROW_WIDTH = 60
    REPO_LEN = 8
    justify_format(root, 'uptime_data', uptime_data, 51)
    justify_format(root, 'repo_data', repo_data, REPO_LEN)
    justify_format(root, 'contrib_data', contrib_data)
    contrib_str = '{:,}'.format(contrib_data) if isinstance(contrib_data, int) else str(contrib_data)
    left_width = len('. Repos:') + REPO_LEN + len(' {Contributed: ') + len(contrib_str) + len('}')
    right_width = ROW_WIDTH - left_width - len(' | ')
    star_len = right_width - len('Stars:')
    justify_format(root, 'star_data', star_data, star_len)
    commit_len = left_width - len('. Commits:')
    justify_format(root, 'commit_data', commit_data, commit_len)
    follower_len = right_width - len('Followers:')
    justify_format(root, 'follower_data', follower_data, follower_len)

    # Lines of Code: '(' lands on the same column as the '|' above; ')' lands on the card's rightmost
    # column like everything else. "add++, del--" stays put as one block with a plain ', ' between the
    # two numbers, and whatever width is left over is split evenly as padding against each parenthesis.
    loc_prefix_len = len('. Lines of Code on GitHub:')
    loc_len = left_width - loc_prefix_len
    justify_format(root, 'loc_data', loc_data[2], loc_len)
    add_str = '{:,}'.format(loc_data[0]) if isinstance(loc_data[0], int) else str(loc_data[0])
    del_str = '{:,}'.format(loc_data[1]) if isinstance(loc_data[1], int) else str(loc_data[1])
    fixed_len = len(' (') + len(add_str) + len('++') + len(', ') + len(del_str) + len('--') + len(')')
    total_pad = max(0, ROW_WIDTH - left_width - fixed_len)
    pad_l = total_pad // 2
    pad_r = total_pad - pad_l
    find_and_replace(root, 'loc_pad_open', ' ' * pad_l)
    find_and_replace(root, 'loc_pad_close', ' ' * pad_r)
    justify_format(root, 'loc_add', loc_data[0])
    justify_format(root, 'loc_del', loc_data[1])
    find_and_replace(root, 'last_update', last_update_timestamp())

    build_left_panel(root, top_repos, top_langs, repo_langs)
    build_activity_graph(root, activity_data, prev_activity_data)
    tree.write(filename, encoding='utf-8', xml_declaration=True)


def justify_format(root, element_id, new_text, length=0):
    """
    Updates and formats the text of the element, and modifes the amount of dots in the previous element to justify the new text on the svg
    """
    if isinstance(new_text, int):
        new_text = f"{'{:,}'.format(new_text)}"
    new_text = str(new_text)
    find_and_replace(root, element_id, new_text)
    just_len = max(0, length - len(new_text))
    if just_len <= 2:
        dot_map = {0: '', 1: ' ', 2: '. '}
        dot_string = dot_map[just_len]
    else:
        dot_string = ' ' + ('.' * (just_len - 2)) + ' '
    find_and_replace(root, f"{element_id}_dots", dot_string)


def find_and_replace(root, element_id, new_text):
    """
    Finds the element in the SVG file and replaces its text with a new value
    """
    element = root.find(f".//*[@id='{element_id}']")
    if element is not None:
        element.text = new_text


def commit_counter(comment_size):
    """
    Counts up my total commits, using the cache file created by cache_builder.
    """
    total_commits = 0
    filename = 'cache/'+hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest()+'.txt' # Use the same filename as cache_builder
    with open(filename, 'r') as f:
        data = f.readlines()
    cache_comment = data[:comment_size] # save the comment block
    data = data[comment_size:] # remove those lines
    for line in data:
        total_commits += int(line.split()[2])
    return total_commits


def user_getter(username):
    """
    Returns the account ID and creation time of the user
    """
    query_count('user_getter')
    query = '''
    query($login: String!){
        user(login: $login) {
            id
            createdAt
        }
    }'''
    variables = {'login': username}
    request = simple_request(user_getter.__name__, query, variables)
    return {'id': request.json()['data']['user']['id']}, request.json()['data']['user']['createdAt']

def follower_getter(username):
    """
    Returns the number of followers of the user
    """
    query_count('follower_getter')
    query = '''
    query($login: String!){
        user(login: $login) {
            followers {
                totalCount
            }
        }
    }'''
    request = simple_request(follower_getter.__name__, query, {'login': username})
    return int(request.json()['data']['user']['followers']['totalCount'])


def query_count(funct_id):
    """
    Counts how many times the GitHub GraphQL API is called
    """
    global QUERY_COUNT
    QUERY_COUNT[funct_id] += 1


def perf_counter(funct, *args):
    """
    Calculates the time it takes for a function to run
    Returns the function result and the time differential
    """
    start = time.perf_counter()
    funct_return = funct(*args)
    return funct_return, time.perf_counter() - start


def formatter(query_type, difference, funct_return=False, whitespace=0):
    """
    Prints a formatted time differential
    Returns formatted result if whitespace is specified, otherwise returns raw result
    """
    print('{:<23}'.format('   ' + query_type + ':'), sep='', end='')
    print('{:>12}'.format('%.4f' % difference + ' s ')) if difference > 1 else print('{:>12}'.format('%.4f' % (difference * 1000) + ' ms'))
    if whitespace:
        return f"{'{:,}'.format(funct_return): <{whitespace}}"
    return funct_return


if __name__ == '__main__':
    print('Calculation times:')
    # define global variable for owner ID and calculate user's creation date
    user_data, user_time = perf_counter(user_getter, USER_NAME)
    OWNER_ID, acc_date = user_data
    formatter('account data', user_time)
    uptime_data, uptime_time = perf_counter(account_uptime, acc_date)
    formatter('uptime calculation', uptime_time)
    total_loc, loc_time = perf_counter(loc_query, ['OWNER', 'COLLABORATOR', 'ORGANIZATION_MEMBER'], 7)
    formatter('LOC (cached)', loc_time) if total_loc[3] else formatter('LOC (no cache)', loc_time)
    loc_edges, loc_cache_data = total_loc[4], total_loc[5]
    commit_data, commit_time = perf_counter(commit_counter, 7)
    star_data, star_time = perf_counter(graph_repos_stars, 'stars', ['OWNER'])
    repo_data, repo_time = perf_counter(graph_repos_stars, 'repos', ['OWNER'])
    contrib_data, contrib_time = perf_counter(graph_repos_stars, 'repos', ['OWNER', 'COLLABORATOR', 'ORGANIZATION_MEMBER'])
    follower_data, follower_time = perf_counter(follower_getter, USER_NAME)
    top_repo_data, top_repo_time = perf_counter(latest_repos, loc_edges, loc_cache_data)
    lang_edges, lang_time = perf_counter(graph_languages, ['OWNER', 'COLLABORATOR', 'ORGANIZATION_MEMBER'])
    top_lang_data = aggregate_languages(lang_edges)
    repo_lang_data = repo_language_map(lang_edges)
    activity_60d, activity_time = perf_counter(daily_activity, 60)
    prev_activity_data, activity_data = activity_60d[:30], activity_60d[30:]

    for index in range(3): total_loc[index] = '{:,}'.format(total_loc[index]) # format added, deleted, and total LOC

    svg_overwrite('dark_mode.svg', uptime_data, commit_data, star_data, repo_data, contrib_data, follower_data, total_loc[:3], top_repo_data, top_lang_data, repo_lang_data, activity_data, prev_activity_data)
    svg_overwrite('light_mode.svg', uptime_data, commit_data, star_data, repo_data, contrib_data, follower_data, total_loc[:3], top_repo_data, top_lang_data, repo_lang_data, activity_data, prev_activity_data)

    # move cursor to override 'Calculation times:' with 'Total function time:' and the total function time, then move cursor back
    print('\033[F\033[F\033[F\033[F\033[F\033[F\033[F\033[F',
        '{:<21}'.format('Total function time:'), '{:>11}'.format('%.4f' % (user_time + uptime_time + loc_time + commit_time + star_time + repo_time + contrib_time + top_repo_time + lang_time + activity_time)),
        ' s \033[E\033[E\033[E\033[E\033[E\033[E\033[E\033[E', sep='')

    print('Total GitHub GraphQL API calls:', '{:>3}'.format(sum(QUERY_COUNT.values())))
    for funct_name, count in QUERY_COUNT.items(): print('{:<28}'.format('   ' + funct_name + ':'), '{:>6}'.format(count))