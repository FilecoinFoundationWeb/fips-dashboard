#!/usr/bin/env python3
"""Generate the static FIPs dashboard (fips-dashboard-static.html).

Data sources (all read-only):
  * a local clone of filecoin-project/FIPs: README table, its full git
    history, and each FIP file's front matter
  * the GitHub API: open pull requests, the files they touch, their reviews
"""

from collections import defaultdict
from datetime import datetime, timezone

import fip_utils as u
from fip_utils import html_escape as esc
from theme import page

OUTPUT_FILE = 'fips-dashboard-static.html'

# Statuses where a FIP is still moving through the process.
IN_FLIGHT = ('Draft', 'Last Call', 'Accepted', 'Deferred')
STATUS_ORDER = ['Last Call', 'Draft', 'Accepted', 'Deferred', 'Active', 'Final',
                'Superseded', 'Withdrawn', 'Rejected']


def badge(status):
    return f'<span class="status-badge {u.get_status_class(status)}">{esc(status)}</span>'


def fip_link(num):
    return f'<a class="fip-id" href="{esc(u.fip_url(num))}" target="_blank" rel="noopener">FIP-{esc(num)}</a>'


def date_str(d):
    return d.strftime('%Y-%m-%d') if d else '—'


def age_cell(days):
    if days is None:
        return '<span class="age">—</span>'
    return f'<span class="age">{esc(u.humanize_days(days))}</span>'


def discussion_links(urls):
    if not urls:
        return '<span class="pill">none listed</span>'
    out = []
    for i, url in enumerate(urls):
        label = 'Discussion' if len(urls) == 1 else f'Discussion {i + 1}'
        out.append(f'<a href="{esc(url)}" target="_blank" rel="noopener">{label}</a>')
    return ' · '.join(out)


def review_pill(state):
    cls = ('approved' if state.startswith('Approved') else
           'changes' if state == 'Changes requested' else
           'waiting' if state == 'Awaiting review' else '')
    return f'<span class="pill {cls}">{esc(state)}</span>'


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def stats_html(fips, open_lc, prs, prs_loaded=True):
    counts = defaultdict(int)
    for f in fips.values():
        counts[f['status']] += 1
    cards = [
        ('Total FIPs', len(fips), False),
        ('In Last Call', len(open_lc), bool(open_lc)),
        ('Draft', counts['Draft'], False),
        ('Accepted', counts['Accepted'], False),
        ('Final', counts['Final'], False),
        ('Open PRs', len({p['number'] for p in prs}) if prs or prs_loaded else '—', False),
    ]
    return '<section class="stats">' + ''.join(
        f'<div class="stat{" accent" if accent else ""}"><div class="label">{esc(label)}</div>'
        f'<div class="value">{value}</div></div>'
        for label, value, accent in cards
    ) + '</section>'


def last_call_html(open_lc, past_lc):
    now = datetime.now(timezone.utc)
    if open_lc:
        rows = []
        for w in open_lc:
            left = (w['end'] - now).days
            left_txt = f'{left} days left' if left > 0 else ('ends today' if left == 0 else f'ended {-left} days ago')
            est = ' <span class="pill est" title="No review-period-end set; FIP-0001 default of 14 days">est.</span>' if w['estimated_end'] else ''
            rows.append(f'''<tr>
<td>{fip_link(w["number"])}</td><td class="title-cell">{esc(w["title"])}</td>
<td class="nowrap">{date_str(w["start"])}</td>
<td class="nowrap">{date_str(w["end"])}{est}</td>
<td class="nowrap"><strong>{esc(left_txt)}</strong></td>
<td>{discussion_links(w["discussions"])}</td></tr>''')
        current = f'''<div class="table-scroll"><table class="data">
<thead><tr><th>FIP</th><th>Title</th><th>Entered</th><th>Review ends</th><th>Window</th><th>Where to comment</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>'''
    else:
        current = '<p class="empty">No FIPs are in Last Call right now.</p>'

    past_rows = ''.join(f'''<tr>
<td>{fip_link(w["number"])}</td><td class="title-cell">{esc(w["title"])}</td>
<td class="nowrap">{date_str(w["start"])}</td><td class="nowrap">{date_str(w["exit"])}</td>
<td class="num">{w["days"]}</td><td>{badge(w["outcome"])}</td></tr>''' for w in past_lc[:10])
    past = ''
    if past_lc:
        past = f'''<details class="more"><summary>Recent Last Calls ({min(10, len(past_lc))} of {len(past_lc)})</summary>
<div class="table-scroll" style="margin-top:10px"><table class="data">
<thead><tr><th>FIP</th><th>Title</th><th>Entered</th><th>Left</th><th class="num">Days</th><th>Moved to</th></tr></thead>
<tbody>{past_rows}</tbody></table></div></details>'''

    return f'''<section class="card" id="last-call">
<div class="card-head"><h2>Last Call</h2>
<span class="hint">The final review window before a FIP moves on. Per FIP-0001, editors set a review end date, normally 14 days out. Dates here are when the README showed the change.</span></div>
<div class="card-body">{current}{past}</div></section>'''


