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
import scope_planning as sp
from fip_utils import html_escape as esc

IDLE_PR_DAYS = 30
QUIET_DRAFT_DAYS = 365
RECENT_CHANGE_DAYS = 30     # status changes listed under "Recently moved"
MAX_REVIEW_LOOKUPS = 60     # PRs whose reviews are fetched per build
EDITOR_APPROVALS_NEEDED = 2 # FIP editor approvals a PR needs before it is merged
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


def fip_editors(repo):
    """FIP editors' GitHub logins, from the FIPs repo's CODEOWNERS file."""
    try:
        with open(f'{repo or ""}/CODEOWNERS', encoding='utf-8') as f:
            return set(re.findall(r'@([A-Za-z0-9-]+)', f.read()))
    except OSError:
        return set()


def review_info(raw_prs, editors):
    """{pr number: who approved, who asked for changes, which editors are requested}.

    Uses the latest decisive review per person; an author's own review doesn't count.
    None when PRs couldn't be loaded.
    """
    editors = {e.lower() for e in editors}
    if raw_prs is None:
        return None
    out = {}
    for pr in [p for p in raw_prs if not p.get('draft')][:MAX_REVIEW_LOOKUPS]:
        author = (pr.get('user') or {}).get('login', '')
        try:
            reviews = u._paged(f'{u.GITHUB_API_BASE}/pulls/{pr["number"]}/reviews')
        except Exception as e:
            print(f'Warning: Could not fetch reviews for PR #{pr["number"]}: {e}')
            continue
        latest = {}
        for r in reviews:
            who = (r.get('user') or {}).get('login', '')
            if who and who != author and r.get('state') in ('APPROVED', 'CHANGES_REQUESTED', 'DISMISSED'):
                latest[who] = r['state']
        approved = [w for w, st in latest.items() if st == 'APPROVED']
        out[pr['number']] = {
            'editor_ok': sorted(w for w in approved if w.lower() in editors),
            'other_ok': sorted(w for w in approved if w.lower() not in editors),
            'changes': sorted(w for w, st in latest.items() if st == 'CHANGES_REQUESTED'),
            'requested': sorted(x['login'] for x in pr.get('requested_reviewers') or [] if x['login'].lower() in editors),
            'author_is_editor': author.lower() in editors,
        }
    return out


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
    editors = fip_editors(ctx.get('fips_repo'))
    raw = ctx['_raw_prs'] if '_raw_prs' in ctx else (u.fetch_open_prs() if ctx.get('prs') is not None else None)
    reviews = ctx['_reviews'] if '_reviews' in ctx else review_info(raw, editors)

    # 0. PRs waiting on FIP editor approval
    def who(names):
        return ', '.join('@' + esc(x) for x in names) or '—'
    waiting = []
    for p in ctx.get('prs') or []:
        info = (reviews or {}).get(p['number'])
        if p['draft'] or not info or len(info['editor_ok']) >= EDITOR_APPROVALS_NEEDED:
            continue
        waiting.append((p, info))
    # Closest to merge first: most editor approvals, then technical approvals, then oldest
    waiting.sort(key=lambda x: (-len(x[1]['editor_ok']), -len(x[1]['other_ok']), x[0]['created_at']))
    rows = []
    for p, info in waiting:
        need = EDITOR_APPROVALS_NEEDED - len(info['editor_ok'])
        state = (f'<span class="pill waiting">changes requested by {who(info["changes"])}</span>' if info['changes']
                 else f'<strong>needs {need} more</strong>')
        nums = ' '.join(fip_a(x) for x in p['fip_numbers'] if x != 'General') or 'General'
        rows.append(f'<tr><td class="title-cell"><a href="{esc(p["url"])}" target="_blank" rel="noopener">#{p["number"]} {esc(p["title"])}</a>'
                    f'<div class="muted small">{nums} · by @{esc(p["author"])} · updated {esc(p["updated_at"][:10])}</div></td>'
                    f'<td class="nowrap">{len(info["editor_ok"])} / {EDITOR_APPROVALS_NEEDED}<div class="muted small">{who(info["editor_ok"])}</div></td>'
                    f'<td class="small">{who(info["other_ok"])}</td><td class="small">{state}</td>'
                    f'<td class="small">{who(info["requested"])}</td></tr>')
    rev_note = '' if reviews is not None else ' Pull requests couldn\'t be loaded on this run.'
    q0, m0 = section('approvals', 'Waiting on FIP editor approval',
                     f'Open, non-draft PRs on the FIPs repo with fewer than {EDITOR_APPROVALS_NEEDED} approvals from FIP editors '
                     '(the CODEOWNERS list). Closest to merge first; "Other approvals" are reviewers who aren\'t editors, '
                     'such as technical reviewers.' + rev_note,
                     ['Pull request', 'Editor approvals', 'Other approvals', 'Status', 'Requested editors'],
                     rows, 'Every open PR has its editor approvals.' if reviews is not None else
                     'Pull requests couldn\'t be loaded on this run, so this list is empty.')
    all_files = {**(ctx.get('frc_files') or {}), **files}
    all_rows = {**(ctx.get('frcs') or {}), **fips}

    # 1. Idea discussions with traction that no FIP or FRC links to yet
    ideas = ctx['_ideas'] if '_ideas' in ctx else fetch_ideas()
    disc_re = re.compile(r'github\.com/filecoin-project/FIPs/discussions/(\d+)', re.I)
    drafted = {}   # discussion number -> what already exists for it
    for n, f in all_files.items():
        for url in f.get('_discussions') or []:
            m = disc_re.search(url) or re.search(r'/discussions/(\d+)', url)
            if m:
                drafted.setdefault(int(m.group(1)), u.label(n))
    for pr in raw or []:
        for m in disc_re.finditer(f'{pr.get("title") or ""} {pr.get("body") or ""}'):
            drafted.setdefault(int(m.group(1)), f'PR #{pr["number"]}')
    for plan in ctx.get('planning') or []:
        for row in plan['scope']:
            if row.get('fip'):
                for url in row.get('links') or []:
                    m = disc_re.search(url)
                    if m:
                        drafted.setdefault(int(m.group(1)), u.label(row['fip']))
    in_plan = {}   # discussion number -> NV, for planning rows that only have a discussion
    for plan_ in sp.upcoming(ctx.get('planning'), ctx['upgrades']):
        for row in plan_['scope']:
            for url in row.get('links') or []:
                m = disc_re.search(url)
                if m and row['readiness'] != 'deferred-out':
                    in_plan.setdefault(int(m.group(1)), plan_['nv'])
    ready_draft, skipped = [], 0
    for d in ideas or []:
        if d['closed']:
            continue
        if d['number'] in drafted or re.search(r'\bF(IP|RC)[-\s]?(\d+|X{2,})\b', d['title'], re.I) \
                or re.search(r'\b(FIP|FRC) draft\b|\bdraft (FIP|FRC)\b', d['title'], re.I):
            skipped += 1
            continue
        if (now - d['updated']).days > DISCUSSION_ACTIVE_DAYS:
            continue
        if d['number'] in in_plan or d['comments'] >= DISCUSSION_MIN_COMMENTS or d['upvotes'] >= DISCUSSION_MIN_UPVOTES:
            ready_draft.append(d)
    ready_draft.sort(key=lambda d: (d['number'] not in in_plan, -(d['comments'] + d['upvotes'])))
    disc_note = '' if ideas is not None else ' Discussions couldn\'t be loaded on this run.'
    q1, m1 = section('ready-draft', 'Discussions that may be ready for a FIP draft',
                     f'Open discussions in the FIPs repo with {DISCUSSION_MIN_COMMENTS}+ comments or {DISCUSSION_MIN_UPVOTES}+ upvotes, '
                     f'active in the last {DISCUSSION_ACTIVE_DAYS} days, with no FIP or FRC yet, plus any that upcoming upgrade planning names. '
                     'Ones in planning come first. Traction, not consensus. '
                     f'{skipped} open discussion{"s" if skipped != 1 else ""} skipped because they already have one: a FIP or FRC links to them, '
                     'an open FIPs PR links to them, their title carries a FIP number, or the upgrade planning lists them with a FIP number.' + disc_note,
                     ['Discussion', 'Category', 'Author', 'Comments', 'Upvotes', 'Last active'],
                     [f'<tr><td class="title-cell"><a href="{esc(d["url"])}" target="_blank" rel="noopener">#{d["number"]} {esc(d["title"])}</a>'
                      f'{" <span class=pill>In NV" + str(in_plan[d["number"]]) + " planning</span>" if d["number"] in in_plan else ""}</td>'
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
    for p, _ in new_prs:
        info = (reviews or {}).get(p['number'])
        if p['draft']:
            p['review'] = 'Draft PR'
        elif info:
            p['review'] = (f'Changes requested' if info['changes'] else
                           f'{len(info["editor_ok"])} of {EDITOR_APPROVALS_NEEDED} editor approvals')
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

    # --- Upgrade timetable: everything aimed at the next network upgrade ----
    plan = (sp.active(ctx.get('planning'), ctx['upgrades']) or [None])[0]
    pr_by_num = {p['number']: p for p in ctx.get('prs') or []}
    lc_by_num = {w['number']: w for w in ctx['open_lc'] + (ctx.get('frc_open_lc') or [])}

    def pr_state(p):
        info = (reviews or {}).get(p['number'])
        if p['draft']:
            st = 'draft PR'
        elif not info:
            st = 'review state unknown'
        elif info['changes']:
            st = f'changes requested by {who(info["changes"])}'
        else:
            st = f'{len(info["editor_ok"])}/{EDITOR_APPROVALS_NEEDED} editor approvals'
        return f'<a href="{esc(p["url"])}" target="_blank" rel="noopener">PR #{p["number"]}</a> ({st})'

    def next_step(row):
        n = row.get('fip')
        linked_prs = [pr_by_num[int(m.group(1))] for url in row.get('links') or []
                      if (m := re.search(r'FIPs/pull/(\d+)', url, re.I)) and int(m.group(1)) in pr_by_num]
        prs_for = (ctx.get('prs_by_fip') or {}).get(n, []) if n else []
        prs = list({p['number']: p for p in linked_prs + prs_for}.values())
        status = (all_rows.get(n) or {}).get('status') or ((all_files.get(n) or {}).get('_status') if n else None)
        steps = []
        if not n:
            discs = [url for url in row.get('links') or [] if '/discussions/' in url]
            if prs:
                steps.append('Proposal PR open: ' + ', '.join(pr_state(p) for p in prs))
            elif discs:
                steps.append(f'Only a discussion so far (<a href="{esc(discs[0])}" target="_blank" rel="noopener">thread</a>). '
                             '<strong>Needs a FIP draft.</strong>')
            else:
                steps.append('<span class="muted">No FIP linked in the planning table.</span>')
            return status, steps
        if not status:
            steps.append('<strong>Not merged yet.</strong> ' + (', '.join(pr_state(p) for p in prs) or 'No open PR found.'))
            return status, steps
        if status == 'Draft':
            lc_prs = [p for p in prs if re.search(r'last[\s-]?call', f'{p["title"]} {p.get("body") or ""}', re.I)]
            other = [p for p in prs if p not in lc_prs]
            if other:
                steps.append('Open edits: ' + ', '.join(pr_state(p) for p in other))
            steps.append('Last Call PR: ' + ', '.join(pr_state(p) for p in lc_prs) if lc_prs
                         else '<strong>Needs a PR opening Last Call.</strong>')
        elif status == 'Last Call':
            w = lc_by_num.get(n)
            if w and w['end'] < now:
                steps.append(f'<strong>Review period ended {fmt_date(w["end"])}{" (est.)" if w["estimated_end"] else ""}: ready to move on.</strong>')
            elif w:
                steps.append(f'In Last Call until {fmt_date(w["end"])}{" (est.)" if w["estimated_end"] else ""}.')
        elif status in ('Accepted', 'Final'):
            steps.append(f'{esc(status)}. Nothing for editors.')
        else:
            steps.append(esc(status))
        if prs and status not in ('Draft',):
            steps.append('Open PRs: ' + ', '.join(pr_state(p) for p in prs))
        return status, steps

    order = {'ready': 0, 'risk': 1, 'deferred-in': 2, 'unknown': 3, 'none': 4, 'deferred-out': 5}
    nv_rows, out_of_scope = [], False
    for i, row in sorted(enumerate((plan or {}).get('scope') or []), key=lambda x: (order.get(x[1]['readiness'], 3), x[0])):
        status, steps = next_step(row)
        if row['readiness'] == 'deferred-out' and not out_of_scope:
            out_of_scope = True
            nv_rows.append('<tr><td colspan="5" class="muted small" style="text-align:center;font-weight:600">'
                           'Moved to a later upgrade</td></tr>')
        item = (fip_a(row['fip']) if row.get('fip') else
                (f'<a href="{esc(row["link"])}" target="_blank" rel="noopener">{esc(row.get("link_label") or "link")}</a>' if row.get('link') else '—'))
        detail = ' · '.join(x for x in (esc(row.get('status') or ''), esc(row.get('timeline') or ''),
                                         f'size {esc(row["size"])}' if row.get('size') else '') if x)
        nv_rows.append(f'<tr><td class="nowrap">{item}</td><td class="title-cell">{esc(row["name"])}'
                       f'{"<div class=muted small>" + esc(row["summary"]) + "</div>" if row.get("summary") else ""}</td>'
                       f'<td class="small nowrap">{esc(row["readiness_label"])}</td>'
                       f'<td class="small">{detail or "—"}{"<div class=muted>" + esc(row["notes"]) + "</div>" if row.get("notes") else ""}</td>'
                       f'<td class="small">{"<br>".join(steps)}{"<div class=muted>FIP status: " + esc(status) + "</div>" if status else ""}</td></tr>')
    if plan:
        miles = ' · '.join(f'{esc(m["name"])}: <strong>{esc(m["date"])}</strong>' for m in plan.get('milestones') or [])
        nv_title = f'NV{plan["nv"]} timetable'
        nv_hint = (f'Everything in the <a href="{esc(plan["url"])}" target="_blank" rel="noopener">NV{plan["nv"]} planning discussion</a>, '
                   'with the next step for FIP editors worked out from the FIPs repo and open PRs. Planning status and notes are the planners\' own words.')
        nv_card, nv_count = section('nv', nv_title, nv_hint, ['FIP', 'Item', 'Readiness', 'Planning status', 'Next step for editors'],
                                    nv_rows, 'The planning discussion has no scope table yet.')
        if miles:
            nv_card = nv_card.replace('<div class="card-body">', f'<div class="card-body"><p class="note" style="margin:0 0 12px">{miles}</p>', 1)
    else:
        nv_card, nv_count = ('<section class="card" id="nv"><div class="card-head"><h2>Next upgrade timetable</h2></div>'
                             '<div class="card-body"><p class="empty">'
                             + ('No active upgrade planning discussion found.' if ctx.get('planning') is not None else
                                'The core-devs planning discussion couldn\'t be loaded on this run.')
                             + '</p></div></section>'), 0

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
    editor_list = (f'<p class="note" style="margin-top:10px">FIP editors (from CODEOWNERS): '
                   f'{", ".join("@" + esc(e) for e in sorted(editors))}.</p>' if editors else '')
    tools = ('<section class="card" id="tools"><div class="card-head"><h2>Editor tools</h2></div><div class="card-body"><div class="links-grid">'
             + ''.join(f'<a class="link-card" href="{esc(url)}" target="_blank" rel="noopener"><strong>{esc(lbl)} ↗</strong><span>{esc(d)}</span></a>'
                       for lbl, url, d in TOOLS)
             + f'</div>{agenda_html}{editor_list}</div></section>')

    counts = [('nv', f'NV{plan["nv"]} items' if plan else 'Next upgrade', nv_count if plan else '—'),
              ('approvals', 'Need editor approval', m0 if reviews is not None else '—'),
              ('ready-draft', 'Ideas ready to draft', m1 if ideas is not None else '—'),
              ('new-proposals', 'New proposals', m2 if ctx.get('prs') is not None else '—'),
              ('ready-lc', 'Drafts ready for LC?', m3),
              ('overdue', 'Last Calls over', n1), ('final', 'Awaiting Final', n2), ('mismatch', 'Status mismatches', n3),
              ('idle-prs', 'Idle PRs', n4 if ctx.get('prs') is not None else '—'), ('quiet', 'Quiet Drafts', n5),
              ('no-discussion', 'No discussion link', n6)]
    stats = '<section class="stats">' + ''.join(
        f'<a class="stat{" accent" if isinstance(v, int) and v and k in ("approvals", "ready-draft", "new-proposals", "ready-lc") else ""}" href="#{k}">'
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
    upgrade_h = '<h2 style="margin:22px 2px 0;font-size:.82rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)">Next network upgrade</h2>'
    body = '\n'.join([stats, intro, upgrade_h, nv_card, tools, queues, q0, q1, q2, q3, tracking, t1, t2, checks, s1, s2, s3, s4, s5, s6])
    return page(title='Editor checklist',
                description='Signals for FIP editors from the public records.',
                current='editors', subtitle='One place for FIP editors: what to review, what is moving, and what needs tidying.',
                body_html=body, path='editors.html', noindex=True)
