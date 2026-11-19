#!/usr/bin/env python3
"""One page per FIP, plus the files that help people follow along.

  fip/NNNN.html      everything about one FIP: summary, status path and history,
                     Last Call window, upgrade, calls that discussed it, open PRs
  fip/index.html     redirect to the FIPs page, for anyone who trims the URL
  fips-index.json    number / title / status for the header search box
  feed.xml           RSS: status changes, Last Calls, upgrades and meetings
  calendar.ics       meetings, Last Call review deadlines and upgrade dates
  data.json          every FIP and upgrade as JSON (see extras.py)
  og/*.png           link-preview images, when Pillow is available (og_cards.py)

Also provides this_week_card() for the home page. Called from generate_hub.py
with the context it has already loaded, so nothing is fetched twice.
Read-only like the rest of the dashboard: it reports the records, it doesn't
decide anything.
"""

import json
import os
import re
import zlib
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import extras
import fip_utils as u
import og_cards
from fip_utils import html_escape as esc
from theme import page

OUT_DIR = 'fip'
FEED_DAYS = 120
CALLS_SHOWN = 12

# Short, plain definitions. FIP-0001 is the authority; these are paraphrases.
GLOSSARY = {
    'FIP': 'Filecoin Improvement Proposal: a written proposal to change the protocol, its standards or the governance process.',
    'Draft': 'The FIP has a number and is being refined in the open. Anyone can comment.',
    'Last Call': 'A final review window, normally 14 days, before the FIP is Accepted (core) or Final (everything else).',
    'Accepted': 'A core FIP approved for implementation. It ships in a network upgrade, then becomes Final.',
    'Final': 'Done: implemented and adopted. Only errata are fixed from here.',
    'Core Devs': 'The regular open meeting where implementation and research teams discuss FIPs and upgrade priorities.',
    'Network upgrade': 'A scheduled change to the protocol that all nodes adopt at a set epoch, named NV followed by a number (NV30).',
    'Epoch': 'One 30-second slot of the Filecoin chain. Upgrades activate at a specific epoch.',
    'Implementers': 'The teams that build Filecoin node software (such as Lotus, Venus and Forest) and ship upgrades.',
    'FIP editor': 'Maintainers of the FIPs repo who check proposals for format and move them between statuses.',
}
READY = {'ready': 'ready', 'risk': 'at risk', 'deferred-in': 'carried over', 'deferred-out': 'moved to the next upgrade',
         'none': 'not upgrade-bound', 'unknown': 'in planning'}


def term(word, label=None):
    """A word with its glossary definition on hover/focus."""
    tip = GLOSSARY.get(word)
    text = esc(label or word)
    return f'<abbr class="term" tabindex="0" title="{esc(tip)}">{text}</abbr>' if tip else text


def fmt(d, year=True):
    return d.strftime('%b %-d, %Y' if year else '%b %-d') if d else '—'


def badge(status):
    return f'<span class="status-badge {u.get_status_class(status)}">{esc(status)}</span>'


def ext(url, label, cls='btn'):
    return f'<a class="{cls}" href="{esc(url)}" target="_blank" rel="noopener">{label}</a>'


def short(text, n):
    """Trim to about n characters at a word boundary."""
    text = text or ''
    return text if len(text) <= n else text[:n].rsplit(' ', 1)[0].rstrip(',;:') + '…'


def days_word(n):
    return f'{n} day{"s" if n != 1 else ""}'


# ---------------------------------------------------------------------------
# Reading the FIP's own text
# ---------------------------------------------------------------------------

def _inline_md(text):
    """Escape, then allow links, inline code and bold from the FIP's markdown."""
    out = esc(text)
    out = re.sub(r'`([^`]+)`', r'<code>\1</code>', out)
    out = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', out)
    out = re.sub(r'(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])', r'<em>\1</em>', out)
    out = re.sub(r'\[([^\]]+)\]\((https?://[^)\s]+)\)',
                 lambda m: f'<a href="{m.group(2)}" target="_blank" rel="noopener">{m.group(1)}</a>', out)
    return re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', out)  # relative links: keep the words