IN_FLIGHT_MAX_DAYS = 365


def in_flight_html(fips, history, files, prs_grouped):
    """In-flight FIPs that changed status within the last year.

    Longer-running FIPs are left out of the table and only counted in a
    footnote, so the page doesn't spotlight how long individual proposals
    have been waiting. They still appear under "All FIPs by status".
    """
    rows = []
    older = 0
    for num, f in fips.items():
        if f['status'] not in IN_FLIGHT:
            continue
        since = u.current_status_since(history, num, f['status'])
        days = u.days_between(since) if since else None
        if days is None or days > IN_FLIGHT_MAX_DAYS:
            older += 1
            continue
        meta = files.get(num, {})
        pr_count = len(prs_grouped.get(num, []))
        rows.append((days, f'''<tr>
<td>{fip_link(num)}</td><td class="title-cell">{esc(f["title"])}</td>
<td>{badge(f["status"])}</td>
<td class="nowrap">{date_str(since)}</td><td>{age_cell(days)}</td>
<td>{discussion_links(meta.get("_discussions", []))}</td>
<td class="num">{f'<a href="#pr-{num}">{pr_count}</a>' if pr_count else '0'}</td></tr>'''))
    rows.sort(key=lambda r: r[0])
    body = (f'''<div class="table-scroll"><table class="data">
<thead><tr><th>FIP</th><th>Title</th><th>Status</th><th>Since</th><th>Time in status</th><th>Discussion</th><th class="num">Open PRs</th></tr></thead>
<tbody>{"".join(r[1] for r in rows)}</tbody></table></div>''' if rows
            else '<p class="empty">No FIPs have changed status in the last year.</p>')
    if older:
        body += (f'<p class="note">* {older} other in-flight FIP{"s have" if older != 1 else " has"} '
                 'been in the same status for more than a year and '
                 f'{"are" if older != 1 else "is"} not listed here. '
                 'See <a href="#by-status">All FIPs by status</a>.</p>')
    return f'''<section class="card" id="in-flight">
<div class="card-head"><h2>In flight</h2>
<span class="hint">Draft, Last Call, Accepted and Deferred FIPs that changed status in the last year, most recent first.*</span></div>
<div class="card-body">{body}</div></section>'''


def mismatch_html(mismatches):
    if not mismatches:
        body = '<p class="empty">README and FIP files agree on every status.</p>'
    else:
        rows = ''.join(f'''<tr>
<td>{fip_link(m["number"])}</td><td class="title-cell">{esc(m["title"])}</td>
<td>{badge(m["readme"]) if m["readme"] else '<span class="pill">not listed</span>'}</td>
<td>{badge(m["file"]) if m["file"] else '<span class="pill">no file</span>'}</td>
<td>{esc(m["note"])}</td></tr>''' for m in mismatches)
        body = f'''<div class="table-scroll"><table class="data">
<thead><tr><th>FIP</th><th>Title</th><th>README says</th><th>FIP file says</th><th>Note</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<p class="note">Flagged for FIP editors to look at. The dashboard doesn't decide which one is right.</p>'''
    return f'''<section class="card" id="consistency">
<div class="card-head"><h2>Consistency check</h2>
<span class="hint">Compares the README table with the <code>status:</code> line in each FIP's own file.</span></div>
<div class="card-body">{body}</div></section>'''


