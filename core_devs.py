#!/usr/bin/env python3
"""Read Core Devs meetings and network upgrades from filecoin-project/core-devs.

Sources (all public, read-only):
  * README.md "Recent Meetings" table: date, agenda, notes and recording links
  * Core Dev Meetings/*.md: meeting notes (topics, FIP mentions, older dates
    and recordings for meetings that predate the README table)
  * upgrades.json: every network upgrade with its FIPs and activation times
  * Network Upgrades/vNN.md: per-upgrade write-ups (linked)
  * open issues: the agenda issue for the next meeting (GitHub API, optional)
"""

import json
import os
import re
from datetime import datetime, timezone

import fip_utils as u

CORE_DEVS_REPO = 'filecoin-project/core-devs'
CORE_DEVS_GIT_URL = f'https://github.com/{CORE_DEVS_REPO}.git'
CORE_DEVS_BLOB = f'https://github.com/{CORE_DEVS_REPO}/blob/master/'
NOTES_DIR = 'Core Dev Meetings'

MONTHS = ('january february march april may june july august september october '
          'november december').split()


def get_core_devs_repo(path=None):
    return u.get_repo(CORE_DEVS_GIT_URL, 'CORE_DEVS_REPO_DIR', 'core-devs-src', path)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _first_link(cell):
    m = re.search(r'\[([^\]]*)\]\((https?://[^)\s]+)\)', cell or '')
    return (m.group(1), m.group(2)) if m else (None, None)