def fip_summary(repo, num, limit=900):
    """(html, section name) from the FIP's Simple Summary, else its Abstract."""
    path = os.path.join(repo or '', 'FIPS', f'fip-{num}.md')
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            text = f.read()
    except OSError:
        return '', ''
    text = re.sub(r'^---\n.*?\n---\n', '', text, count=1, flags=re.S)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    for name in ('Simple Summary', 'Abstract', 'Summary'):
        m = re.search(rf'^##+\s*{name}\s*$\n(.*?)(?=^##?\s|\Z)', text, re.M | re.S | re.I)
        if m and m.group(1).strip():
            body = m.group(1).strip()
            break
    else:
        return '', ''
    blocks, used = [], 0
    for para in re.split(r'\n\s*\n', body):
        lines = [l.strip() for l in para.strip().splitlines() if l.strip()]
        if not lines:
            continue
        if re.match(r'^[-*]\s+', lines[0]):
            # A bullet, possibly wrapped over several lines; consecutive bullets share one list.
            items, cur = [], []
            for l in lines:
                if re.match(r'^[-*]\s+', l) and cur:
                    items.append(' '.join(cur)); cur = []
                cur.append(re.sub(r'^[-*]\s+', '', l))
            items.append(' '.join(cur))
            lis = ''.join(f'<li>{_inline_md(i)}</li>' for i in items)
            if blocks and blocks[-1].startswith('<ul class="topics">'):
                blocks[-1] = blocks[-1][:-5] + lis + '</ul>'
            else:
                blocks.append(f'<ul class="topics">{lis}</ul>')
        else:
            blocks.append(f'<p>{_inline_md(" ".join(lines))}</p>')
        used += len(para)
        if used > limit:
            break
    return ''.join(blocks), name


# ---------------------------------------------------------------------------
# Per-FIP page
# ---------------------------------------------------------------------------

def _is_core(fip, f):
    kind = f'{f.get("type", "")} {f.get("category", "")} {fip.get("type", "")}'.lower()
    return 'core' in kind


def status_path(status, history, core):
    """Idea → Draft → Last Call → (Accepted) → Final, with where this FIP is."""
    main = ['Draft', 'Last Call'] + (['Accepted'] if core else []) + ['Final']
    reached = {h['status'] for h in history}
    steps = []
    if status in main:
        i = main.index(status)
        for j, s in enumerate(main):
            steps.append((s, 'done' if j < i else 'now' if j == i else ''))
    else:
        for s in main:
            if s in reached:
                steps.append((s, 'done'))
        steps.append((status, 'now'))
    items = ''.join(f'<li class="{cls}"><span class="dot" aria-hidden="true"></span>{term(s)}'
                    f'{"<span class=visually-hidden> (current)</span>" if cls == "now" else ""}</li>' for s, cls in steps)
    return f'<ol class="path" aria-label="Where this FIP is in the process">{items}</ol>'