def by_status_html(fips, prs_grouped):
    groups = defaultdict(list)
    for num, f in fips.items():
        groups[f['status']].append(num)
    order = [s for s in STATUS_ORDER if s in groups] + sorted(s for s in groups if s not in STATUS_ORDER)
    rows = []
    for status in order:
        chips = []
        for num in sorted(groups[status], key=int):
            n = len(prs_grouped.get(num, []))
            dot = f' <span class="pr-dot" title="{n} open PR{"s" if n != 1 else ""}">{n}</span>' if n else ''
            chips.append(f'<a class="chip" href="{esc(u.fip_url(num))}" target="_blank" rel="noopener" '
                         f'title="{esc(fips[num]["title"])}">FIP-{num}{dot}</a>')
        rows.append(f'<tr><td>{badge(status)}</td><td class="num"><strong>{len(groups[status])}</strong></td>'
                    f'<td><div class="chips">{"".join(chips)}</div></td></tr>')
    return f'''<section class="card" id="by-status">
<div class="card-head"><h2>All FIPs by status</h2><span class="hint">FRCs are excluded. Blue dots show open PRs.</span></div>
<div class="card-body"><div class="table-scroll"><table class="data">
<thead><tr><th>Status</th><th class="num">Count</th><th>FIPs</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div></div></section>'''


def prs_html(prs_grouped, fips, loaded=True):
    unique = {pr['number'] for prs in prs_grouped.values() for pr in prs}
    if not loaded:
        body = ('<div class="callout">Couldn\'t load pull requests from the GitHub API on this run '
                '(rate limit or network). They\'ll reappear on the next update.</div>')
    elif not unique:
        body = '<p class="empty">No open PRs found.</p>'
    else:
        keys = sorted((k for k in prs_grouped if k != 'General'), key=int)
        if 'General' in prs_grouped:
            keys.append('General')
        groups = []
        for key in keys:
            if key == 'General':
                head = '<h3>General FIP-related</h3>'
                anchor = 'pr-general'
            else:
                status = fips.get(key, {}).get('status')
                t = fips.get(key, {}).get("title", "")
                pill = f'<span class="pill">{esc(t[:80])}</span>' if t else '<span class="pill">not yet in README</span>'
                head = f'<h3>{fip_link(key)} {badge(status) if status else ""} {pill}</h3>'
                anchor = f'pr-{key}'
            items = []
            for pr in sorted(prs_grouped[key], key=lambda p: p['updated_at'], reverse=True):
                idle = pr['idle_days']
                items.append(f'''<div class="pr-item">
<a href="{esc(pr["url"])}" target="_blank" rel="noopener">#{pr["number"]}: {esc(pr["title"])}</a>
<span class="pr-meta">{review_pill(pr["review"])}<span>@{esc(pr["author"])}</span>
<span>opened {esc(pr["created_at"][:10])}</span>
<span>{"active today" if idle == 0 else f"idle {idle} day" + ("s" if idle != 1 else "")}</span></span></div>''')
            groups.append(f'<div class="pr-group" id="{anchor}">{head}{"".join(items)}</div>')
        body = ''.join(groups)
    return f'''<section class="card" id="prs">
<div class="card-head"><h2>Open pull requests ({len(unique)})</h2>
<span class="hint">Matched to FIPs by the files each PR changes, then by title. Review state is the latest decisive review from each reviewer.</span></div>
<div class="card-body">{body}</div></section>'''


# ---------------------------------------------------------------------------

def main():
    print('Cloning / updating filecoin-project/FIPs...')
    repo = u.get_fips_repo()

    fips = {f['number']: f for f in u.parse_fip_table(u.read_readme(repo))}
    print(f'Found {len(fips)} FIPs in README')
    if not fips:
        print('ERROR: No FIPs parsed. Aborting to avoid overwriting existing dashboard.')
        return 1

    print('Reading README history and FIP files...')
    history, _ = u.build_status_history(repo)
    files = u.load_fip_files(repo)
    open_lc, past_lc = u.last_call_windows(history, files, fips)
    mismatches = u.status_mismatches(fips, files)

    print('Fetching open PRs and reviews...')
    raw_prs = u.fetch_open_prs()
    processed = u.process_prs(raw_prs)
    grouped = u.prs_by_fip(processed)
    print(f'{len(processed)} FIP-related PR(s); {len(open_lc)} in Last Call; {len(mismatches)} mismatch(es)')

    body = '\n'.join([
        stats_html(fips, open_lc, processed, prs_loaded=raw_prs is not None),
        last_call_html(open_lc, past_lc),
        in_flight_html(fips, history, files, grouped),
        mismatch_html(mismatches),
        prs_html(grouped, fips, loaded=raw_prs is not None),
        by_status_html(fips, grouped),
    ])

    html = page(
        title='Filecoin Improvement Proposals',
        description='Read-only dashboard of Filecoin Improvement Proposals: status, time in status, Last Call windows, open PRs and review state.',
        current='dashboard',
        subtitle='Where every FIP stands, how long it has been there, and what is waiting on review.',
        body_html=body,
    )
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'Dashboard generated: {OUTPUT_FILE}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
