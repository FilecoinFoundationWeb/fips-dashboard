#!/usr/bin/env python3
"""Network upgrade scope planning from the public core-devs Discussions.

Each upcoming upgrade gets a "nvNN Network Upgrade Planning" discussion in
filecoin-project/core-devs. Its comments hold:

  * a Scope table: one row per candidate FIP/FRC with a readiness marker
    (🟢 🟡 🔴 🟤 ⚪), status and progress, timeline, T-shirt size, summary and
    notes;
  * a Timeline table: milestones (actor code freeze, Lotus RC, Calibnet,
    mainnet...) with their latest dates;
  * a naming note.

This module finds those discussions (GitHub GraphQL, public data only) and
parses the tables. Columns are matched by header name, so reordering or
adding columns in the discussion doesn't break the page.
"""

import re
from datetime import datetime, timezone

import fip_utils as u

REPO_OWNER, REPO_NAME = 'filecoin-project', 'core-devs'
TITLE = re.compile(r'\bnv\s?-?(\d{2,3})\b.*\b(planning|scope|scoping)\b', re.I)

READINESS = {
    '🟢': ('ready', 'Ready'),
    '🟡': ('risk', 'Needs review / at risk'),
    '🔴': ('deferred-in', 'Deferred into this upgrade'),
    '🟤': ('deferred-out', 'Deferred to the next upgrade'),
    '⚪': ('none', 'Not tied to an upgrade'),
}

QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    discussions(first: 40, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes {
        number title url updatedAt body
        comments(first: 30) { totalCount nodes { body updatedAt } }
      }
    }
  }
}
"""


# ---------------------------------------------------------------------------
# Markdown table parsing
# ---------------------------------------------------------------------------

def _cells(line):
    line = line.strip()
    if line.startswith('|'):
        line = line[1:]
    if line.endswith('|'):
        line = line[:-1]
    # Split on pipes that aren't escaped.
    return [c.strip() for c in re.split(r'(?<!\\)\|', line)]


def tables(md):
    """Every markdown table in `md` as (header cells, [row cells])."""
    out, lines, i = [], (md or '').replace('\r', '').split('\n'), 0
    while i < len(lines) - 1:
        if '|' in lines[i] and re.match(r'^\s*\|?\s*:?-{2,}', lines[i + 1]):
            head = _cells(lines[i])
            rows, j = [], i + 2
            while j < len(lines) and '|' in lines[j] and lines[j].strip():
                rows.append(_cells(lines[j]))
                j += 1
            out.append((head, rows))
            i = j
        else:
            i += 1
    return out


def _col(head, *names):
    for n in names:
        for k, h in enumerate(head):
            if n in h.lower():
                return k
    return None


def _links(cell):
    return re.findall(r'\[([^\]]+)\]\((https?://[^)\s]+)\)', cell or '')


def _plain(cell):
    s = re.sub(r'<br\s*/?>', ' · ', cell or '', flags=re.I)
    s = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', s)
    s = re.sub(r'<[^>]+>', '', s)
    s = re.sub(r'[*_`]', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def _readiness(cell):
    for mark, (key, label) in READINESS.items():
        if mark in (cell or ''):
            return key, label
    return 'unknown', ''


def parse_scope(head, rows):
    item = _col(head, 'fip', 'item', 'proposal')
    link = _col(head, 'link')
    status = _col(head, 'status')
    timeline = _col(head, 'timeline')
    size = _col(head, 't-shirt', 'size')
    summary = _col(head, 'summary')
    notes = _col(head, 'notes', 'decision')
    ready_col = _col(head, 'readiness', 'scope', 'ready')
    if item is None or status is None:
        return []
    out = []
    for r in rows:
        r = r + [''] * (len(head) - len(r))
        name_cell = r[item]
        # The readiness marker usually leads the name cell, but some tables
        # put it in its own "Scope"/"Readiness" column; fall back to any cell.
        key, label = _readiness(name_cell)
        if key == 'unknown' and ready_col is not None:
            key, label = _readiness(r[ready_col])
        if key == 'unknown':
            key, label = _readiness(' '.join(r))
        name = _plain(re.sub('|'.join(READINESS), '', name_cell))
        if not name:
            continue
        links = _links(r[link]) if link is not None else []
        links += _links(name_cell)
        m = re.search(r'\b(FIP|FRC)-?0*(\d{1,4})\b', name)
        size_txt = _plain(r[size]) if size is not None else ''
        size_txt = re.sub(r'\s*\(.*?\)', '', size_txt).strip()  # "L (someone's estimate)" -> "L"
        out.append({
            'readiness': key, 'readiness_label': label, 'name': name,
            'fip': f'{int(m.group(2)):04d}' if m and m.group(1).upper() == 'FIP' else None,
            'link': links[0][1] if links else None,
            'link_label': links[0][0] if links else None,
            'links': [url for _, url in links],
            'status': _plain(r[status]),
            'timeline': _plain(r[timeline]) if timeline is not None else '',
            'size': size_txt if size_txt and size_txt.upper() != 'TBD' else '',
            'summary': _plain(r[summary]) if summary is not None else '',
            'notes': re.sub(r'^(open|decide|notes?)\s*:\s*', '', _plain(r[notes]), flags=re.I) if notes is not None else '',
        })
    return out


def parse_milestones(head, rows):
    item = _col(head, 'item', 'milestone')
    date = _col(head, 'date', 'when')
    if item is None or date is None:
        return []
    out = []
    for r in rows:
        r = r + [''] * (len(head) - len(r))
        name = _plain(r[item])
        if name:
            out.append({'name': name, 'date': _plain(r[date]) or 'TBD'})
    return out


def parse_discussion(d):
    """Scope rows, milestones and naming note from one planning discussion."""
    bodies = [d.get('body') or ''] + [c.get('body') or '' for c in (d.get('comments') or {}).get('nodes') or []]
    scope, milestones, naming = [], [], ''
    for body in bodies:
        for head, rows in tables(body):
            low = ' '.join(head).lower()
            if 'status' in low and ('fip' in low or 'item' in low and 'size' in low):
                scope = scope or parse_scope(head, rows)
            elif 'date' in low and ('item' in low or 'milestone' in low):
                milestones = milestones or parse_milestones(head, rows)
        m = re.search(r'name of the upgrade:?\**\s*\n+(.+)', body, re.I)
        if m and not naming:
            naming = _plain(m.group(1))[:200]
    return scope, milestones, naming


# ---------------------------------------------------------------------------

def fetch_planning():
    """Planning entries newest-upgrade first, or None if GitHub was unavailable."""
    data = u.github_graphql(QUERY, {'owner': REPO_OWNER, 'name': REPO_NAME})
    try:
        nodes = data['repository']['discussions']['nodes']
    except (TypeError, KeyError):
        return None
    out, seen = [], set()
    for d in nodes:
        m = TITLE.search(d.get('title') or '')
        if not m:
            continue
        nv = int(m.group(1))
        if nv in seen:
            continue
        seen.add(nv)
        scope, milestones, naming = parse_discussion(d)
        out.append({
            'nv': nv, 'title': d['title'], 'url': d['url'],
            'updated': datetime.fromisoformat(d['updatedAt'].replace('Z', '+00:00')),
            'comments': (d.get('comments') or {}).get('totalCount', 0),
            'scope': scope, 'milestones': milestones, 'naming': naming,
        })
        print(f'Scope planning: NV{nv} ({len(scope)} candidates, {len(milestones)} milestones) from #{d["number"]}')
    out.sort(key=lambda x: x['nv'], reverse=True)
    return out


# ---------------------------------------------------------------------------
# Flagging FIPs that appear in planning
# ---------------------------------------------------------------------------

FIPS_PR = re.compile(r'github\.com/filecoin-project/FIPs/pull/(\d+)', re.I)
FIPS_FILE = re.compile(r'github\.com/filecoin-project/FIPs/blob/[^/]+/FIPS/fip-0*(\d+)\.md', re.I)


def _norm_url(url):
    return (url or '').split('#')[0].split('?')[0].rstrip('/').lower()


def _norm_title(text):
    text = re.sub(r'^\s*(FIP|FRC)-?(\d+|X+)\s*[:\-—]\s*', '', text or '', flags=re.I)
    return re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()


def active(planning, upgrades, now=None):
    """The active planning cycle: the lowest-numbered upgrade not yet live on
    mainnet that has a planning discussion. Returns [entry] or [].

    Once that upgrade activates, the next one's planning becomes active, so
    the FIPs page rolls from NV30 to NV31 without code changes.
    """
    plans = upcoming(planning, upgrades, now)
    return [min(plans, key=lambda p: p['nv'])] if plans else []


def upcoming(planning, upgrades, now=None):
    """Planning entries for upgrades that haven't reached mainnet yet."""
    now = now or datetime.now(timezone.utc)
    live = [x['number'] for x in upgrades or []
            if isinstance(x.get('number'), int) and x.get('mainnet') and x['mainnet'] <= now]
    latest_live = max(live) if live else 0
    return [p for p in planning or [] if p['nv'] > latest_live]


