#!/usr/bin/env python3
"""Shared utilities for the FIPs dashboard scripts.

Everything here is read-only with respect to filecoin-project/FIPs: it reads
a local clone of the repository and the public GitHub API, and never writes
anything back.
"""

import os
import re
import json
import shutil
import subprocess
import tempfile
import urllib.request
from datetime import datetime, timedelta, timezone

FIPS_REPO = 'filecoin-project/FIPs'
FIPS_GIT_URL = f'https://github.com/{FIPS_REPO}.git'
FIPS_BASE_URL = f'https://github.com/{FIPS_REPO}/blob/master/'
GITHUB_API_BASE = f'https://api.github.com/repos/{FIPS_REPO}'

# FIP-0001: Last Call sets `review-period-end`, "normally 14 days later".
DEFAULT_LAST_CALL_DAYS = 14


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def html_escape(text):
    """Escape HTML special characters to prevent XSS."""
    if text is None:
        return ''
    text = str(text)
    return (
        text
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
        .replace("'", '&#x27;')
    )


def normalize_status(status):
    """Normalize a status string: 'Superseded by FIP-0x' -> 'Superseded', etc."""
    s = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', status or '').strip()
    s = s.strip('*_` ')
    low = s.lower()
    for known in ('Superseded', 'Last Call', 'Withdrawn', 'Rejected', 'Deferred',
                  'Accepted', 'Final', 'Active', 'Draft'):
        if low.startswith(known.lower()):
            return known
    return s


def get_status_class(status):
    """Get CSS class for status badge."""
    status_lower = (status or '').lower()
    if 'final' in status_lower:
        return 'status-final'
    elif 'last call' in status_lower:
        return 'status-last-call'
    elif 'draft' in status_lower:
        return 'status-draft'
    elif 'accepted' in status_lower or 'approved' in status_lower:
        return 'status-accepted'
    elif 'deferred' in status_lower:
        return 'status-deferred'
    elif 'rejected' in status_lower:
        return 'status-rejected'
    elif 'withdrawn' in status_lower:
        return 'status-withdrawn'
    elif 'active' in status_lower:
        return 'status-active'
    elif 'superseded' in status_lower:
        return 'status-superseded'
    else:
        print(f"Warning: Unknown FIP status '{status}', defaulting to 'status-draft'")
        return 'status-draft'


def fip_url(number):
    return f'{FIPS_BASE_URL}FIPS/fip-{number}.md'


def days_between(start, end=None):
    end = end or datetime.now(timezone.utc)
    return max(0, (end - start).days)


def humanize_days(days):
    if days is None:
        return '—'
    if days < 1:
        return 'today'
    if days < 60:
        return f'{days} day{"s" if days != 1 else ""}'
    months = days / 30.44
    if months < 24:
        return f'{months:.0f} months'
    return f'{days / 365.25:.1f} years'


# ---------------------------------------------------------------------------
# README table parsing
# ---------------------------------------------------------------------------

def _split_row(line):
    cells = line.strip().split('|')
    if cells and cells[0].strip() == '':
        cells = cells[1:]
    if cells and cells[-1].strip() == '':
        cells = cells[:-1]
    return [c.strip() for c in cells]


