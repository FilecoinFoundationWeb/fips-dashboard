#!/usr/bin/env python3
"""Build an internal (unpublished) FIPs report: internal/fips-internal-report.html.

The public dashboard only lists FIPs that changed status in the last year.
This report lists every in-flight FIP with its full time in status, plus the
complete Last Call history, for the team's own follow-up.

It is written to internal/, which is gitignored and never committed by the
auto-update workflow, so it is not published to GitHub Pages. Run it locally
and share the file directly.
"""

import os
import statistics
from datetime import datetime, timezone

import fip_utils as u
from fip_utils import html_escape as esc
from theme import CSS, FONT_LINK
from generate_fips_dashboard import (IN_FLIGHT, badge, fip_link, date_str, age_cell,
                                     discussion_links, mismatch_html)

OUTPUT_DIR = 'internal'
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'fips-internal-report.html')

EXTRA_CSS = """
.internal-banner { background: var(--warn-bg); border-bottom: 1px solid var(--warn-border); color: var(--text);
  padding: 10px 0; font-size: .9rem; font-weight: 600; }
.site-header { padding-bottom: 40px; }
.age.old { color: var(--rejected-fg); } .age.mid { color: var(--lastcall-fg); }
"""


def aged(days):
    if days is None:
        return '<span class="age">unknown</span>'
    cls = 'old' if days >= 365 else 'mid' if days >= 180 else ''
    return f'<span class="age {cls}">{esc(u.humanize_days(days))}</span>'


def in_flight_full(fips, history, files, grouped, prs_loaded=True):
    rows = []
    for num, f in fips.items():
        if f['status'] not in IN_FLIGHT:
            continue
        since = u.current_status_since(history, num, f['status'])
        days = u.days_between(since) if since else None
        meta = files.get(num, {})
        n = len(grouped.get(num, []))
        rows.append((days if days is not None else 10 ** 6, f'''<tr>
<td>{fip_link(num)}</td><td class="title-cell">{esc(f["title"])}</td><td>{esc(f["authors"])}</td>
<td>{badge(f["status"])}</td><td class="nowrap">{date_str(since)}</td><td>{aged(days)}</td>
<td>{discussion_links(meta.get("_discussions", []))}</td><td class="num">{n if prs_loaded else '—'}</td></tr>'''))
    rows.sort(key=lambda r: r[0], reverse=True)
    over = sum(1 for d, _ in rows if d > 365)
    return f'''<section class="card"><div class="card-head"><h2>All in-flight FIPs ({len(rows)})</h2>
<span class="hint">{over} have been in the same status for over a year. These are left off the public page.</span></div>
<div class="card-body"><div class="table-scroll"><table class="data">
<thead><tr><th>FIP</th><th>Title</th><th>Authors</th><th>Status</th><th>Since</th><th>Time in status</th><th>Discussion</th><th class="num">Open PRs</th></tr></thead>
<tbody>{"".join(r for _, r in rows)}</tbody></table></div></div></section>'''


def last_call_history(open_lc, past_lc):
    durations = [w['days'] for w in past_lc]
    summary = ''
    if durations:
        summary = (f'<p class="note">{len(durations)} past Last Calls. Median {statistics.median(durations):.0f} days, '
                   f'shortest {min(durations)}, longest {max(durations)}. '
                   f'{sum(1 for d in durations if d < 14)} were shorter than the usual 14 days in the README '
                   '(the README often lags the actual decision).</p>')
    rows = ''.join(f'''<tr><td>{fip_link(w["number"])}</td><td class="title-cell">{esc(w["title"])}</td>
<td class="nowrap">{date_str(w["start"])}</td><td class="nowrap">{date_str(w["exit"])}</td>
<td class="num">{w["days"]}</td><td>{badge(w["outcome"])}</td></tr>''' for w in past_lc)
    open_rows = ''.join(f'<li>{fip_link(w["number"])} {esc(w["title"])}, since {date_str(w["start"])}</li>' for w in open_lc)
    return f'''<section class="card"><div class="card-head"><h2>Last Call history</h2>
<span class="hint">Every Last Call in the README history, newest first.</span></div>
<div class="card-body">{f"<p><strong>Open now:</strong></p><ul style='margin:6px 0 12px 20px'>{open_rows}</ul>" if open_rows else '<p class="empty">Nothing in Last Call right now.</p>'}
<div class="table-scroll"><table class="data">
<thead><tr><th>FIP</th><th>Title</th><th>Entered</th><th>Left</th><th class="num">Days</th><th>Moved to</th></tr></thead>
<tbody>{rows}</tbody></table></div>{summary}</div></section>'''


def stale_prs(processed):
    stale = sorted((p for p in processed if p['idle_days'] >= 30), key=lambda p: -p['idle_days'])
    if not stale:
        return ''
    rows = ''.join(f'''<tr><td><a href="{esc(p["url"])}" target="_blank" rel="noopener">#{p["number"]}</a></td>
<td class="title-cell">{esc(p["title"])}</td><td>@{esc(p["author"])}</td><td>{esc(p["review"])}</td>
<td class="num">{p["idle_days"]}</td></tr>''' for p in stale)
    return f'''<section class="card"><div class="card-head"><h2>PRs idle 30+ days ({len(stale)})</h2></div>
<div class="card-body"><div class="table-scroll"><table class="data">
<thead><tr><th>PR</th><th>Title</th><th>Author</th><th>Review</th><th class="num">Days idle</th></tr></thead>
<tbody>{rows}</tbody></table></div></div></section>'''


def main():
    repo = u.get_fips_repo()
    fips = {f['number']: f for f in u.parse_fip_table(u.read_readme(repo))}
    if not fips:
        print('ERROR: No FIPs parsed.')
        return 1
    history, _ = u.build_status_history(repo)
    files = u.load_fip_files(repo)
    open_lc, past_lc = u.last_call_windows(history, files, fips)
    raw = u.fetch_open_prs()
    processed = u.process_prs(raw)
    grouped = u.prs_by_fip(processed)

    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    pr_note = '' if raw is not None else '<div class="callout" style="margin-top:20px">Couldn\'t load PRs from the GitHub API on this run, so PR counts are missing.</div>'
    body = '\n'.join([pr_note, in_flight_full(fips, history, files, grouped, raw is not None), last_call_history(open_lc, past_lc),
                      mismatch_html(u.status_mismatches(fips, files)), stale_prs(processed)])

    html = f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"><meta name="robots" content="noindex">
<meta name="color-scheme" content="light dark"><title>FIPs internal report</title>{FONT_LINK}
<style>{CSS}{EXTRA_CSS}</style></head><body>
<div class="internal-banner"><div class="wrap">Internal: not published. Generated {stamp} from the public FIPs repo.</div></div>
<header class="site-header"><div class="wrap"><span class="eyebrow">Filecoin governance</span>
<h1>FIPs internal report</h1><p class="sub">Full time-in-status for every in-flight FIP, complete Last Call history and stale PRs.</p></div></header>
<main><div class="wrap">{body}</div></main>
<footer class="site-footer"><div class="wrap"><p>Generated by <code>internal_report.py</code>. Kept out of the published site.</p></div></footer>
</body></html>'''
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'Internal report: {OUTPUT_FILE}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
