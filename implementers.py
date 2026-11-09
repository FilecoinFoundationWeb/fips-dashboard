#!/usr/bin/env python3
"""Read Filecoin implementers' calls from the Notion meetings database.

Sources, tried in order:

  0. The public site (default). The Meetings database is published at
     filecoindev.notion.site, so it's read there without any sign-in or token,
     the same way any visitor's browser reads it. Only public data is used, and
     of that only: each call's title, date, public page link, its agenda lines,
     recording links, and FIP / upgrade mentions. People (host, attendees,
     @-mentions) and the async-update tables are never published.
     NOTION_PUBLIC_SITE overrides the site; set it to "" to skip this source.
  1. The Notion API, when NOTION_TOKEN is set. Create an internal integration
     in Notion, share the Meetings database with it, and add its token as the
     NOTION_TOKEN repository secret. NOTION_MEETINGS_DB overrides the database
     ID (default: the filecoindev Meetings database).
  2. A CSV export of the database at data/implementers-calls.csv (Notion:
     ··· → Export → Markdown & CSV). Used when there's no token or the API
     call fails, so the page still builds.

Columns are detected rather than hard-coded: the title column, the first date
column, a select/multi-select column for the meeting type, URL columns for
recording / notes / agenda, and text columns for a summary. Only rows whose
type or title matches IMPLEMENTERS_MATCH (default "implement", which covers
"Implementers" and "Implementors") are kept; set it to "" to keep every row.

Page bodies are read (NOTION_READ_BODIES, on by default) only to find FIP and
network-upgrade mentions. Body text is never written to the published pages.
"""

import csv
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

import core_devs as cd

DEFAULT_DB = '6e47427dee6c4095a90fec4bbe89929d'
NOTION_VERSION = '2022-06-28'
CSV_PATH = os.environ.get('IMPLEMENTERS_CSV') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'implementers-calls.csv')
BODY_LIMIT = 60  # newest calls whose page bodies are scanned for mentions

TYPE_HINT = re.compile(r'type|category|series|kind|meeting|tag', re.I)
SUMMARY_HINT = re.compile(r'summary|topic|agenda|description|tl;?dr|notes', re.I)


def _match():
    return os.environ.get('IMPLEMENTERS_MATCH', 'implement').strip().lower()


def _classify_url(name, url):
    """'recording', 'notes' or 'agenda' for a URL column, by name then host."""
    n, low = (name or '').lower(), (url or '').lower()
    if 'agenda' in n:
        return 'agenda'
    if any(k in n for k in ('record', 'video', 'youtube', 'zoom')) or \
            any(k in low for k in ('youtu', 'zoom.us/rec', 'vimeo', 'loom.com')):
        return 'recording'
    if 'github.com' in low and '/issues/' in low:
        return 'agenda'
    return 'notes'


def _call(title, date, types, urls, summary, page_url, text):
    """Normalize one call. `text` is used only for mention detection."""
    links = {}
    for kind, url in urls:
        links.setdefault(kind, url)
    blob = ' '.join([title or '', summary or '', ' '.join(types), text or ''])
    return {
        'title': (title or '').strip() or 'Implementers call',
        'date': date,
        'types': types,
        'recording_url': links.get('recording'),
        'youtube_id': cd.youtube_id(links.get('recording')),
        'notes_url': links.get('notes'),
        'agenda_url': links.get('agenda'),
        'page_url': page_url,
        'summary': (summary or '').strip(),
        'fips': sorted(cd.fip_mentions(blob)),
        'match_text': blob,
    }


def _keep(title, types):
    m = _match()
    return not m or m in (title or '').lower() or any(m in t.lower() for t in types)


# ---------------------------------------------------------------------------
# Notion API
# ---------------------------------------------------------------------------

def _notion(path, body=None, method='POST'):
    req = urllib.request.Request(
        'https://api.notion.com/v1/' + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method)
    req.add_header('Authorization', 'Bearer ' + os.environ['NOTION_TOKEN'])
    req.add_header('Notion-Version', NOTION_VERSION)
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))


def _plain(rich):
    return ''.join(x.get('plain_text', '') for x in rich or [])