def parse_fip_table(text):
    """Parse FIPs from the README markdown table.

    Column positions are read from the header row, so this works across the
    README's historical layouts (with or without a Type column, with or
    without padding). Returns a list of dicts with keys: number, title, type,
    authors, status. FRCs are excluded.
    """
    fips = []
    cols = None

    for line in (text or '').split('\n'):
        stripped = line.strip()
        if not stripped.startswith('|'):
            if cols is not None and fips:
                # First table ended. The FIP table is the first one in the README.
                break
            continue

        cells = _split_row(stripped)
        lowered = [c.lower() for c in cells]

        if cols is None:
            if any(c.startswith('fip') and '#' in c for c in lowered) and 'status' in lowered:
                cols = {name: i for i, name in enumerate(lowered)}
            continue

        if re.match(r'^\|[\s\-|:]+$', stripped):
            continue

        num_cell = cells[0] if cells else ''
        m = re.search(r'\[(\d+)\]\(([^)]*)\)', num_cell)
        if not m:
            continue
        number, link = m.group(1), m.group(2)

        def col(name, default=''):
            for key, idx in cols.items():
                if key.startswith(name) and idx < len(cells):
                    return cells[idx]
            return default

        fip_type = col('type', '')
        is_frc = '/frcs/' in link.lower() or fip_type.strip().upper() == 'FRC'
        if is_frc:
            continue

        fips.append({
            'number': number.zfill(4),
            'title': col('title'),
            'type': fip_type or 'FIP',
            'authors': col('author'),
            'status': normalize_status(col('status')),
        })

    return fips


# ---------------------------------------------------------------------------
# Local clone of the FIPs repo (full history, no API quota used)
# ---------------------------------------------------------------------------

def _git(repo_dir, *args):
    return subprocess.run(
        ['git', '-C', repo_dir, *args],
        check=True, capture_output=True, text=True,
    ).stdout


def get_repo(git_url, env_var, default_name, path=None):
    """Return a path to an up-to-date local clone of a public repo.

    Uses the directory in `env_var` if set (handy for local runs and for
    sharing one clone between scripts in CI), otherwise clones into a
    temporary directory. Full clones are used because the history walk reads
    hundreds of README versions; a blob-filtered clone would fetch each one
    separately and run several times slower.
    """
    path = path or os.environ.get(env_var)
    if path and os.path.isdir(os.path.join(path, '.git')):
        try:
            _git(path, 'fetch', '-q', 'origin')
            _git(path, 'reset', '-q', '--hard', 'origin/HEAD')
        except subprocess.CalledProcessError as e:
            print(f'Warning: could not update {path}: {e.stderr.strip()}')
        return path

    path = path or os.path.join(tempfile.gettempdir(), default_name)
    if os.path.isdir(path):
        shutil.rmtree(path)
    subprocess.run(['git', 'clone', '-q', git_url, path], check=True)
    return path


def get_fips_repo(path=None):
    """Local clone of filecoin-project/FIPs (FIPS_REPO_DIR to reuse one)."""
    return get_repo(FIPS_GIT_URL, 'FIPS_REPO_DIR', 'fips-src', path)


def read_readme(repo_dir, sha='HEAD'):
    return _git(repo_dir, 'show', f'{sha}:README.md')


def readme_commits(repo_dir):
    """All commits touching README.md, oldest first: [(sha, datetime)]."""
    out = _git(repo_dir, 'log', '--reverse', '--format=%H %cI', '--', 'README.md')
    commits = []
    for line in out.splitlines():
        sha, date = line.split(' ', 1)
        commits.append((sha, datetime.fromisoformat(date).astimezone(timezone.utc)))
    return commits


def build_status_history(repo_dir):
    """Walk every README commit and record each FIP's status transitions.

    Returns (history, events):
      history: {fip_number: [{'status', 'since', 'sha'}...]} oldest first
      events:  flat list of {'date', 'sha', 'number', 'title', 'from', 'to'}
               where 'from' is None for a newly listed FIP.
    Commits whose README can't be parsed are skipped rather than treated as
    "every FIP removed".
    """
    history = {}
    events = []
    prev = {}
    for sha, date in readme_commits(repo_dir):
        try:
            fips = {f['number']: f for f in parse_fip_table(read_readme(repo_dir, sha))}
        except subprocess.CalledProcessError:
            continue
        if not fips:
            continue
        for num, fip in fips.items():
            status = fip['status']
            old = prev.get(num)
            if old is None or old['status'] != status:
                history.setdefault(num, []).append({'status': status, 'since': date, 'sha': sha})
                events.append({
                    'date': date, 'sha': sha, 'number': num, 'title': fip['title'],
                    'from': old['status'] if old else None, 'to': status,
                })
        for num, old in prev.items():
            if num not in fips:
                events.append({
                    'date': date, 'sha': sha, 'number': num, 'title': old['title'],
                    'from': old['status'], 'to': None,
                })
        prev = fips
    return history, events