def fip_flags(plans, titles=None, files=None, prs=None):
    """Map FIP number -> list of planning mentions, one per upcoming upgrade.

    A planning row is tied to a FIP by, in order: the FIP number in its name;
    a link to the FIP's file, to an open FIPs PR that touches it, or to its
    discussions-to thread; or (for "FIP-XXXX" rows not yet renumbered) an
    exact match on the normalized title.
    """
    titles, files, prs = titles or {}, files or {}, prs or []
    by_disc = {}
    for num, meta in files.items():
        for d in meta.get('_discussions', []):
            by_disc.setdefault(_norm_url(d), set()).add(num)
    by_pr = {}
    for pr in prs:
        for num in pr.get('fip_numbers', []):
            if num != 'General':
                by_pr.setdefault(int(pr['number']), set()).add(num)
    by_title = {}
    for num, t in titles.items():
        key = _norm_title(t)
        if len(key) >= 12:
            by_title.setdefault(key, set()).add(num)

    flags = {}
    for p in plans:
        for row in p['scope']:
            nums = set()
            if row.get('fip'):
                nums.add(row['fip'])
            for url in row.get('links') or ([row['link']] if row.get('link') else []):
                if m := FIPS_FILE.search(url):
                    nums.add(f'{int(m.group(1)):04d}')
                elif m := FIPS_PR.search(url):
                    nums |= by_pr.get(int(m.group(1)), set())
                nums |= by_disc.get(_norm_url(url), set())
            if not nums:
                nums |= by_title.get(_norm_title(row['name']), set())
            for num in nums:
                entry = {'nv': p['nv'], 'readiness': row['readiness'], 'label': row['readiness_label'],
                         'name': row['name'], 'url': p['url']}
                if not any(e['nv'] == p['nv'] for e in flags.get(num, [])):
                    flags.setdefault(num, []).append(entry)
    return flags