def fip_page_html(n, ctx, prev_n, next_n):
    fips, files = ctx['fips'], ctx['files']
    fip, f = fips.get(n) or {}, files.get(n) or {}
    title = fip.get('title') or f.get('title') or f'FIP-{n}'
    status = fip.get('status') or f.get('_status') or 'Draft'
    history = ctx['history'].get(n) or []
    now = datetime.now(timezone.utc)
    B = '../'
    discussions = f.get('_discussions') or []
    discuss = discussions[0] if discussions else 'https://github.com/filecoin-project/FIPs/discussions'
    core = _is_core(fip, f)

    since = u.current_status_since(ctx['history'], n, status)
    in_stage = (now - since).days if since else None

    # Upgrade: shipped, or a candidate in the active planning discussion
    up_html = '<span class="muted">Not in a network upgrade</span>'
    for x in ctx['upgrades']:
        if n in x['fips']:
            live = x['mainnet'] and x['mainnet'] <= now
            up_html = (f'<a href="{B}network-upgrades.html#nv{x["number"]}">NV{x["number"]} {esc(x["name"])}</a> · '
                       f'{"activated" if live else "activates"} on mainnet {fmt(x["mainnet"])}')
            break
    else:
        for p in ctx.get('planning') or []:
            row = next((r for r in p['scope'] if r.get('fip') == n), None)
            if row:
                up_html = (f'Candidate for <a href="{B}network-upgrades.html#plan-nv{p["nv"]}">NV{p["nv"]}</a> '
                           f'({esc(READY.get(row["readiness"], "in planning"))}). Candidates aren\'t commitments.')
                break

    # Calls that mentioned it
    convos = [m for m in ctx['meetings'] if n in m['fips'] and m['date']] + \
             [c for c in ctx.get('calls') or [] if n in c['fips'] and c['date']]
    convos.sort(key=lambda c: c['date'], reverse=True)

    # Call to action
    lc = next((w for w in ctx['open_lc'] if w['number'] == n), None)
    if lc:
        left = (lc['end'].date() - now.date()).days
        est = ' (estimated)' if lc['estimated_end'] else ''
        if left >= 0:
            when = (f'Review ends <strong>{fmt(lc["end"])}</strong>{est}'
                    + (f', {days_word(left)} left' if left else ', today')
                    + '. This is the last chance to raise concerns before the FIP moves on.')
        else:
            when = (f'The review period was due to end <strong>{fmt(lc["end"])}</strong>{est}. '
                    'It stays in Last Call until the FIP editors move it on, so comments still count.')
        cta = (f'<div class="cta"><span><strong>In {term("Last Call")}.</strong> {when}</span>'
               f'{ext(discuss, "Comment on the discussion ↗", "btn primary")}</div>')
    elif status == 'Draft':
        cta = (f'<div class="cta info"><span><strong>Open for feedback.</strong> This FIP is a {term("Draft")}: '
               'questions and suggestions go in its discussion thread.</span>'
               f'{ext(discuss, "Join the discussion ↗", "btn primary")}</div>')
    else:
        cta = ''

    # Summary
    summary, section = fip_summary(ctx.get('fips_repo'), n)
    summary_card = (f'<section class="card"><div class="card-head"><h2>What it proposes</h2>'
                    f'<span class="hint">From the FIP\'s own {esc(section)}.</span></div><div class="card-body">'
                    f'<div class="summary-text">{summary}</div>'
                    f'<div class="btn-row">{ext(u.fip_url(n), "Read the full FIP ↗")}</div></div></section>'
                    if summary else
                    f'<section class="card"><div class="card-head"><h2>What it proposes</h2></div><div class="card-body">'
                    f'<p class="empty">No summary section found in the FIP file.</p>'
                    f'<div class="btn-row">{ext(u.fip_url(n), "Read the full FIP ↗")}</div></div></section>')

    # At a glance
    def listval(v):
        return ', '.join(v) if isinstance(v, list) else (v or '')
    file_status = f.get('_status')
    mismatch = (f' <span class="pill waiting" title="The README table and the FIP file disagree; flagged for editors.">'
                f'file says {esc(file_status)}</span>' if file_status and file_status != status else '')
    requires = [r for r in (f.get('requires') if isinstance(f.get('requires'), list) else
                            re.split(r'[,\s]+', f.get('requires') or '')) if r]
    req_html = ', '.join(u.fip_anchor(m.group(1).zfill(4), base=B) if (m := re.search(r'(\d+)', r)) else esc(r)
                         for r in requires)
    rows = [
        ('Status', f'{badge(status)}{mismatch}'),
        ('In this stage', f'{u.humanize_days(in_stage)} (since {fmt(since)})' if since else '—'),
        ('Type', esc(' · '.join(x for x in (listval(f.get('type')) or fip.get('type', ''), listval(f.get('category'))) if x)) or '—'),
        ('Authors', esc(listval(f.get('author')) or fip.get('authors', '')) or '—'),
        ('Created', esc(listval(f.get('created'))) or '—'),
        ('Network upgrade', up_html),
        ('Requires', req_html),
        ('Discussion', ' · '.join(ext(d, f'Thread {i + 1}' if len(discussions) > 1 else 'Discussion thread ↗', '')
                                  for i, d in enumerate(discussions)) or '<span class="muted">None listed</span>'),
    ]
    facts = ''.join(f'<dt>{k}</dt><dd>{v}</dd>' for k, v in rows if v)
    nxt = extras.what_next(n, ctx, B)
    nxt_html = (f'<div class="where-at"><h3 class="sub-h">Where it\'s at</h3><ul>{"".join(f"<li>{x}</li>" for x in nxt)}</ul>'
                '<p class="note" style="margin-top:4px">From the records, not a judgment.</p></div>' if nxt else '')
    groups = extras.affected(ctx.get('fips_repo'), n)
    groups_html = (f'<div class="mentions"><h3 class="sub-h">The FIP\'s text mentions</h3><div class="chips">'
                   + ''.join(f'<span class="chip static">{esc(g)}</span>' for g in groups) +
                   '</div><p class="note" style="margin-top:6px">Found by searching the FIP\'s own wording. Not an official impact assessment; read the FIP.</p></div>'
                   if groups else '')
    glance = (f'<section class="card"><div class="card-head"><h2>At a glance</h2></div><div class="card-body">'
              f'{status_path(status, history, core)}<dl class="facts">{facts}</dl>{nxt_html}{groups_html}</div></section>')

    # History, with Last Call windows
    hist = []
    prev = None
    for h in history:
        commit = f'https://github.com/{u.FIPS_REPO}/commit/{h["sha"]}'
        change = (f'Listed as {badge(h["status"])}' if prev is None
                  else f'{badge(prev)}<span class="arrow">→</span>{badge(h["status"])}')
        hist.append(f'<li><time datetime="{h["since"].isoformat()}">{fmt(h["since"])}</time>'
                    f'<span>{change} <a class="muted small" href="{esc(commit)}" target="_blank" rel="noopener">commit</a></span></li>')
        prev = h['status']
    past = [w for w in ctx.get('past_lc') or [] if w['number'] == n]
    lc_notes = ''.join(f'<li>Last Call {fmt(w["start"])} to {fmt(w["exit"])} ({days_word(w["days"])}), then {badge(w["outcome"])}</li>'
                       for w in past if w.get('exit'))
    hist_card = (f'<section class="card"><div class="card-head"><h2>Status history</h2>'
                 '<span class="hint">From the FIPs README. Dates are when the table changed, which can lag the decision by a few days.</span></div>'
                 f'<div class="card-body">{"<ol class=history>" + "".join(reversed(hist)) + "</ol>" if hist else "<p class=empty>No README history.</p>"}'
                 f'{"<ul class=topics style=margin-top:12px>" + lc_notes + "</ul>" if lc_notes else ""}</div></section>')

    # Calls
    items = []
    for c in convos[:CALLS_SHOWN]:
        if c.get('kind') == 'implementers':
            url = c.get('recording_url') or c.get('notes_url') or c.get('page_url')
            label, kind, name = 'Implementers', 'impl', esc(c['title'])
        else:
            url = c.get('notes_url') or c.get('recording_url')
            label, kind, name = 'Core Devs', 'meeting', f'Core Devs #{c["number"]}'
        link = f'<a href="{esc(url)}" target="_blank" rel="noopener">{name}</a>' if url else name
        rec = (f' · <a class="small" href="{esc(c["recording_url"])}" target="_blank" rel="noopener">recording</a>'
               if c.get('recording_url') and url != c.get('recording_url') else '')
        items.append(f'<li><time>{fmt(c["date"])}</time><span class="kind {kind}">{label}</span><span>{link}{rec}</span></li>')
    more = f'<p class="note">Showing the latest {CALLS_SHOWN} of {len(convos)}.</p>' if len(convos) > CALLS_SHOWN else ''
    calls_card = (f'<section class="card"><div class="card-head"><h2>Discussed in calls ({len(convos)})</h2>'
                  f'<span class="hint">{term("Core Devs")} meetings and implementers\' calls whose notes mention FIP-{n}. A mention means it was discussed, not decided.</span></div>'
                  f'<div class="card-body">{"<ul class=convo-list>" + "".join(items) + "</ul>" + more if items else "<p class=empty>Not mentioned in any call notes yet.</p>"}'
                  '</div></section>')

    # The discussion itself, embedded when giscus is set up in data/site.json
    embed = extras.giscus_embed(discussions)
    disc_card = (f'<section class="card" id="discussion"><div class="card-head"><h2>Discussion</h2>'
                 f'<span class="hint">The FIP\'s GitHub discussion. Replies post from your own GitHub account. '
                 f'{ext(discuss, "Open on GitHub ↗", "")}</span></div><div class="card-body">{embed}</div></section>'
                 if embed else '')

    # Open PRs
    prs = (ctx.get('prs_by_fip') or {}).get(n) or []
    pr_card = ''
    if prs:
        pr_items = ''.join(f'<div class="pr-item"><a href="{esc(p["url"])}" target="_blank" rel="noopener">#{p["number"]} {esc(p["title"])}</a>'
                           f'<span class="pr-meta">@{esc(p["author"])} · {"draft · " if p["draft"] else ""}'
                           f'last activity {days_word(p["idle_days"])} ago</span></div>' for p in prs)
        pr_card = (f'<section class="card"><div class="card-head"><h2>Open pull requests ({len(prs)})</h2>'
                   '<span class="hint">Proposed edits to this FIP waiting on review.</span></div>'
                   f'<div class="card-body">{pr_items}</div></section>')

    # Take part
    involve = (f'<section class="card"><div class="card-head"><h2>Take part</h2></div><div class="card-body">'
               '<div class="links-grid">'
               f'<a class="link-card" href="{esc(discuss)}" target="_blank" rel="noopener"><strong>Comment on FIP-{n} ↗</strong><span>Questions and feedback go in the discussion thread on GitHub.</span></a>'
               f'<a class="link-card" href="https://github.com/filecoin-project/core-devs/issues" target="_blank" rel="noopener"><strong>Raise it at Core Devs ↗</strong><span>Add a topic to the next meeting\'s agenda issue.</span></a>'
               f'<a class="link-card" href="https://github.com/filecoin-project/FIPs/blob/master/FIPS/fip-0001.md" target="_blank" rel="noopener"><strong>How the process works ↗</strong><span>FIP-0001 sets out every stage and who decides.</span></a>'
               '</div>'
               '<details class="more"><summary>What the terms mean</summary><dl class="glossary" style="margin-top:10px">'
               + ''.join(f'<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in GLOSSARY.items()) +
               '</dl></details></div></section>')

    def pn(num, cls, label):
        if not num:
            return '<span></span>'
        t = (fips.get(num) or files.get(num) or {}).get('title', '')
        return f'<a class="{cls}" href="{num}.html"><span>{label}</span>FIP-{num} {esc(short(t, 60))}</a>'
    prevnext = f'<nav class="prev-next" aria-label="Other FIPs">{pn(prev_n, "prev", "← Previous")}{pn(next_n, "next", "Next →")}</nav>'

    report = extras.report_url(f'FIP-{n}', f'{u.SITE_URL}fip/{n}.html')
    crumbs = (f'<div class="crumbs"><span><a href="{B}fips-dashboard-static.html#by-status">← All FIPs</a> · '
              f'<a href="{B}">How FIPs move</a></span><span>{ext(report, "Report a data problem", "")} · '
              f'{ext(u.fip_url(n), "View on GitHub ↗", "")}</span></div>')

    body = '\n'.join(x for x in [
        crumbs, cta,
        f'<div class="grid-2"><div>{summary_card}{calls_card}</div><div>{glance}{hist_card}</div></div>',
        disc_card, pr_card, involve, prevnext,
    ] if x)
    sub = f'{esc(listval(f.get("type")) or fip.get("type") or "FIP")} · {badge(status)}'
    return page(
        title=f'FIP-{n}: {title}',
        description=f'FIP-{n} ({status}): {title}. Status history, Last Call window, network upgrade and the calls that discussed it.',
        current='dashboard', subtitle=sub, body_html=body, base=B, path=f'fip/{n}.html',
        og_image=f'og/{n}.png' if og_cards.available() else None,
    )


# ---------------------------------------------------------------------------
# This week (home page)
# ---------------------------------------------------------------------------

def this_week_card(ctx, base=''):
    now = datetime.now(timezone.utc)

    lcs = sorted(ctx['open_lc'], key=lambda w: w['end'])
    lc_items = []
    for w in lcs:
        left = (w['end'].date() - now.date()).days
        label = f'{days_word(left)} left' if left > 0 else 'ends today' if left == 0 else 'review period over'
        pill = f'<span class="days-left{" soon" if left <= 3 else ""}">{label}</span>'
        disc = w['discussions'][0] if w['discussions'] else None
        lc_items.append(f'<li>{u.fip_anchor(w["number"], base=base)} {esc(w["title"])} {pill}'
                        f'<div class="muted small">Review ends {fmt(w["end"], False)}{" (est.)" if w["estimated_end"] else ""}'
                        f'{" · " + ext(disc, "Comment", "") if disc else ""}</div></li>')
    lc_col = (f'<div class="week-col"><h3>{term("Last Call", "In Last Call")}</h3>'
              + (f'<ul>{"".join(lc_items)}</ul>' if lc_items else '<p class="muted small">No Last Calls open right now.</p>') + '</div>')

    meetings = [m for m in ctx['meetings'] if m['date']]
    latest = meetings[0] if meetings else None
    agenda = (ctx.get('agenda') or [])[:1]
    cd_lines = []
    if agenda:
        a = agenda[0]
        cd_lines.append(f'<li><strong>Next agenda:</strong> <a href="{esc(a["url"])}" target="_blank" rel="noopener">{esc(a["title"])}</a>'
                        '<div class="muted small">Add a topic before the meeting.</div></li>')
    if latest:
        rec = f' · {ext(latest["recording_url"], "recording", "")}' if latest['recording_url'] else ''
        cd_lines.append(f'<li><strong>Latest:</strong> <a href="{base}core-devs.html">Core Devs #{latest["number"]}</a> · {fmt(latest["date"], False)}{rec}</li>')
    if not agenda:
        cd_lines.append(f'<li class="small">{ext("https://github.com/filecoin-project/core-devs/issues", "See open agenda issues", "")}</li>')
    cd_col = f'<div class="week-col"><h3>{term("Core Devs")}</h3><ul>{"".join(cd_lines)}</ul></div>'

    upcoming = sorted((x for x in ctx['upgrades'] if x['mainnet'] and x['mainnet'] > now), key=lambda x: x['mainnet'])
    if upcoming:
        x = upcoming[0]
        days = (x['mainnet'] - now).days
        epoch = f' · epoch {x["mainnet_epoch"]:,}' if x.get('mainnet_epoch') else ''
        up_body = (f'<div class="big">NV{x["number"]} in {days_word(days)}</div>'
                   f'<div class="small">{esc(x["name"])} · mainnet {fmt(x["mainnet"])}{epoch}</div>'
                   f'<div class="small" style="margin-top:6px"><a href="{base}network-upgrades.html#readiness">Get ready checklist →</a></div>')
    else:
        live = [x['number'] for x in ctx['upgrades'] if x['mainnet'] and x['mainnet'] <= now and isinstance(x['number'], int)]
        plan = next((p for p in sorted(ctx.get('planning') or [], key=lambda p: p['nv']) if p['nv'] > max(live or [0])), None)
        if plan:
            up_body = (f'<div class="big">NV{plan["nv"]} in planning</div>'
                       f'<div class="small">{len(plan["scope"])} candidates, no date set yet.</div>'
                       f'<div class="small" style="margin-top:6px"><a href="{base}network-upgrades.html#plan-nv{plan["nv"]}">See the candidates →</a></div>')
        else:
            up_body = '<p class="muted small">No upgrade scheduled.</p>'
    up_col = f'<div class="week-col"><h3>Next {term("Network upgrade", "upgrade")}</h3>{up_body}</div>'

    cutoff = now - timedelta(days=7)
    changes = [e for e in ctx['events'] if e['date'] >= cutoff and e['to'] and e['from'] != e['to']]
    ch_items = ''.join(f'<li>{u.fip_anchor(e["number"], base=base)} '
                       + (f'listed as {badge(e["to"])}' if e['from'] is None else f'{badge(e["from"])} → {badge(e["to"])}')
                       + f'<div class="muted small">{esc(short(e["title"], 70))} · {fmt(e["date"], False)}</div></li>'
                       for e in sorted(changes, key=lambda e: e['date'], reverse=True)[:5])
    ch_col = ('<div class="week-col"><h3>Status changes, last 7 days</h3>'
              + (f'<ul>{ch_items}</ul>' if ch_items else
                 f'<p class="muted small">None this week. <a href="{base}fips-timeline-tracker.html">Full timeline →</a></p>') + '</div>')

    return (f'<section class="card" id="this-week"><div class="card-head"><h2>This week</h2>'
            f'<span class="hint">What\'s open for input and what\'s coming up. '
            f'<a href="{base}calendar.ics">Add to your calendar</a> · <a href="{base}feed.xml">RSS</a>'
            + (f' · <a href="{esc(extras.digest_signup_url())}" target="_blank" rel="noopener">Email digest</a>' if extras.digest_signup_url() else '')
            + '</span></div>'
            f'<div class="card-body"><div class="week">{lc_col}{cd_col}{up_col}{ch_col}</div></div></section>')


# ---------------------------------------------------------------------------
# Feeds
# ---------------------------------------------------------------------------

def _all_fips(ctx):
    return sorted(set(ctx['fips']) | set(ctx['files']), key=int)


def search_index(ctx):
    out = []
    for n in sorted(_all_fips(ctx), key=int, reverse=True):
        f, fl = ctx['fips'].get(n) or {}, ctx['files'].get(n) or {}
        authors = fl.get('author') if isinstance(fl.get('author'), str) else ', '.join(fl.get('author') or [])
        out.append({'n': n, 't': (f.get('title') or fl.get('title') or '').replace('`', ''), 's': f.get('status') or fl.get('_status') or '',
                    'a': authors or f.get('authors') or ''})
    return json.dumps(out, ensure_ascii=False, separators=(',', ':'))


def _xml(s):
    return esc(s).replace('&#x27;', '&#39;')


def rss(ctx):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=FEED_DAYS)
    site = u.SITE_URL
    items = []
    for e in ctx['events']:
        if e['date'] < cutoff or not e['to'] or e['from'] == e['to']:
            continue
        what = f'listed as {e["to"]}' if e['from'] is None else f'{e["from"]} → {e["to"]}'
        items.append((e['date'], f'FIP-{e["number"]} {what}: {e["title"]}', f'{site}fip/{e["number"]}.html',
                      f'FIP-{e["number"]} ({e["title"]}) moved {what} in the FIPs README.' if e['from'] else
                      f'New FIP-{e["number"]}: {e["title"]}, listed as {e["to"]}.', f'status-{e["number"]}-{e["sha"][:10]}'))
    for w in ctx['open_lc']:
        items.append((w['start'], f'Last Call open: FIP-{w["number"]} {w["title"]}', f'{site}fip/{w["number"]}.html',
                      f'Review ends {fmt(w["end"])}{" (estimated)" if w["estimated_end"] else ""}. Comment in the discussion thread.',
                      f'lastcall-{w["number"]}-{w["start"]:%Y%m%d}'))
    for x in ctx['upgrades']:
        if x['mainnet'] and cutoff <= x['mainnet'] <= now:
            fl = ', '.join(f'FIP-{f}' for f in x['fips']) or 'no FIPs'
            items.append((x['mainnet'], f'NV{x["number"]} {x["name"]} activated on mainnet', f'{site}network-upgrades.html#nv{x["number"]}',
                          f'Network upgrade NV{x["number"]} ({x["name"]}) activated on mainnet. Included: {fl}.', f'upgrade-{x["number"]}'))
    for m in ctx['meetings']:
        if m['date'] and cutoff <= m['date'] <= now:
            topics = '; '.join(t.rstrip('.') for t in m['topics'][:3])
            items.append((m['date'], f'Core Devs #{m["number"]}', m['notes_url'] or m['recording_url'] or f'{site}core-devs.html',
                          topics or 'Notes and recording on the Core Devs page.', f'coredevs-{m["number"]}'))
    items.sort(key=lambda i: i[0], reverse=True)
    body = ''.join(f'<item><title>{_xml(t)}</title><link>{_xml(l)}</link><guid isPermaLink="false">{_xml(g)}</guid>'
                   f'<pubDate>{format_datetime(d)}</pubDate><description>{_xml(desc)}</description></item>'
                   for d, t, l, desc, g in items[:60])
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
            '<title>Filecoin governance updates</title>'
            f'<link>{site}</link>'
            '<description>FIP status changes, Last Calls, network upgrades and Core Devs meetings, from the public records.</description>'
            f'<lastBuildDate>{format_datetime(now)}</lastBuildDate>{body}</channel></rss>\n')