def parse_date(text):
    """Find the first date in free text. Handles the formats used in the notes:
    2021-01-28 · Thursday, September 1, 2022 · August 5th, 2026 ·
    Thursday 28 January 2021 · Thursday 3, August 2023."""
    if not text:
        return None
    m = re.search(r'(20\d\d)-(\d\d)-(\d\d)', text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except ValueError:
            pass
    low = text.lower()
    month = r'(' + '|'.join(MONTHS) + r')'
    m = re.search(month + r'\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d)', low)
    if m:
        return datetime(int(m.group(3)), MONTHS.index(m.group(1)) + 1, int(m.group(2)), tzinfo=timezone.utc)
    m = re.search(r'(\d{1,2})(?:st|nd|rd|th)?,?\s+' + month + r',?\s+(20\d\d)', low)
    if m:
        return datetime(int(m.group(3)), MONTHS.index(m.group(2)) + 1, int(m.group(1)), tzinfo=timezone.utc)
    return None


def youtube_id(url):
    if not url:
        return None
    m = re.search(r'(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/|live/))([A-Za-z0-9_-]{11})', url)
    return m.group(1) if m else None


def fip_mentions(text):
    """Unique FIP numbers mentioned in text (FRCs excluded)."""
    nums = set()
    for m in re.finditer(r'(?<![A-Za-z])FIP[\s#-]?0*(\d{1,4})\b', text or '', re.IGNORECASE):
        n = int(m.group(1))
        if 0 < n < 10000:
            nums.add(f'{n:04d}')
    return nums


def notes_topics(text, limit=10):
    """Topics from a notes file: the Agenda section's bullets when present,
    otherwise the second-level headings."""
    lines = (text or '').split('\n')
    bullets, in_agenda = [], False
    for line in lines:
        if re.match(r'^#{1,3}\s', line):
            heading = re.sub(r'^#+\s*(\d+\.\s*)?', '', line).strip()
            if in_agenda and bullets:
                break
            in_agenda = heading.lower().startswith('agenda')
            continue
        if in_agenda:
            m = re.match(r'^\s*[-*]\s+(.*\S)', line)
            if m:
                bullets.append(_clean_md(m.group(1)))
    if bullets:
        return bullets[:limit]
    heads = []
    for line in lines:
        m = re.match(r'^##\s+(?:\d+\.\s*)?(.*\S)', line)
        if m:
            h = _clean_md(m.group(1))
            low = h.lower().rstrip(':')
            if low in ('agenda', 'attendance', 'attendees', 'notes', 'action items', 'next steps',
                       'summary', 'updates for the week', 'timezones', 'meeting overview'):
                continue
            if 'summary' in low or low.startswith(('core devs', 'filecoin core devs')) or 'timezone' in low:
                continue
            heads.append(h)
    return heads[:limit]


def _facilitator(head):
    m = re.search(r'Facilitator:?\**\s*([^\n*]+)', head)
    return m.group(1).strip().rstrip('\\').strip() if m else None


def _clean_md(s):
    s = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', s)
    s = re.sub(r'[*_`]', '', s)
    return s.strip().rstrip(':').strip()


# ---------------------------------------------------------------------------
# Meetings
# ---------------------------------------------------------------------------

def _readme_rows(repo):
    with open(os.path.join(repo, 'README.md'), encoding='utf-8', errors='replace') as f:
        text = f.read()
    rows = {}
    for line in text.split('\n'):
        if not line.strip().startswith(('|', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9')):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) < 2 or not re.fullmatch(r'\d{1,4}', cells[0]):
            continue
        num = int(cells[0])
        date_cell, agenda, notes, rec = (cells + ['', '', '', ''])[1:5]
        _, agenda_url = _first_link(agenda)
        _, notes_url = _first_link(notes)
        rec_label, rec_url = _first_link(rec)
        passcode = None
        m = re.search(r'passcode:?\s*([^\s\]\)|]+)', rec, re.IGNORECASE) or \
            re.search(r'passcode:?\s*([^\s\])|]+)', rec_label or '', re.IGNORECASE)
        if m:
            passcode = m.group(1)
        note = None
        plain_agenda = re.sub(r'\[[^\]]*\]\([^)]*\)', '', agenda).strip()
        if plain_agenda:
            note = plain_agenda  # e.g. "Meeting Cancelled", "Brussels Convening"
        rows[num] = {
            'date': parse_date(date_cell), 'agenda_url': agenda_url, 'notes_url': notes_url,
            'recording_url': rec_url, 'passcode': passcode, 'note': note,
            'unrecorded': 'unrecorded' in date_cell.lower(),
        }
    return rows


def _notes_files(repo):
    out = {}
    d = os.path.join(repo, NOTES_DIR)
    if not os.path.isdir(d):
        return out
    for name in os.listdir(d):
        m = re.search(r'(\d{1,4})\.md$', name)
        if not m:
            continue
        with open(os.path.join(d, name), encoding='utf-8', errors='replace') as f:
            text = f.read()
        head = '\n'.join(text.split('\n')[:20])
        rec = re.search(r'Recording:?\**\s*(?:\[[^\]]*\]\()?(https?://\S+?)[)\s]', head + '\n')
        out[int(m.group(1))] = {
            'file_url': CORE_DEVS_BLOB + f'{NOTES_DIR}/{name}'.replace(' ', '%20'),
            'date': parse_date(head),
            'recording_url': rec.group(1) if rec else None,
            'topics': notes_topics(text),
            'fips': fip_mentions(text),
            'facilitator': _facilitator(head),
        }
    return out


def load_meetings(repo):
    """All meetings, newest first, merging the README table with notes files."""
    rows, notes = _readme_rows(repo), _notes_files(repo)
    meetings = []
    for num in sorted(set(rows) | set(notes), reverse=True):
        r, n = rows.get(num, {}), notes.get(num, {})
        notes_url = r.get('notes_url') or n.get('file_url')
        rec = r.get('recording_url') or n.get('recording_url')
        meetings.append({
            'number': num,
            'date': r.get('date') or n.get('date'),
            'agenda_url': r.get('agenda_url'),
            'notes_url': notes_url,
            'notes_kind': ('slides' if notes_url and 'docs.google.com' in notes_url else 'notes') if notes_url else None,
            'recording_url': rec,
            'youtube_id': youtube_id(rec),
            'passcode': r.get('passcode'),
            'note': r.get('note'),
            'topics': n.get('topics', []),
            'fips': sorted(n.get('fips', set())),
            'facilitator': (n.get('facilitator') or '').strip() or None,
        })
    return meetings


def last_discussed(meetings):
    """{fip_number: most recent meeting dict that mentions it}."""
    out = {}
    for m in meetings:  # newest first
        for f in m['fips']:
            out.setdefault(f, m)
    return out


def fip_meeting_counts(meetings, since=None):
    counts = {}
    for m in meetings:
        if since and (not m['date'] or m['date'] < since):
            continue
        for f in m['fips']:
            counts[f] = counts.get(f, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Network upgrades
# ---------------------------------------------------------------------------

def _ts(value):
    if isinstance(value, dict):
        value = value.get('time')
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None


def load_upgrades(repo):
    """Network upgrades, newest first."""
    path = os.path.join(repo, 'upgrades.json')
    if not os.path.isfile(path):
        return []
    with open(path, encoding='utf-8') as f:
        data = json.load(f).get('networkUpgrades', [])
    out = []
    for up in data:
        num = up.get('upgrade')
        try:
            num = int(num)
        except (TypeError, ValueError):
            pass
        act = up.get('activation') or {}
        doc = os.path.join(repo, 'Network Upgrades', f'v{num}.md')
        out.append({
            'number': num,
            'name': up.get('name') or '',
            'actors': up.get('actorsVersion') or '',
            'fips': [str(x).zfill(4) for x in up.get('fips') or []],
            'mainnet': _ts(act.get('mainnet')),
            'mainnet_epoch': (act.get('mainnet') or {}).get('epoch') if isinstance(act.get('mainnet'), dict) else None,
            'calibration': _ts(act.get('calibrationnet') or act.get('calibration')),
            'doc_url': CORE_DEVS_BLOB + f'Network%20Upgrades/v{num}.md' if os.path.isfile(doc) else None,
        })
    def _order(x):
        try:
            return float(x['number'])
        except (TypeError, ValueError):
            return -1.0
    out.sort(key=_order, reverse=True)
    return out


def fip_upgrades(upgrades):
    """{fip_number: upgrade dict} for FIPs shipped in a network upgrade."""
    out = {}
    for up in upgrades:
        for f in up['fips']:
            out.setdefault(f, up)
    return out


# ---------------------------------------------------------------------------
# Next meeting agenda (GitHub API, optional)
# ---------------------------------------------------------------------------

def fetch_open_agenda():
    """Open agenda issues on core-devs, newest first, or None if unavailable."""
    try:
        issues = u.make_github_request(
            f'https://api.github.com/repos/{CORE_DEVS_REPO}/issues?state=open&per_page=30')
    except Exception as e:
        print(f'Warning: Could not fetch core-devs issues: {e}')
        return None
    out = []
    for i in issues:
        if i.get('pull_request'):
            continue
        title = i.get('title') or ''
        if 'agenda' not in title.lower() and 'meeting' not in title.lower():
            continue
        out.append({'number': i['number'], 'title': title, 'url': i['html_url'],
                    'comments': i.get('comments', 0),
                    'created': datetime.fromisoformat(i['created_at'].replace('Z', '+00:00'))})
    out.sort(key=lambda x: x['created'], reverse=True)
    return out