# ---------------------------------------------------------------------------
# FIP file front matter
# ---------------------------------------------------------------------------

def parse_front_matter(text):
    """Minimal YAML front matter parser (stdlib only).

    Handles `key: value`, quoted values and `- item` lists, which is all the
    FIP template uses.
    """
    lines = (text or '').split('\n')
    if not lines or lines[0].strip() != '---':
        return {}
    meta = {}
    key = None
    for line in lines[1:]:
        if line.strip() == '---':
            break
        m = re.match(r'^([A-Za-z0-9_-]+):\s*(.*)$', line)
        if m:
            key = m.group(1).lower()
            val = m.group(2).strip().strip('"\'')
            meta[key] = val if val else []
        elif key and re.match(r'^\s*-\s+', line):
            item = re.sub(r'^\s*-\s+', '', line).strip().strip('"\'')
            if not isinstance(meta.get(key), list):
                meta[key] = [meta[key]] if meta.get(key) else []
            meta[key].append(item)
    return meta


def load_fip_files(repo_dir):
    """{fip_number: front-matter dict} for every FIPS/fip-XXXX.md file."""
    result = {}
    fips_dir = os.path.join(repo_dir, 'FIPS')
    if not os.path.isdir(fips_dir):
        return result
    for name in sorted(os.listdir(fips_dir)):
        m = re.match(r'fip-(\d+)\.md$', name, re.IGNORECASE)
        if not m:
            continue
        with open(os.path.join(fips_dir, name), encoding='utf-8', errors='replace') as f:
            meta = parse_front_matter(f.read())
        meta['_status'] = normalize_status(meta.get('status') if isinstance(meta.get('status'), str) else '')
        disc = meta.get('discussions-to') or []
        meta['_discussions'] = [d for d in (disc if isinstance(disc, list) else [disc]) if d.startswith('http')]
        result[m.group(1).zfill(4)] = meta
    return result


def parse_date(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.strip()[:10]).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# GitHub API (pull requests)
# ---------------------------------------------------------------------------

def make_github_request(url):
    """Make an authenticated GitHub API request if GITHUB_TOKEN is available."""
    req = urllib.request.Request(url)
    token = os.environ.get('GITHUB_TOKEN', '')
    if token:
        req.add_header('Authorization', f'token {token}')
    req.add_header('Accept', 'application/vnd.github.v3+json')
    req.add_header('User-Agent', 'fips-dashboard')
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))


def github_graphql(query, variables=None):
    """POST a GraphQL query (needs GITHUB_TOKEN). Returns data or None."""
    token = os.environ.get('GITHUB_TOKEN', '')
    if not token:
        return None
    body = json.dumps({'query': query, 'variables': variables or {}}).encode()
    req = urllib.request.Request('https://api.github.com/graphql', data=body, method='POST')
    req.add_header('Authorization', f'bearer {token}')
    req.add_header('Content-Type', 'application/json')
    req.add_header('User-Agent', 'fips-dashboard')
    try:
        with urllib.request.urlopen(req) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f'Warning: GraphQL request failed: {e}')
        return None
    if payload.get('errors'):
        print(f"Warning: GraphQL errors: {payload['errors'][:1]}")
    return payload.get('data')


DISCUSSIONS_QUERY = """
query($owner: String!, $name: String!, $n: Int!) {
  repository(owner: $owner, name: $name) {
    discussions(first: $n, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes {
        number title url createdAt updatedAt
        author { login }
        category { name }
        comments { totalCount }
      }
    }
  }
}
"""