def _ics_text(s):
    return (s or '').replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')


def _fold(line):
    """RFC 5545: lines over 75 octets continue on the next line after a space."""
    out, raw = [], line.encode('utf-8')
    while len(raw) > (75 if not out else 74):  # continuation lines start with a space
        cut = 75 if not out else 74
        while cut and (raw[cut] & 0xC0) == 0x80:  # don't split a UTF-8 character
            cut -= 1
        out.append(raw[:cut].decode('utf-8'))
        raw = raw[cut:]
    out.append(raw.decode('utf-8'))
    return '\r\n '.join(out)


def calendar(ctx):
    now = datetime.now(timezone.utc)
    stamp = now.strftime('%Y%m%dT%H%M%SZ')
    site = u.SITE_URL
    events = []

    def add(uid, day, summary, desc, url):
        events.append((day, uid, summary, desc, url))

    for m in [m for m in ctx['meetings'] if m['date']][:24]:
        topics = '; '.join(t.rstrip('.') for t in m['topics'][:4])
        add(f'coredevs-{m["number"]}', m['date'], f'Filecoin Core Devs #{m["number"]}', topics,
            m['notes_url'] or m['agenda_url'] or f'{site}core-devs.html')
    for c in [c for c in ctx.get('calls') or [] if c['date']][:24]:
        add(f'impl-{c["date"]:%Y%m%d}-{zlib.crc32(c["title"].encode()):08x}', c['date'], f'Filecoin implementers: {c["title"]}',
            c.get('summary') or '', c.get('page_url') or c.get('notes_url') or f'{site}implementers.html')
    for w in ctx['open_lc'] + [w for w in ctx.get('past_lc') or [] if w['end'] >= now - timedelta(days=90)]:
        add(f'lastcall-end-{w["number"]}-{w["start"]:%Y%m%d}', w['end'],
            f'Last Call ends: FIP-{w["number"]}' + (' (est.)' if w['estimated_end'] else ''),
            f'{w["title"]}. Final day to comment before the FIP moves on.', f'{site}fip/{w["number"]}.html')
    for x in ctx['upgrades']:
        for net, when in (('mainnet', x['mainnet']), ('calibration', x['calibration'])):
            if when and when >= now - timedelta(days=365):
                fl = ', '.join(f'FIP-{f}' for f in x['fips']) or 'no FIPs'
                add(f'upgrade-{x["number"]}-{net}', when, f'NV{x["number"]} {x["name"]} on {net}',
                    f'Network upgrade activates on {net}' + (f' at epoch {x["mainnet_epoch"]:,}' if net == 'mainnet' and x.get('mainnet_epoch') else '')
                    + f'. Includes {fl}.', f'{site}network-upgrades.html#nv{x["number"]}')

    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Filecoin Governance Hub//EN', 'CALSCALE:GREGORIAN',
             'METHOD:PUBLISH', 'X-WR-CALNAME:Filecoin governance', 'X-PUBLISHED-TTL:PT6H',
             'X-WR-CALDESC:Core Devs and implementers\' calls\\, Last Call deadlines and network upgrade dates.']
    for day, uid, summary, desc, url in sorted(events, key=lambda e: e[0]):
        d = day.astimezone(timezone.utc).date()
        lines += ['BEGIN:VEVENT', f'UID:{uid}@fips-dashboard', f'DTSTAMP:{stamp}',
                  f'DTSTART;VALUE=DATE:{d:%Y%m%d}', f'DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}',
                  f'SUMMARY:{_ics_text(summary)}', f'DESCRIPTION:{_ics_text((desc + chr(10) + url).strip())}',
                  f'URL:{url}', 'TRANSP:TRANSPARENT', 'END:VEVENT']
    lines.append('END:VCALENDAR')
    return '\r\n'.join(_fold(l) for l in lines) + '\r\n'


