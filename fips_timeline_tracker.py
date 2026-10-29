#!/usr/bin/env python3
"""Generate the FIP status timeline (fips-timeline-tracker.html).

Every status change is read from the README's full git history in a local
clone of filecoin-project/FIPs, so changes within the same month are all
shown with their exact date (no API pagination limits, no monthly sampling).
"""

from collections import defaultdict, OrderedDict
from datetime import datetime, timezone

import fip_utils as u
from fip_utils import html_escape as esc
from theme import page

OUTPUT_FILE = 'fips-timeline-tracker.html'
RECENT_MONTHS = 24


def badge(status):
    return f'<span class="status-badge {u.get_status_class(status)}">{esc(status)}</span>'


def event_html(e):
    link = f'<a class="fip-id" href="{esc(u.fip_url(e["number"]))}" target="_blank" rel="noopener">FIP-{esc(e["number"])}</a>'
    title = esc(e['title'][:70] + ('…' if len(e['title']) > 70 else ''))
    commit = f'https://github.com/{u.FIPS_REPO}/commit/{e["sha"]}'
    if e['from'] is None:
        change = f'<strong>Listed</strong> as {badge(e["to"])}'
    elif e['to'] is None:
        change = f'<strong>Removed</strong> from README (was {badge(e["from"])})'
    else:
        change = f'{badge(e["from"])}<span class="arrow">→</span>{badge(e["to"])}'
    return (f'<div class="tl-event"><time datetime="{e["date"].isoformat()}">'
            f'<a href="{esc(commit)}" target="_blank" rel="noopener" title="README commit">{e["date"].strftime("%b %d")}</a></time>'
            f'<div>{link} {title}<div style="margin-top:4px">{change}</div></div></div>')


def months_html(events):
    by_month = OrderedDict()
    for e in sorted(events, key=lambda e: e['date'], reverse=True):
        by_month.setdefault(e['date'].strftime('%Y-%m'), []).append(e)
    blocks = []
    for key, evs in by_month.items():
        label = datetime.strptime(key, '%Y-%m').strftime('%B %Y')
        blocks.append(f'<div class="tl-month"><h3>{label} <span>{len(evs)} change{"s" if len(evs) != 1 else ""}</span></h3>'
                      f'<div class="tl-events">{"".join(event_html(e) for e in evs)}</div></div>')
    return blocks


def main():
    print('Cloning / updating filecoin-project/FIPs...')
    repo = u.get_fips_repo()
    current = {f['number']: f for f in u.parse_fip_table(u.read_readme(repo))}
    if not current:
        print('ERROR: No FIPs parsed. Aborting to avoid overwriting existing tracker.')
        return 1

    print('Walking README history...')
    _, events = u.build_status_history(repo)
    # The very first parsed snapshot lists every FIP at once; that's the
    # baseline, not a burst of new proposals.
    first_date = min(e['date'] for e in events) if events else None
    events = [e for e in events if not (e['from'] is None and e['date'] == first_date)]
    print(f'{len(events)} status events since {first_date:%Y-%m-%d}' if first_date else 'No events')

    now = datetime.now(timezone.utc)
    cutoff = f'{now.year - RECENT_MONTHS // 12:04d}-{now.month:02d}'
    recent = [e for e in events if e['date'].strftime('%Y-%m') >= cutoff]
    older = [e for e in events if e['date'].strftime('%Y-%m') < cutoff]

    counts = defaultdict(int)
    for f in current.values():
        counts[f['status']] += 1
    summary = '<section class="stats compact">' + ''.join(
        f'<div class="stat"><div class="label">{esc(s)}</div><div class="value">{n}</div></div>'
        for s, n in sorted(counts.items(), key=lambda x: -x[1])
    ) + '</section>'

    moves = defaultdict(int)
    for e in recent:
        if e['from'] and e['to']:
            moves[(e['from'], e['to'])] += 1
    move_rows = ''.join(
        f'<tr><td>{badge(a)}<span class="arrow" style="margin:0 6px">→</span>{badge(b)}</td><td class="num"><strong>{n}</strong></td></tr>'
        for (a, b), n in sorted(moves.items(), key=lambda x: -x[1])
    )
    moves_card = f'''<section class="card"><div class="card-head"><h2>Transitions, last {RECENT_MONTHS} months</h2>
<span class="hint">How FIPs have been moving through the process.</span></div>
<div class="card-body">{f'<div class="table-scroll"><table class="data"><thead><tr><th>Change</th><th class="num">Count</th></tr></thead><tbody>{move_rows}</tbody></table></div>' if move_rows else '<p class="empty">No transitions in this period.</p>'}</div></section>'''

    recent_blocks = months_html(recent)
    older_blocks = months_html(older)
    older_html = (f'<details class="more"><summary>Earlier history ({len(older)} changes back to {first_date:%B %Y})</summary>'
                  f'<div class="timeline" style="margin-top:14px">{"".join(older_blocks)}</div></details>') if older else ''
    timeline_card = f'''<section class="card"><div class="card-head"><h2>Status changes</h2>
<span class="hint">Every change to the README's status column, dated by commit. Click a date to see the commit.</span></div>
<div class="card-body"><div class="timeline">{"".join(recent_blocks) or '<p class="empty">No changes recently.</p>'}</div>{older_html}</div></section>'''

    html = page(
        title='FIP Status Timeline',
        description='Every Filecoin Improvement Proposal status change, dated from the FIPs README git history.',
        current='timeline',
        subtitle='Every status change in the FIPs README, dated by commit, back to the start of the table.',
        body_html='\n'.join([summary, moves_card, timeline_card]),
    )
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'Timeline generated: {OUTPUT_FILE}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