def _prop_values(props):
    """Pull title, date, types, urls and summary out of a page's properties."""
    title, date, date_named, types, urls, summary = '', None, False, [], [], ''
    for name, p in props.items():
        t = p.get('type')
        if t == 'title':
            title = _plain(p['title'])
        elif t == 'date' and p.get('date'):
            d = _iso(p['date'].get('start'))
            named = 'date' in name.lower() or 'when' in name.lower()
            if d and (date is None or (named and not date_named)):
                date, date_named = d, named
        elif t in ('select', 'status') and p.get(t) and TYPE_HINT.search(name):
            types.append(p[t]['name'])
        elif t == 'multi_select' and TYPE_HINT.search(name):
            types += [o['name'] for o in p['multi_select']]
        elif t == 'url' and p.get('url'):
            urls.append((_classify_url(name, p['url']), p['url']))
        elif t == 'rich_text' and SUMMARY_HINT.search(name) and not summary:
            summary = _plain(p['rich_text'])
    return title, date, types, urls, summary


def _iso(value):
    if not value:
        return None
    try:
        d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _body_text(page_id, depth=0):
    """Plain text of a page's blocks (one level of children), for mentions only."""
    out, cursor = [], None
    while True:
        q = f'blocks/{page_id}/children?page_size=100' + (f'&start_cursor={cursor}' if cursor else '')
        res = _notion(q, method='GET')
        for b in res.get('results', []):
            data = b.get(b.get('type'), {}) or {}
            out.append(_plain(data.get('rich_text')))
            if b.get('has_children') and depth < 1 and b.get('type') not in ('child_page', 'child_database'):
                out.append(_body_text(b['id'], depth + 1))
        if not res.get('has_more'):
            return '\n'.join(out)
        cursor = res.get('next_cursor')