def fetch_discussions(owner, name, n=20):
    """Recently updated GitHub Discussions for a repo, or None if unavailable."""
    data = github_graphql(DISCUSSIONS_QUERY, {'owner': owner, 'name': name, 'n': n})
    try:
        nodes = data['repository']['discussions']['nodes']
    except (TypeError, KeyError):
        return None
    out = []
    for d in nodes:
        out.append({
            'number': d['number'], 'title': d['title'], 'url': d['url'],
            'created': datetime.fromisoformat(d['createdAt'].replace('Z', '+00:00')),
            'updated': datetime.fromisoformat(d['updatedAt'].replace('Z', '+00:00')),
            'author': (d.get('author') or {}).get('login', 'ghost'),
            'category': (d.get('category') or {}).get('name', ''),
            'comments': (d.get('comments') or {}).get('totalCount', 0),
            'repo': f'{owner}/{name}',
        })
    return out


def _paged(url):
    items, page = [], 1
    while True:
        sep = '&' if '?' in url else '?'
        batch = make_github_request(f'{url}{sep}per_page=100&page={page}')
        if not batch:
            break
        items.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return items


def fetch_open_prs():
    """All open PRs on the FIPs repo, or None if they couldn't be fetched."""
    try:
        return _paged(f'{GITHUB_API_BASE}/pulls?state=open')
    except Exception as e:
        print(f'Warning: Could not fetch PRs: {e}')
        return None


def extract_fip_from_title(title):
    """Subject FIP numbers from a PR title (placeholders like FIPXXXX skipped)."""
    if not title or re.search(r'FIP[-\s]?[Xx]{2,}', title, re.IGNORECASE):
        return []
    return sorted({m.zfill(4) for m in re.findall(r'FIP[-\s]?(\d{1,4})', title, re.IGNORECASE)})


def extract_fip_from_files(pr_number):
    """FIP numbers from files a PR changes — the ground truth for its subject."""
    try:
        files = _paged(f'{GITHUB_API_BASE}/pulls/{pr_number}/files')
    except Exception as e:
        print(f'Warning: Could not fetch files for PR #{pr_number}: {e}')
        return []
    nums = set()
    for f in files:
        m = re.search(r'FIPS/fip-(\d+)\.md', f.get('filename', ''), re.IGNORECASE)
        if m:
            nums.add(m.group(1).zfill(4))
    return sorted(nums)


def fetch_review_state(pr_number, is_draft=False):
    """Summarize a PR's reviews: the latest decisive review per reviewer wins."""
    if is_draft:
        return 'Draft PR'
    try:
        reviews = _paged(f'{GITHUB_API_BASE}/pulls/{pr_number}/reviews')
    except Exception as e:
        print(f'Warning: Could not fetch reviews for PR #{pr_number}: {e}')
        return 'Unknown'
    latest = {}
    commented = False
    for r in reviews:
        state = r.get('state')
        user = (r.get('user') or {}).get('login')
        if state == 'COMMENTED':
            commented = True
        elif state in ('APPROVED', 'CHANGES_REQUESTED', 'DISMISSED') and user:
            latest[user] = state
    states = set(latest.values())
    if 'CHANGES_REQUESTED' in states:
        return 'Changes requested'
    if 'APPROVED' in states:
        n = sum(1 for s in latest.values() if s == 'APPROVED')
        return f'Approved ({n})'
    if commented:
        return 'Comments only'
    return 'Awaiting review'


def categorize_pr(pr):
    """Rough category from the PR title/body (informational only)."""
    title = (pr.get('title') or '').lower()
    combined = f"{title} {(pr.get('body') or '').lower()}"
    categories = []
    if any(w in title for w in ('new', 'add', 'create')):
        categories.append('New FIP')
    if any(w in title for w in ('update', 'modify', 'change')):
        categories.append('Update FIP')
    if any(w in combined for w in ('status', 'final', 'draft', 'last call')):
        categories.append('Status Change')
    if 'supersede' in combined or 'replace' in combined:
        categories.append('Supersede')
    return categories or ['General']


