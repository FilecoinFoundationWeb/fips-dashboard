#!/usr/bin/env python3
"""editors.html: an unlisted checklist for FIP editors.

Not in the nav, footer or sitemap, and marked noindex. The header search
offers it only when someone types "editor". It gathers signals from the public
records that may need an editor's attention: Last Calls past their review
date, shipped FIPs still marked Accepted, README/file status mismatches (FIPs
and FRCs), idle pull requests, quiet Drafts and open FIPs with no discussion
link. Prompts, not judgments; editors decide under FIP-0001.

The public pages deliberately don't show these signals (see extras.py).
"""

from datetime import datetime, timedelta, timezone

import re

import fip_utils as u
from fip_utils import html_escape as esc

IDLE_PR_DAYS = 30
QUIET_DRAFT_DAYS = 365
RECENT_CHANGE_DAYS = 30     # status changes listed under "Recently moved"
MAX_REVIEW_LOOKUPS = 30     # review-state API calls per build, for the proposals list
RECENT_CALL_DAYS = 90        # a Draft discussed in a call this recently counts as active
DISCUSSION_MIN_COMMENTS = 5  # engagement for an idea discussion to be listed as a possible Draft
DISCUSSION_MIN_UPVOTES = 5
DISCUSSION_ACTIVE_DAYS = 180