def load_from_notion():
    db = (os.environ.get('NOTION_MEETINGS_DB') or DEFAULT_DB).replace('-', '')
    rows, cursor = [], None
    while True:
        body = {'page_size': 100}
        if cursor:
            body['start_cursor'] = cursor
        res = _notion(f'databases/{db}/query', body)
        rows += res.get('results', [])
        if not res.get('has_more'):
            break
        cursor = res.get('next_cursor')
    read_bodies = os.environ.get('NOTION_READ_BODIES', '1') != '0'
    calls = []
    for page in rows:
        title, date, types, urls, summary = _prop_values(page.get('properties', {}))
        if not _keep(title, types):
            continue
        calls.append([page, _call(title, date or _iso(page.get('created_time')), types, urls, summary,
                                  page.get('public_url') or page.get('url'), '')])
    calls.sort(key=lambda pc: pc[1]['date'] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    if read_bodies:
        for page, c in calls[:BODY_LIMIT]:
            try:
                text = _body_text(page['id'])
            except Exception as e:  # one unreadable page shouldn't sink the run
                print(f'Warning: could not read Notion page {page["id"]}: {e}')
                continue
            c['match_text'] += '\n' + text
            c['fips'] = sorted(set(c['fips']) | cd.fip_mentions(text))
    return [c for _, c in calls]


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def load_from_csv(path=CSV_PATH):
    with open(path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        title_col = next((c for c in cols if c.lower() in ('name', 'title', 'meeting')), cols[0] if cols else None)
        date_col = next((c for c in cols if 'date' in c.lower() or c.lower() == 'when'), None)
        type_cols = [c for c in cols if c != title_col and TYPE_HINT.search(c)]
        summary_col = next((c for c in cols if c != title_col and SUMMARY_HINT.search(c)), None)
        url_col_hint = re.compile(r'url|link|record|video|notes|agenda|doc', re.I)
        calls = []
        for row in reader:
            title = row.get(title_col, '') if title_col else ''
            types = [t.strip() for c in type_cols for t in (row.get(c) or '').split(',') if t.strip()]
            if not _keep(title, types):
                continue
            urls = []
            for c in cols:
                v = (row.get(c) or '').strip()
                if v.startswith('http') and (url_col_hint.search(c) or c not in (title_col, summary_col)):
                    urls.append((_classify_url(c, v), v.split()[0]))
            date = _parse_csv_date(row.get(date_col, '')) if date_col else None
            calls.append(_call(title, date, types, urls, row.get(summary_col, '') if summary_col else '',
                               None, ' '.join(row.values())))
    calls.sort(key=lambda c: c['date'] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return calls


def _parse_csv_date(text):
    text = (text or '').split('→')[0].strip()
    for fmt in ('%B %d, %Y %I:%M %p', '%B %d, %Y', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return cd.parse_date(text)


# ---------------------------------------------------------------------------
# Public Notion site (no token)
# ---------------------------------------------------------------------------

PUBLIC_SITE = 'https://filecoindev.notion.site'
AGENDA_HEAD = re.compile(r'agenda', re.I)
SKIP_HEAD = re.compile(r'async|update|attend|transcript', re.I)


def _public_site():
    v = os.environ.get('NOTION_PUBLIC_SITE')
    return PUBLIC_SITE if v is None else v.rstrip('/')


def _site_post(site, path, body):
    req = urllib.request.Request(site + '/api/v3/' + path, data=json.dumps(body).encode(), method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('User-Agent', 'fips-dashboard (public governance tracker)')
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))


def _val(rec):
    """recordMap entries are {value: X} or {value: {value: X}} depending on API version."""
    v = (rec or {}).get('value') or {}
    return v.get('value') if isinstance(v.get('value'), dict) else v


def _uuid(hex_id):
    h = hex_id.replace('-', '')
    return f'{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}'


def _chunk(site, page_id):
    return _site_post(site, 'loadPageChunk', {'pageId': page_id, 'limit': 500, 'cursor': {'stack': []},
                                              'chunkNumber': 0, 'verticalColumns': False})


def _rich(segments):
    """(text, hrefs) from Notion's internal rich text. People mentions are dropped."""
    text, hrefs = [], []
    for seg in segments or []:
        s, ann = seg[0], (seg[1] if len(seg) > 1 else [])
        keep = True
        for a in ann:
            if a[0] in ('u', 'p', 'd', 'ui'):  # user, page, date mentions: not published
                keep = False
            elif a[0] == 'a' and len(a) > 1:
                hrefs.append(a[1])
            elif a[0] == 'lm' and len(a) > 1 and isinstance(a[1], dict):
                hrefs.append(a[1].get('href'))
                s = a[1].get('title') or ''
        if keep and s != '‣':
            text.append(s)
    return ''.join(text), [h for h in hrefs if h]


def _topic(text):
    """An agenda line fit to publish: no proposer names, no raw URLs, no legends."""
    t = re.sub(r'https?://\S+', '', text or '')
    t = re.sub(r'^\s*\([^)]{1,40}\)\s*', '', t)          # "(Steve) nv29 update" -> "nv29 update"
    t = re.sub(r'\s+', ' ', cd._clean_md(t)).strip(' :-–;,')
    if len(t) < 4 or re.match(r'^(XS|S|M|L|XL)\b\s*[:=]', t):
        return None
    return t[:120]


def _page_content(site, page_id):
    """(agenda topics, links, all text) for one public call page."""
    rm = _chunk(site, page_id).get('recordMap', {}).get('block', {})
    get = lambda i: _val(rm.get(i))
    topics, links, texts = [], [], []
    section = None

    def walk(bid, depth):
        nonlocal section
        b = get(bid)
        if not b:
            return
        t = b.get('type', '')
        text, hrefs = _rich((b.get('properties') or {}).get('title'))
        links.extend(hrefs)
        src = (b.get('format') or {}).get('display_source') or ((b.get('properties') or {}).get('source') or [[None]])[0][0]
        if src and t in ('video', 'embed', 'bookmark'):
            links.append(src)
        if t in ('header', 'sub_header', 'sub_sub_header') and depth == 0:
            section = 'agenda' if AGENDA_HEAD.search(text) else ('skip' if SKIP_HEAD.search(text) else 'other')
        if section != 'skip':
            texts.append(text)
            if section == 'agenda' and depth == 0 and t in ('bulleted_list', 'numbered_list', 'to_do'):
                topic = _topic(text)
                if topic:
                    topics.append(topic)
        # Don't descend into tables (the async-update grid) or into sub-pages.
        if t not in ('table', 'collection_view', 'collection_view_page', 'page'):
            for k in b.get('content') or []:
                walk(k, depth + 1)

    root = get(_uuid(page_id))
    for k in (root or {}).get('content') or []:
        walk(k, 0)
    return topics, links, '\n'.join(texts)


def load_from_public_site():
    site = _public_site()
    db = (os.environ.get('NOTION_MEETINGS_DB') or DEFAULT_DB).replace('-', '')
    rm = _chunk(site, _uuid(db)).get('recordMap', {})
    page = _val(rm.get('block', {}).get(_uuid(db)))
    if not page:
        raise RuntimeError('database page is not public')
    space = page.get('space_id')
    coll_id = (page.get('collection_id') or next(iter(rm.get('collection', {})), None))
    view_ids = page.get('view_ids') or list(rm.get('collection_view', {}))
    if not coll_id or not view_ids:
        raise RuntimeError('database has no public view')
    q = _site_post(site, 'queryCollection?src=initial_load', {
        'source': {'type': 'collection', 'id': coll_id, 'spaceId': space},
        'collectionView': {'id': view_ids[0], 'spaceId': space},
        'loader': {'type': 'reducer', 'reducers': {'collection_group_results': {'type': 'results', 'limit': 500}},
                   'searchQuery': '', 'userTimeZone': 'UTC'}})
    ids = q['result']['reducerResults']['collection_group_results']['blockIds']
    blocks = q.get('recordMap', {}).get('block', {})
    rows = []
    for bid in ids:
        b = _val(blocks.get(bid)) or {}
        title, _ = _rich((b.get('properties') or {}).get('title'))
        if not _keep(title, []):
            continue
        clean = re.sub(r'(\d)\s*-\s*(\d)', r'\1-\2', title)  # "2026-11- 03" -> "2026-11-03"
        date = cd.parse_date(clean)
        if not date and b.get('created_time'):
            date = datetime.fromtimestamp(b['created_time'] / 1000, tz=timezone.utc)
        rows.append((bid, re.sub(r'\s+', ' ', clean).strip(), date))
    rows.sort(key=lambda r: r[2] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    calls = []
    for i, (bid, title, date) in enumerate(rows):
        topics, links, text = [], [], ''
        if i < BODY_LIMIT:
            try:
                topics, links, text = _page_content(site, bid)
            except Exception as e:
                print(f'Warning: could not read public page {bid}: {e}')
        urls = [(_classify_url('', h), h) for h in links if _classify_url('', h) == 'recording']
        c = _call(title, date, [], urls, '; '.join(topics[:4]), f'{site}/{bid.replace("-", "")}',
                  text + '\n' + '\n'.join(links))
        c['topics'] = topics
        calls.append(c)
    return calls


# ---------------------------------------------------------------------------

def load_calls():
    """(calls newest first, source) where source is 'public', 'notion', 'csv' or None.
    Returns ([], None) when no source is available."""
    if _public_site():
        try:
            calls = load_from_public_site()
            print(f'Loaded {len(calls)} implementers calls from {_public_site()}')
            return calls, 'public'
        except Exception as e:
            print(f'Warning: could not read the public Notion site ({e}); trying other sources')
    if os.environ.get('NOTION_TOKEN'):
        try:
            calls = load_from_notion()
            print(f'Loaded {len(calls)} implementers calls from Notion')
            return calls, 'notion'
        except urllib.error.HTTPError as e:
            hint = (' (share the Meetings database with the integration)' if e.code == 404 else '')
            print(f'Warning: Notion API returned {e.code}{hint}; trying the CSV export')
        except Exception as e:
            print(f'Warning: could not read Notion ({e}); trying the CSV export')
    if os.path.isfile(CSV_PATH):
        calls = load_from_csv()
        print(f'Loaded {len(calls)} implementers calls from {os.path.relpath(CSV_PATH)}')
        return calls, 'csv'
    print('No implementers call source (set NOTION_TOKEN or add data/implementers-calls.csv)')
    return [], None


if __name__ == '__main__':
    calls, src = load_calls()
    for c in calls[:20]:
        d = c['date'].strftime('%Y-%m-%d') if c['date'] else '—'
        print(f'{d}  {c["title"]}  {", ".join(c["types"])}  FIPs: {", ".join(c["fips"]) or "—"}')
