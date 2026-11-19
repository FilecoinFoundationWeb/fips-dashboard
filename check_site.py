#!/usr/bin/env python3
"""Check the built site before it's published. Exits non-zero on a problem.

Run after the generators (the workflows do this). Checks that:
  * every page exists and isn't suspiciously empty
  * every internal link and image on every page points at a file that exists
  * feed.xml parses, calendar.ics follows the format (line length, unique IDs)
  * fips-index.json and data.json are valid and list the same FIPs
Stdlib only.
"""

import glob
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

PAGES = ['index.html', 'overview.html', 'fips-dashboard-static.html', 'fips-timeline-tracker.html',
         'core-devs.html', 'implementers.html', 'network-upgrades.html', 'frcs.html']
MIN_FIP_PAGES = 50


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for key in ('href', 'src'):
            if a.get(key) and tag in ('a', 'img', 'link', 'script'):
                self.refs.append(a[key])


def check():
    problems = []
    for p in PAGES:
        if not os.path.exists(p):
            problems.append(f'missing page {p}')
        elif os.path.getsize(p) < 5000:
            problems.append(f'{p} is only {os.path.getsize(p)} bytes')

    fip_pages = [f for f in glob.glob('fip/*.html') if not f.endswith('index.html')]
    if len(fip_pages) < MIN_FIP_PAGES:
        problems.append(f'only {len(fip_pages)} FIP pages (expected at least {MIN_FIP_PAGES})')

    checked = 0
    for page in sorted(glob.glob('*.html') + glob.glob('fip/*.html') + glob.glob('frc/*.html')):
        parser = Links()
        with open(page, encoding='utf-8') as f:
            parser.feed(f.read())
        here = os.path.dirname(page)
        for ref in parser.refs:
            if re.match(r'^(https?:|mailto:|data:|#|javascript:|//)', ref):
                continue
            target = ref.split('#')[0].split('?')[0]
            path = os.path.normpath(os.path.join(here, target)) if target else page
            if target in ('', './', '../') or target.endswith('/'):
                path = os.path.join(path, 'index.html') if target else page
            checked += 1
            if not os.path.exists(path):
                problems.append(f'{page}: broken link {ref}')

    try:
        items = ET.parse('feed.xml').getroot().findall('.//item')
        if not items:
            problems.append('feed.xml has no items')
    except (OSError, ET.ParseError) as e:
        problems.append(f'feed.xml: {e}')

    try:
        with open('calendar.ics', encoding='utf-8', newline='') as f:
            ics = f.read()
        if not ics.startswith('BEGIN:VCALENDAR\r\n') or 'END:VCALENDAR' not in ics:
            problems.append('calendar.ics is not a calendar')
        long = [l for l in ics.split('\r\n') if len(l.encode('utf-8')) > 75]
        if long:
            problems.append(f'calendar.ics has {len(long)} lines over 75 octets')
        uids = re.findall(r'^UID:(.*)$', ics.replace('\r\n ', ''), re.M)
        if len(uids) != len(set(uids)):
            problems.append('calendar.ics has duplicate UIDs')
    except OSError as e:
        problems.append(f'calendar.ics: {e}')

    try:
        with open('fips-index.json', encoding='utf-8') as f:
            entries = [x for x in json.load(f) if not x.get('u')]  # 'u': open-PR proposals, no page
        index = {x['n'] for x in entries if x.get('k') != 'FRC'}
        frc_index = {x['n'] for x in entries if x.get('k') == 'FRC'}
        with open('data.json', encoding='utf-8') as f:
            d = json.load(f)
        data, frc_data = {x['number'] for x in d['fips']}, {x['number'] for x in d.get('frcs', [])}
        if index != data:
            problems.append(f'fips-index.json and data.json disagree on {len(index ^ data)} FIPs')
        if frc_index != frc_data:
            problems.append(f'fips-index.json and data.json disagree on {len(frc_index ^ frc_data)} FRCs')
        missing = [n for n in index if not os.path.exists(f'fip/{n}.html')] + \
                  [n for n in frc_index if not os.path.exists(f'frc/{n}.html')]
        if missing:
            problems.append(f'no page for {len(missing)} FIPs/FRCs, e.g. {missing[:3]}')
    except (OSError, ValueError, KeyError) as e:
        problems.append(f'JSON files: {e}')

    print(f'Checked {len(PAGES)} main pages, {len(fip_pages)} FIP pages and {checked} internal links.')
    for p in problems[:50]:
        print(f'PROBLEM: {p}')
    if len(problems) > 50:
        print(f'... and {len(problems) - 50} more')
    print('OK' if not problems else f'{len(problems)} problem(s)')
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(check())