IDEAS_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    discussions(first: 100, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes { number title url createdAt updatedAt closed upvoteCount
              author { login } category { name } comments { totalCount } }
    }
  }
}
"""


def fetch_ideas():
    """Up to 100 recently active FIPs-repo discussions with upvotes, or None (needs GITHUB_TOKEN)."""
    data = u.github_graphql(IDEAS_QUERY, {'owner': 'filecoin-project', 'name': 'FIPs'})
    try:
        nodes = data['repository']['discussions']['nodes']
    except (TypeError, KeyError):
        return None
    out = []
    for d in nodes:
        out.append({'number': d['number'], 'title': d['title'], 'url': d['url'], 'closed': d.get('closed'),
                    'updated': datetime.fromisoformat(d['updatedAt'].replace('Z', '+00:00')),
                    'author': (d.get('author') or {}).get('login', 'ghost'),
                    'category': (d.get('category') or {}).get('name', ''),
                    'comments': (d.get('comments') or {}).get('totalCount', 0), 'upvotes': d.get('upvoteCount', 0)})
    return out


REPO = 'https://github.com/filecoin-project/FIPs'
TOOLS = [
    ('Open pull requests', f'{REPO}/pulls', 'Everything waiting on the FIPs repo'),
    ('PRs with no review yet', f'{REPO}/pulls?q=is%3Apr+is%3Aopen+review%3Anone', 'GitHub filter: open and unreviewed'),
    ('Discussions', f'{REPO}/discussions', 'Ideas and FIP threads'),
    ('FIP-0001', f'{REPO}/blob/master/FIPS/fip-0001.md', 'The process: stages, criteria and editor duties'),
    ('FIP template', f'{REPO}/blob/master/templates/template.md', 'What a new Draft should contain'),
    ('README table', f'{REPO}/blob/master/README.md', 'Where statuses are recorded'),
    ('Core Devs agenda issues', 'https://github.com/filecoin-project/core-devs/issues', 'Add a FIP to the next meeting'),
]


def _days(n):
    return f'{n} day{"s" if n != 1 else ""}'


def _last_activity(n, ctx):
    dates = [h['since'] for h in ctx['history'].get(n) or []]
    dates += [m['date'] for m in ctx['meetings'] if m['date'] and n in m['fips']]
    dates += [c['date'] for c in ctx.get('calls') or [] if c['date'] and n in c['fips']]
    for p in (ctx.get('prs_by_fip') or {}).get(n) or []:
        try:
            dates.append(datetime.fromisoformat(p['updated_at'].replace('Z', '+00:00')))
        except (ValueError, KeyError):
            pass
    return max(dates) if dates else None


def editors_page(ctx, page, fip_a, fmt_date):
    now = datetime.now(timezone.utc)
    fips, files = ctx['fips'], ctx['files']

    def section(anchor, title, hint, head, rows, empty):
        body = (f'<div class="table-scroll"><table class="data"><thead><tr>{"".join(f"<th>{h}</th>" for h in head)}</tr></thead>'
                f'<tbody>{"".join(rows)}</tbody></table></div>' if rows else f'<p class="empty">{empty}</p>')
        return (f'<section class="card" id="{anchor}"><div class="card-head"><h2>{title} ({len(rows)})</h2>'
                f'<span class="hint">{hint}</span></div><div class="card-body">{body}</div></section>'), len(rows)

    def title(n):
        return esc((fips.get(n) or files.get(n) or {}).get('title', ''))

    overdue = sorted((w for w in ctx['open_lc'] + (ctx.get('frc_open_lc') or []) if w['end'] < now), key=lambda w: w['end'])
    s1, n1 = section('overdue', 'Last Call review period over',
                     'Still in Last Call after the review-period-end date (or the FIP-0001 default of 14 days, marked est.).',
                     ['FIP', 'Title', 'Review ended', 'Over by', 'Discussion'],
                     [f'<tr><td>{fip_a(w["number"])}</td><td class="title-cell">{esc(w["title"])}</td>'
                      f'<td class="nowrap">{fmt_date(w["end"])}{" (est.)" if w["estimated_end"] else ""}</td>'
                      f'<td class="num">{_days(max(1, (now - w["end"]).days))}</td>'
                      f'<td>{"<a href=" + chr(34) + esc(w["discussions"][0]) + chr(34) + " target=_blank rel=noopener>Thread</a>" if w["discussions"] else "—"}</td></tr>'
                      for w in overdue], 'Every Last Call is within its review period.')

    shipped = {}
    for x in ctx['upgrades']:
        for f in x['fips']:
            shipped.setdefault(f, x)
    waiting_final = [n for n, f in sorted(fips.items()) if f['status'] == 'Accepted' and n in shipped
                     and shipped[n]['mainnet'] and shipped[n]['mainnet'] <= now]
    s2, n2 = section('final', 'Live on mainnet, still Accepted',
                     'Shipped in an activated upgrade but not marked Final. It may be intentional (FIP-0001 also asks for a spec update).',
                     ['FIP', 'Title', 'Shipped in', 'Mainnet'],
                     [f'<tr><td>{fip_a(n)}</td><td class="title-cell">{title(n)}</td>'
                      f'<td>NV{shipped[n]["number"]} {esc(shipped[n]["name"])}</td><td class="nowrap">{fmt_date(shipped[n]["mainnet"])}</td></tr>'
                      for n in waiting_final], 'No shipped FIPs are waiting to be marked Final.')

    mism = u.status_mismatches(fips, files)
    for m in u.status_mismatches(ctx.get('frcs') or {}, ctx.get('frc_files') or {}):
        if m['note'].startswith('No FIPS/'):
            m['note'] = f'No FRCs/frc-{m["number"]}.md file'
        mism.append(m)
    mism.sort(key=lambda m: int(m['number']))
    s3, n3 = section('mismatch', 'README and file disagree',
                     'The README table and the FIP or FRC file\'s own <code>status:</code> line differ, or it is in only one of them. '
                     'The dashboard doesn\'t say which is right.',
                     ['FIP / FRC', 'Title', 'README', 'File', 'Note'],
                     [f'<tr><td>{fip_a(m["number"])}</td><td class="title-cell">{esc(m["title"])}</td>'
                      f'<td>{esc(m["readme"] or "—")}</td><td>{esc(m["file"] or "—")}</td><td class="small">{esc(m["note"])}</td></tr>'
                      for m in mism], 'The README and every FIP and FRC file agree.')

    prs = sorted((p for p in ctx.get('prs') or [] if p['idle_days'] >= IDLE_PR_DAYS), key=lambda p: -p['idle_days'])
    pr_note = '' if ctx.get('prs') is not None else ' Pull requests couldn\'t be loaded on this run.'
    s4, n4 = section('idle-prs', f'Pull requests idle {IDLE_PR_DAYS}+ days',
                     'Open PRs on the FIPs repo with no activity for a month or more.' + pr_note,
                     ['PR', 'FIPs', 'Author', 'Idle'],
                     [f'<tr><td class="title-cell"><a href="{esc(p["url"])}" target="_blank" rel="noopener">#{p["number"]} {esc(p["title"])}</a>'
                      f'{" <span class=pill>draft</span>" if p["draft"] else ""}</td>'
                      f'<td>{" ".join(fip_a(x) for x in p["fip_numbers"] if x != "General") or "General"}</td>'
                      f'<td>@{esc(p["author"])}</td><td class="num">{_days(p["idle_days"])}</td></tr>' for p in prs],
                     'No PRs have been idle that long.' if ctx.get('prs') is not None else
                     'Pull requests couldn\'t be loaded on this run, so this list is empty.')

    quiet = []
    for n, f in sorted(fips.items()):
        if f['status'] != 'Draft':
            continue
        last = _last_activity(n, ctx)
        if last and (now - last).days >= QUIET_DRAFT_DAYS:
            quiet.append((n, last))
    s5, n5 = section('quiet', 'Drafts with no activity for a year',
                     'No status change, call mention or PR activity in the records for 12 months. Authors may still be working on them.',
                     ['FIP', 'Title', 'Last recorded activity'],
                     [f'<tr><td>{fip_a(n)}</td><td class="title-cell">{title(n)}</td><td class="nowrap">{fmt_date(last)}</td></tr>'
                      for n, last in sorted(quiet, key=lambda x: x[1])], 'Every Draft has recent activity.')

    nodisc = [n for n, f in sorted(files.items()) if not f.get('_discussions')
              and (fips.get(n) or {}).get('status', f.get('_status')) in ('Draft', 'Last Call', 'Accepted')]
    s6, n6 = section('no-discussion', 'Open FIPs with no discussion link',
                     'Draft, Last Call or Accepted FIPs whose file has no <code>discussions-to</code> URL, so the dashboard can\'t point people to comment.',
                     ['FIP', 'Title', 'Status'],
                     [f'<tr><td>{fip_a(n)}</td><td class="title-cell">{title(n)}</td><td>{esc((fips.get(n) or {}).get("status", ""))}</td></tr>'
                      for n in nodisc], 'Every open FIP links to a discussion.')

    # --- Review queues ---------------------------------------------------
    all_files = {**(ctx.get('frc_files') or {}), **files}
    all_rows = {**(ctx.get('frcs') or {}), **fips}

    # 1. Idea discussions with traction that no FIP or FRC links to yet
    ideas = ctx['_ideas'] if '_ideas' in ctx else fetch_ideas()
    linked = set()
    for f in all_files.values():
        for url in f.get('_discussions') or []:
            m = re.search(r'/discussions/(\d+)', url)
            if m:
                linked.add(int(m.group(1)))
    ready_draft = []
    for d in ideas or []:
        if d['closed'] or d['number'] in linked or re.search(r'\bF(IP|RC)[-\s]?0*\d+', d['title'], re.I) and \
                any(int(x) == int(n) for x in re.findall(r'F(?:IP|RC)[-\s]?0*(\d+)', d['title'], re.I) for n in all_rows):
            continue
        if (now - d['updated']).days > DISCUSSION_ACTIVE_DAYS:
            continue
        if d['comments'] >= DISCUSSION_MIN_COMMENTS or d['upvotes'] >= DISCUSSION_MIN_UPVOTES:
            ready_draft.append(d)
    ready_draft.sort(key=lambda d: -(d['comments'] + d['upvotes']))
    disc_note = '' if ideas is not None else ' Discussions couldn\'t be loaded on this run.'
    q1, m1 = section('ready-draft', 'Discussions that may be ready for a FIP draft',
                     f'Open discussions in the FIPs repo with {DISCUSSION_MIN_COMMENTS}+ comments or {DISCUSSION_MIN_UPVOTES}+ upvotes, '
                     f'active in the last {DISCUSSION_ACTIVE_DAYS} days, that no FIP or FRC links to yet. Traction, not consensus.' + disc_note,
                     ['Discussion', 'Category', 'Author', 'Comments', 'Upvotes', 'Last active'],
                     [f'<tr><td class="title-cell"><a href="{esc(d["url"])}" target="_blank" rel="noopener">#{d["number"]} {esc(d["title"])}</a></td>'
                      f'<td class="small">{esc(d["category"])}</td><td>@{esc(d["author"])}</td>'
                      f'<td class="num">{d["comments"]}</td><td class="num">{d["upvotes"]}</td><td class="nowrap">{fmt_date(d["updated"])}</td></tr>'
                      for d in ready_draft],
                     'No idea discussions meet the bar right now.' if ideas is not None else
                     'Discussions couldn\'t be loaded on this run (the build needs GITHUB_TOKEN), so this list is empty.')

    # 2. New proposals waiting as pull requests (a number with no merged file yet, or a PR adding one)
    new_prs = []
    for p in ctx.get('prs') or []:
        nums = [x for x in p['fip_numbers'] if x != 'General']
        unmerged = [x for x in nums if x not in all_files and x not in all_rows]
        if unmerged or (not nums and re.search(r'\b(add|new|propos)', p['title'], re.I)):
            new_prs.append((p, unmerged))
    new_prs.sort(key=lambda x: x[0]['created_at'])
    for p, _ in new_prs[:MAX_REVIEW_LOOKUPS]:
        if p.get('review') in (None, 'Unknown'):
            p['review'] = u.fetch_review_state(p['number'], p['draft'])
    q2, m2 = section('new-proposals', 'New proposals waiting on review',
                     'Open pull requests that add a FIP or FRC not yet merged into the repo. Oldest first.' + pr_note,
                     ['PR', 'Number', 'Author', 'Review', 'Opened', 'Updated'],
                     [f'<tr><td class="title-cell"><a href="{esc(p["url"])}" target="_blank" rel="noopener">#{p["number"]} {esc(p["title"])}</a>'
                      f'{" <span class=pill>draft</span>" if p["draft"] else ""}</td>'
                      f'<td>{", ".join(esc(x) for x in un) or "—"}</td><td>@{esc(p["author"])}</td>'
                      f'<td class="small">{esc(p.get("review") or "Unknown")}</td>'
                      f'<td class="nowrap">{esc(p["created_at"][:10])}</td><td class="nowrap">{esc(p["updated_at"][:10])}</td></tr>'
                      for p, un in new_prs],
                     'No new proposals are waiting as pull requests.' if ctx.get('prs') is not None else
                     'Pull requests couldn\'t be loaded on this run, so this list is empty.')

    # 3. Drafts that may be ready for Last Call
    planned = {}
    for p in ctx.get('planning') or []:
        for r in p['scope']:
            if r.get('fip'):
                planned.setdefault(r['fip'], (p['nv'], r.get('readiness'), r.get('readiness_label') or ''))
    lc_ready = []
    for n, row in sorted(all_rows.items(), key=lambda kv: int(kv[0])):
        if row['status'] != 'Draft':
            continue
        signals = []
        for p in (ctx.get('prs_by_fip') or {}).get(n) or []:
            if re.search(r'last[\s-]?call', f'{p["title"]} {p.get("body") or ""}', re.I):
                signals.append(f'<a href="{esc(p["url"])}" target="_blank" rel="noopener">PR #{p["number"]}</a> proposes Last Call')
        if n in planned:
            nv, key, label = planned[n]
            signals.append(f'Candidate for NV{nv}' + (f' ({esc(label)})' if label else ''))
        calls = [c for c in ctx['meetings'] + (ctx.get('calls') or []) if c['date'] and n in c['fips']
                 and (now - c['date']).days <= RECENT_CALL_DAYS]
        if calls:
            last = max(c['date'] for c in calls)
            signals.append(f'Discussed in {len(calls)} call{"s" if len(calls) != 1 else ""} in the last {RECENT_CALL_DAYS} days (latest {fmt_date(last)})')
        if signals:
            strong = any('proposes Last Call' in s for s in signals)
            lc_ready.append((not strong, n, signals))
    lc_ready.sort()
    q3, m3 = section('ready-lc', 'Drafts that may be ready for Last Call',
                     'Draft FIPs and FRCs with an open PR proposing Last Call, a place in the active upgrade planning, '
                     f'or discussion in Core Devs or implementers\' calls in the last {RECENT_CALL_DAYS} days. PR-backed ones first.',
                     ['FIP / FRC', 'Title', 'Signals'],
                     [f'<tr><td>{fip_a(n)}</td><td class="title-cell">{esc(all_rows[n]["title"])}</td>'
                      f'<td class="small">{"<br>".join(sig)}</td></tr>' for _, n, sig in lc_ready],
                     'No Drafts show those signals right now.')

    # --- Tracking ------------------------------------------------------------
    in_lc = sorted((w for w in ctx['open_lc'] + (ctx.get('frc_open_lc') or []) if w['end'] >= now), key=lambda w: w['end'])
    t1, k1 = section('in-lc', 'In Last Call now',
                     'Review windows still open, soonest first.',
                     ['FIP / FRC', 'Title', 'Started', 'Ends', 'Discussion'],
                     [f'<tr><td>{fip_a(w["number"])}</td><td class="title-cell">{esc(w["title"])}</td>'
                      f'<td class="nowrap">{fmt_date(w["start"])}</td>'
                      f'<td class="nowrap">{fmt_date(w["end"])}{" (est.)" if w["estimated_end"] else ""}</td>'
                      f'<td>{"<a href=" + chr(34) + esc(w["discussions"][0]) + chr(34) + " target=_blank rel=noopener>Thread</a>" if w["discussions"] else "—"}</td></tr>'
                      for w in in_lc], 'Nothing is in Last Call right now.')
    cutoff = now - timedelta(days=RECENT_CHANGE_DAYS)
    moved = sorted((e for e in ctx.get('events') or [] if e['date'] >= cutoff), key=lambda e: e['date'], reverse=True)
    t2, k2 = section('recent', f'Moved in the last {RECENT_CHANGE_DAYS} days',
                     'Status changes recorded in the FIPs README table.',
                     ['Date', 'FIP', 'Title', 'Change'],
                     [f'<tr><td class="nowrap">{fmt_date(e["date"])}</td><td>{fip_a(e["number"])}</td><td class="title-cell">{esc(e["title"])}</td>'
                      f'<td>{esc(e["from"] or "new")} → {esc(e["to"] or "removed")} '
                      f'<a class="small" href="https://github.com/{u.FIPS_REPO}/commit/{e["sha"]}" target="_blank" rel="noopener">commit</a></td></tr>'
                      for e in moved], 'No status changes in that time.')
    agenda = (ctx.get('agenda') or [])[:1]
    agenda_html = (f'<p class="note" style="margin-top:10px">Next Core Devs agenda: <a href="{esc(agenda[0]["url"])}" target="_blank" rel="noopener">'
                   f'#{agenda[0]["number"]} {esc(agenda[0]["title"])}</a> ({agenda[0]["comments"]} comments).</p>' if agenda else '')
    tools = ('<section class="card" id="tools"><div class="card-head"><h2>Editor tools</h2></div><div class="card-body"><div class="links-grid">'
             + ''.join(f'<a class="link-card" href="{esc(url)}" target="_blank" rel="noopener"><strong>{esc(lbl)} ↗</strong><span>{esc(d)}</span></a>'
                       for lbl, url, d in TOOLS)
             + f'</div>{agenda_html}</div></section>')

    counts = [('ready-draft', 'Ideas ready to draft', m1 if ideas is not None else '—'),
              ('new-proposals', 'New proposals', m2 if ctx.get('prs') is not None else '—'),
              ('ready-lc', 'Drafts ready for LC?', m3),
              ('overdue', 'Last Calls over', n1), ('final', 'Awaiting Final', n2), ('mismatch', 'Status mismatches', n3),
              ('idle-prs', 'Idle PRs', n4 if ctx.get('prs') is not None else '—'), ('quiet', 'Quiet Drafts', n5),
              ('no-discussion', 'No discussion link', n6)]
    stats = '<section class="stats">' + ''.join(
        f'<a class="stat{" accent" if isinstance(v, int) and v and k in ("ready-draft", "new-proposals", "ready-lc") else ""}" href="#{k}">'
        f'<div class="label">{esc(lbl)}</div><div class="value">{v}</div></a>' for k, lbl, v in counts) + '</section>'
    intro = ('<section class="card"><div class="card-body" style="padding-top:18px">'
             '<p>Signals from the public records that may need an editor\'s attention. They are prompts, not judgments: '
             'each one links to the FIP so you can check the context. Editors decide status changes under '
             '<a href="https://github.com/filecoin-project/FIPs/blob/master/FIPS/fip-0001.md" target="_blank" rel="noopener">FIP-0001</a>.</p>'
             '<p class="note">This page is unlisted: it isn\'t in the menu and search engines are asked not to index it. '
             'Find it again by typing <strong>editor</strong> in the search box. Anyone with the link can still open it.</p>'
             '</div></section>')
    queues = '<h2 style="margin:22px 2px 0;font-size:.82rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)">To review</h2>'
    tracking = '<h2 style="margin:22px 2px 0;font-size:.82rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)">Tracking</h2>'
    checks = '<h2 style="margin:22px 2px 0;font-size:.82rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)">Housekeeping</h2>'
    body = '\n'.join([stats, intro, tools, queues, q1, q2, q3, tracking, t1, t2, checks, s1, s2, s3, s4, s5, s6])
    return page(title='Editor checklist',
                description='Signals for FIP editors from the public records.',
                current='editors', subtitle='One place for FIP editors: what to review, what is moving, and what needs tidying.',
                body_html=body, path='editors.html', noindex=True)