REDIRECT_INDEX = '''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>All FIPs</title>
<meta http-equiv="refresh" content="0; url=../fips-dashboard-static.html#by-status">
<link rel="canonical" href="../fips-dashboard-static.html"></head>
<body><p><a href="../fips-dashboard-static.html#by-status">See all FIPs</a>.</p></body></html>
'''


def write_all(ctx):
    nums = _all_fips(ctx)
    os.makedirs(OUT_DIR, exist_ok=True)
    keep = {f'{n}.html' for n in nums} | {'index.html'}
    for name in os.listdir(OUT_DIR):  # drop pages for FIPs no longer listed
        if name.endswith('.html') and name not in keep:
            os.remove(os.path.join(OUT_DIR, name))
    for i, n in enumerate(nums):
        prev_n = nums[i - 1] if i > 0 else None
        next_n = nums[i + 1] if i + 1 < len(nums) else None
        with open(os.path.join(OUT_DIR, f'{n}.html'), 'w', encoding='utf-8') as f:
            f.write(fip_page_html(n, ctx, prev_n, next_n))
    for name, content in ((os.path.join(OUT_DIR, 'index.html'), REDIRECT_INDEX), ('fips-index.json', search_index(ctx)),
                          ('feed.xml', rss(ctx)), ('calendar.ics', calendar(ctx)), ('data.json', extras.data_json(ctx))):
        with open(name, 'w', encoding='utf-8', newline='') as f:
            f.write(content)
    print(f'Generated {len(nums)} FIP pages, fips-index.json, feed.xml, calendar.ics, data.json')
    og_cards.write_all(ctx)