def process_prs(prs, with_reviews=True):
    """Annotate open PRs with the FIPs they touch and their review state.

    Subject FIPs come from changed files first, then the title. PRs with
    neither are kept as 'General' if 'FIP' appears in the title.
    """
    out = []
    now = datetime.now(timezone.utc)
    for pr in prs or []:
        number = pr.get('number')
        title = pr.get('title') or ''
        fips = extract_fip_from_files(number) or extract_fip_from_title(title)
        if not fips:
            if 'fip' in title.lower():
                fips = ['General']
            else:
                continue
        updated = datetime.fromisoformat(pr.get('updated_at', '').replace('Z', '+00:00'))
        body = pr.get('body') or ''
        out.append({
            'number': number,
            'title': title,
            'url': pr.get('html_url'),
            'author': (pr.get('user') or {}).get('login', 'Unknown'),
            'created_at': pr.get('created_at', ''),
            'updated_at': pr.get('updated_at', ''),
            'idle_days': (now - updated).days,
            'branch': (pr.get('head') or {}).get('ref', ''),
            'draft': bool(pr.get('draft')),
            'review': fetch_review_state(number, pr.get('draft')) if with_reviews else 'Unknown',
            'fip_numbers': fips,
            'categories': categorize_pr(pr),
            'body': body[:200] + '...' if len(body) > 200 else body,
        })
    return out


def prs_by_fip(processed):
    grouped = {}
    for pr in processed:
        for num in pr['fip_numbers']:
            grouped.setdefault(num, []).append(pr)
    return grouped


# ---------------------------------------------------------------------------
# Derived views
# ---------------------------------------------------------------------------

def current_status_since(history, number, status):
    """When the FIP entered its current status, per README history."""
    entries = history.get(number) or []
    for entry in reversed(entries):
        if entry['status'] == status:
            return entry['since']
    return None


def last_call_windows(history, files, current):
    """Current and past Last Call windows.

    Returns (open_windows, past_windows). Dates come from README history;
    the end date uses the FIP's `review-period-end` when set, otherwise the
    FIP-0001 default of 14 days (marked as estimated).
    """
    open_windows, past = [], []
    for num, entries in history.items():
        for i, entry in enumerate(entries):
            if entry['status'] != 'Last Call':
                continue
            nxt = entries[i + 1] if i + 1 < len(entries) else None
            meta = files.get(num, {})
            end = parse_date(meta.get('review-period-end'))
            estimated = end is None
            if estimated:
                end = entry['since'] + timedelta(days=DEFAULT_LAST_CALL_DAYS)
            title = (current.get(num) or {}).get('title', meta.get('title', ''))
            window = {
                'number': num, 'title': title, 'start': entry['since'], 'end': end,
                'estimated_end': estimated, 'discussions': meta.get('_discussions', []),
            }
            if nxt is None:
                open_windows.append(window)
            else:
                window['exit'] = nxt['since']
                window['outcome'] = nxt['status']
                window['days'] = (nxt['since'] - entry['since']).days
                past.append(window)
    open_windows.sort(key=lambda w: w['end'])
    past.sort(key=lambda w: w['exit'], reverse=True)
    return open_windows, past


def status_mismatches(current, files):
    """FIPs whose README status disagrees with their own file's `status:`."""
    rows = []
    for num, fip in sorted(current.items()):
        meta = files.get(num)
        if meta is None:
            rows.append({'number': num, 'title': fip['title'], 'readme': fip['status'],
                         'file': None, 'note': 'No FIPS/fip-%s.md file' % num})
            continue
        if meta['_status'] and meta['_status'].lower() != fip['status'].lower():
            rows.append({'number': num, 'title': fip['title'], 'readme': fip['status'],
                         'file': meta['_status'], 'note': ''})
    for num, meta in sorted(files.items()):
        if num not in current:
            rows.append({'number': num, 'title': meta.get('title', ''), 'readme': None,
                         'file': meta['_status'], 'note': 'Not listed in README table'})
    return rows
