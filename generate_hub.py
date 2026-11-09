#!/usr/bin/env python3
"""Generate the governance hub pages:

  index.html             FIP lifecycle (the home page): stages, where open FIPs are, timings
  overview.html          Overview: latest meeting, what's open, activity feed
  fip-lifecycle.html     Redirect to the home page, for old links
  core-devs.html         Core Devs meetings, recordings, FIPs on the agenda
  network-upgrades.html  Network upgrades and the FIPs they shipped

Reads public data only (FIPs and core-devs repos, plus optional GitHub API
calls for discussions and open agenda issues).
"""

import re
from datetime import datetime, timedelta, timezone

import fip_utils as u
import core_devs as cd
import implementers as impl
import scope_planning as sp
from fip_utils import html_escape as esc
from theme import page
from generate_fips_dashboard import badge, fip_link, date_str

FEED_DAYS = 90
AGENDA_WINDOW = 6  # meetings
CALLS_SHOWN = 200  # implementers' calls listed on the Implementers page
UPGRADES_SHOWN = 4  # recent upgrades with their implementers' discussions


def fmt_date(d, with_year=True):
    if not d:
        return '—'
    return d.strftime('%b %-d, %Y' if with_year else '%b %-d')


def ago(d):
    if not d:
        return ''
    days = (datetime.now(timezone.utc) - d).days
    if days <= 0:
        return 'today'
    if days == 1:
        return 'yesterday'
    if days < 45:
        return f'{days} days ago'
    return fmt_date(d)


def ext(url, label, cls='btn'):
    return f'<a class="{cls}" href="{esc(url)}" target="_blank" rel="noopener">{label}</a>'


CTX = {}


def fip_info(num):
    """(title, url, merged) for a FIP number. FIPs that only exist as an open
    PR link to that PR (or a PR search) instead of a missing file."""
    fips, files = CTX.get('fips', {}), CTX.get('files', {})
    title = (fips.get(num) or {}).get('title') or (files.get(num) or {}).get('title') or ''
    if num in files or num in fips:
        return title, u.fip_url(num), True
    pr = (CTX.get('prs_by_fip') or {}).get(num)
    if pr:
        t = re.sub(r'^\s*(add\s+)?FIP[-\s]?0*\d+\s*[:\-–]?\s*', '', pr[0]['title'], flags=re.I) or pr[0]['title']
        return title or t, pr[0]['url'], False
    return title, f'https://github.com/filecoin-project/FIPs/pulls?q=is%3Apr+FIP-{num}', False


def fip_a(num, cls='fip-id'):
    title, url, _ = fip_info(num)
    return f'<a class="{cls}" href="{esc(url)}" target="_blank" rel="noopener" title="{esc(title)}">FIP-{num}</a>'


def fip_chip(num, fips=None, files=None):
    return fip_a(num, 'chip')


def meeting_buttons(m, primary_recording=True):
    out = []
    if m['recording_url']:
        label = '▶ Recording'
        out.append(ext(m['recording_url'], label, 'btn primary' if primary_recording else 'btn'))
    if m['notes_url']:
        out.append(ext(m['notes_url'], 'Slides' if m['notes_kind'] == 'slides' else 'Notes'))
    if m['agenda_url']:
        out.append(ext(m['agenda_url'], 'Agenda'))
    html = '<div class="btn-row">' + ''.join(out) + '</div>' if out else ''
    if m['passcode'] and m['recording_url']:
        html += f'<div class="passcode">Recording passcode: <code>{esc(m["passcode"])}</code></div>'
    return html


def call_links(c):
    """Inline links for an implementers' call."""
    links = []
    if c['recording_url']:
        links.append(f'<a href="{esc(c["recording_url"])}" target="_blank" rel="noopener">Recording</a>')
    if c['notes_url']:
        links.append(f'<a href="{esc(c["notes_url"])}" target="_blank" rel="noopener">Notes</a>')
    if c['agenda_url']:
        links.append(f'<a href="{esc(c["agenda_url"])}" target="_blank" rel="noopener">Agenda</a>')
    if c['page_url']:
        links.append(f'<a href="{esc(c["page_url"])}" target="_blank" rel="noopener">Notes</a>')
    return ' · '.join(links)


def convo_label(c):
    """(kind class, kind label, linked title) for a Core Devs meeting or implementers' call."""
    if c.get('kind') == 'implementers':
        url = c['recording_url'] or c['notes_url'] or c['page_url']
        title = esc(c['title'])
        return 'impl', 'Implementers', (f'<a href="{esc(url)}" target="_blank" rel="noopener">{title}</a>' if url else title)
    url = c['notes_url'] or c['recording_url']
    title = f'Core Devs #{c["number"]}'
    return 'meeting', 'Core Devs', (f'<a href="{esc(url)}" target="_blank" rel="noopener">{title}</a>' if url else title)


def video(m):
    if not m.get('youtube_id'):
        return ''
    vid = esc(m['youtube_id'])
    return (f'<div class="video"><button type="button" data-yt="{vid}" aria-label="Play Core Devs #{m["number"]} recording">'
            f'<img src="https://i.ytimg.com/vi/{vid}/hqdefault.jpg" alt="" loading="lazy">'
            f'<span class="play" aria-hidden="true"></span></button></div>')


def latest_meeting_card(m, fips, files, heading='Latest Core Devs meeting', show_video=True):
    if not m:
        return ''
    meta = [fmt_date(m['date'])]
    if m['facilitator']:
        meta.append(f'Facilitated by {esc(m["facilitator"])}')
    topics = ''.join(f'<li>{esc(t)}</li>' for t in m['topics'][:8])
    chips = ''.join(fip_chip(f, fips, files) for f in m['fips'])
    return f'''<section class="card"><div class="card-head"><h2>{heading}</h2>
<a class="hint" href="core-devs.html">All meetings →</a></div>
<div class="card-body">
<div class="meeting-title">Core Devs #{m["number"]}</div>
<div class="meeting-meta">{" · ".join(meta)}</div>
{f'<ul class="topics">{topics}</ul>' if topics else ''}
{f'<div class="chips" style="margin-bottom:6px">{chips}</div><p class="note" style="margin-top:4px">FIPs mentioned in the notes. Mentions are not decisions.</p>' if chips else ''}
{meeting_buttons(m)}
{video(m) if show_video else ''}
</div></section>'''


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

def overview(ctx):
    fips, files, meetings, upgrades = ctx['fips'], ctx['files'], ctx['meetings'], ctx['upgrades']
    now = datetime.now(timezone.utc)
    latest = next((m for m in meetings if m['date']), None)
    live = [x for x in upgrades if x['mainnet'] and x['mainnet'] <= now]
    upcoming = sorted((x for x in upgrades if x['mainnet'] and x['mainnet'] > now), key=lambda x: x['mainnet'])
    last_up = live[0] if live else None
    open_lc = ctx['open_lc']
    discussions = ctx['discussions']
    active = [d for d in (discussions or []) if (now - d['updated']).days <= 30]
    prs = ctx['prs']

    def stat(href, label, value, sub='', accent=False):
        return (f'<a class="stat{" accent" if accent else ""}" href="{href}"><div class="label">{esc(label)}</div>'
                f'<div class="value">{value}</div>{f"<div class=sub-value>{sub}</div>" if sub else ""}</a>')

    stats = '<section class="stats">' + ''.join([
        stat('core-devs.html', 'Latest Core Devs', f'#{latest["number"]}' if latest else '—', fmt_date(latest['date']) if latest else ''),
        stat('fips-dashboard-static.html#last-call', 'In Last Call', len(open_lc), 'final review windows', bool(open_lc)),
        stat('network-upgrades.html', 'Latest upgrade', f'NV{last_up["number"]}' if last_up else '—',
             f'{esc(last_up["name"])} · {fmt_date(last_up["mainnet"])}' if last_up else ''),
        stat('fips-dashboard-static.html#prs', 'Open FIP PRs', len({p['number'] for p in prs}) if prs is not None else '—', 'on the FIPs repo'),
        stat('#discussions', 'Active discussions', len(active) if discussions is not None else '—', 'updated in 30 days'),
    ]) + '</section>'

    # What's open now
    items = []
    for w in open_lc:
        left = (w['end'] - now).days
        items.append(f'<li><span class="kind fip">Last Call</span> {fip_link(w["number"])} {esc(w["title"])}. '
                     f'Review ends {fmt_date(w["end"])}{" (est.)" if w["estimated_end"] else ""}'
                     f'{f", {left} days left" if left > 0 else ""}. {discussion_link_inline(w["discussions"])}</li>')
    for a in (ctx['agenda'] or [])[:2]:
        items.append(f'<li><span class="kind meeting">Agenda</span> <a href="{esc(a["url"])}" target="_blank" rel="noopener">{esc(a["title"])}</a>. '
                     f'Add topics for the next Core Devs meeting.</li>')
    for x in upcoming[:2]:
        items.append(f'<li><span class="kind upgrade">Upgrade</span> NV{x["number"]} {esc(x["name"])} activates on mainnet {fmt_date(x["mainnet"])}.</li>')
    if not items:
        items.append('<li class="muted">No Last Calls are open and no upgrade is scheduled right now.</li>')
    agenda_note = ''
    if ctx['agenda'] is None:
        agenda_note = '<p class="note">The next meeting\'s agenda issue couldn\'t be loaded on this run.</p>'
    now_card = f'''<section class="card"><div class="card-head"><h2>Open now</h2>
<span class="hint">Where your input counts this week.</span></div>
<div class="card-body"><ul class="open-list">{"".join(items)}</ul>{agenda_note}
<div class="btn-row" style="margin-top:14px">{ext("https://github.com/filecoin-project/FIPs/discussions", "FIP discussions")}{ext("https://github.com/filecoin-project/core-devs/issues", "Core Devs agendas")}</div>
</div></section>'''

    # Activity feed
    cutoff = now - timedelta(days=FEED_DAYS)
    feed = []
    for e in ctx['events']:
        if e['date'] < cutoff or e['to'] is None:
            continue
        what = (f'{fip_link(e["number"])} {esc(e["title"])} listed as {badge(e["to"])}' if e['from'] is None
                else f'{fip_link(e["number"])} {esc(e["title"])}: {badge(e["from"])} → {badge(e["to"])}')
        feed.append((e['date'], 'fip', 'FIP status', what))
    for m in meetings:
        if m['date'] and cutoff <= m['date'] <= now:
            topics = '; '.join(t.rstrip('.') for t in m['topics'][:3])
            link = m['recording_url'] or m['notes_url']
            title = f'<a href="{esc(link)}" target="_blank" rel="noopener">Core Devs #{m["number"]}</a>' if link else f'Core Devs #{m["number"]}'
            feed.append((m['date'], 'meeting', 'Meeting', f'{title}{": " + esc(topics) if topics else ""}'))
    for c in ctx['calls']:
        if c['date'] and cutoff <= c['date'] <= now:
            _, _, title = convo_label(c)
            fl = ', '.join(f'FIP-{f}' for f in c['fips'][:4])
            summary = ': ' + esc(c['summary'][:140]) if c['summary'] else ''
            fips_note = f' <span class="muted small">({fl})</span>' if fl else ''
            feed.append((c['date'], 'impl', 'Implementers', f'{title}{summary}{fips_note}'))
    for x in upgrades:
        for net, when in (('mainnet', x['mainnet']), ('calibration', x['calibration'])):
            if when and cutoff <= when <= now:
                fl = ', '.join(f'FIP-{f}' for f in x['fips']) or 'no FIPs'
                feed.append((when, 'upgrade', 'Upgrade', f'NV{x["number"]} {esc(x["name"])} activated on {net} ({fl})'))
    for d in discussions or []:
        if cutoff <= d['created'] <= now:
            feed.append((d['created'], 'discussion', 'Discussion',
                         f'<a href="{esc(d["url"])}" target="_blank" rel="noopener">{esc(d["title"])}</a> <span class="muted small">by @{esc(d["author"])}</span>'))
    feed.sort(key=lambda r: r[0], reverse=True)
    feed_html = ''.join(f'<li><time datetime="{d.isoformat()}">{fmt_date(d, False)}</time><span class="kind {k}">{label}</span>'
                        f'<span class="feed-text">{text}</span></li>' for d, k, label, text in feed[:30])
    feed_card = f'''<section class="card"><div class="card-head"><h2>Recent activity</h2>
<span class="hint">Last {FEED_DAYS} days across FIPs, Core Devs, implementers' calls and network upgrades.</span></div>
<div class="card-body">{f'<ul class="feed">{feed_html}</ul>' if feed_html else '<p class="empty">Nothing in the last 90 days.</p>'}</div></section>'''

    # Discussions
    if discussions is None:
        disc_body = '<p class="empty">Discussions couldn\'t be loaded on this run. <a href="https://github.com/filecoin-project/FIPs/discussions" target="_blank" rel="noopener">Browse them on GitHub</a>.</p>'
    else:
        rows = ''.join(f'''<tr><td class="title-cell"><a href="{esc(d["url"])}" target="_blank" rel="noopener">{esc(d["title"])}</a>
<div class="muted small">#{d["number"]} · {esc(d["category"])} · @{esc(d["author"])}</div></td>
<td class="num">{d["comments"]}</td><td class="nowrap">{ago(d["updated"])}</td></tr>''' for d in discussions[:10])
        disc_body = f'''<div class="table-scroll"><table class="data"><thead><tr><th>Discussion</th><th class="num">Comments</th><th>Last activity</th></tr></thead>
<tbody>{rows}</tbody></table></div>''' if rows else '<p class="empty">No discussions yet.</p>'
    disc_card = f'''<section class="card" id="discussions"><div class="card-head"><h2>FIP discussions</h2>
<span class="hint">Most recently active threads on the FIPs repo, where proposals start.</span></div>
<div class="card-body">{disc_body}</div></section>'''

    involved = f'''<section class="card"><div class="card-head"><h2>Get involved</h2></div><div class="card-body"><div class="links-grid">
<a class="link-card" href="https://github.com/filecoin-project/FIPs/blob/master/FIPS/fip-0001.md" target="_blank" rel="noopener"><strong>How the FIP process works</strong><span>FIP-0001: types, statuses and how proposals move.</span></a>
<a class="link-card" href="https://github.com/filecoin-project/FIPs/discussions" target="_blank" rel="noopener"><strong>Start or join a discussion</strong><span>Ideas begin as FIP discussions before a draft.</span></a>
<a class="link-card" href="fips-dashboard-static.html"><strong>Track every FIP</strong><span>Status, Last Call windows and open PRs.</span></a>
<a class="link-card" href="core-devs.html"><strong>Core Devs meetings</strong><span>Notes, recordings and agendas back to 2020.</span></a>
<a class="link-card" href="implementers.html"><strong>Implementers' calls</strong><span>How upgrades get built: calls, recordings and what each one covered.</span></a>
<a class="link-card" href="network-upgrades.html"><strong>Network upgrades</strong><span>What shipped when, and which FIPs it included.</span></a>
<a class="link-card" href="mailto:governance@fil.org"><strong>Contact the governance team</strong><span>governance@fil.org</span></a>
</div></div></section>'''

    body = '\n'.join([
        stats,
        f'<div class="grid-2">{latest_meeting_card(latest, fips, files)}{now_card}</div>',
        feed_card,
        disc_card,
        involved,
    ])
    return page(
        title='Filecoin Governance',
        description='One place to follow Filecoin governance: FIPs, Core Devs meetings and recordings, network upgrades and discussions.',
        current='overview',
        subtitle='FIPs, Core Devs meetings, recordings and network upgrades in one place, built from the public GitHub records.',
        body_html=body,
    )


def discussion_link_inline(urls):
    if not urls:
        return ''
    return f'<a href="{esc(urls[0])}" target="_blank" rel="noopener">Comment</a>'


# ---------------------------------------------------------------------------
# Core Devs
# ---------------------------------------------------------------------------

def core_devs_page(ctx):
    fips, files, meetings = ctx['fips'], ctx['files'], ctx['meetings']
    dated = [m for m in meetings if m['date']]
    latest = dated[0] if dated else None
    recent = dated[:AGENDA_WINDOW]

    # FIPs on the recent agenda
    counts, last = {}, {}
    for m in recent:
        for f in m['fips']:
            counts[f] = counts.get(f, 0) + 1
            last.setdefault(f, m)
    upgrades_by_fip = cd.fip_upgrades(ctx['upgrades'])
    agenda_rows = []
    for f, n in sorted(counts.items(), key=lambda x: (-x[1], -int(x[0]))):
        status = (fips.get(f) or {}).get('status') or (files.get(f) or {}).get('_status') or ''
        title, _, merged = fip_info(f)
        m = last[f]
        shipped = upgrades_by_fip.get(f)
        agenda_rows.append(f'''<tr><td>{fip_a(f)}</td><td class="title-cell">{esc(title) or '<span class="muted">—</span>'}</td>
<td>{badge(status) if status else ('<span class="pill waiting">Open PR</span>' if not merged and (CTX.get('prs_by_fip') or {}).get(f) else '<span class="pill">Not merged yet</span>')}</td>
<td class="num">{n} of {len(recent)}</td>
<td class="nowrap"><a href="{esc(m["notes_url"] or m["recording_url"] or "#")}" target="_blank" rel="noopener">#{m["number"]}</a> · {fmt_date(m["date"])}</td>
<td>{f'NV{shipped["number"]} {esc(shipped["name"])}' if shipped else '<span class="muted">—</span>'}</td></tr>''')
    agenda_card = f'''<section class="card"><div class="card-head"><h2>FIPs on the agenda</h2>
<span class="hint">FIPs mentioned in the notes of the last {len(recent)} meetings. A mention means it was discussed, not decided.</span></div>
<div class="card-body">{f"""<div class="table-scroll"><table class="data"><thead><tr><th>FIP</th><th>Title</th><th>Status</th><th class="num">Meetings</th><th>Last discussed</th><th>Shipped in</th></tr></thead>
<tbody>{"".join(agenda_rows)}</tbody></table></div>""" if agenda_rows else '<p class="empty">No FIPs mentioned in recent notes.</p>'}</div></section>'''

    # Archive
    rows = []
    for m in meetings:
        chips = ''.join(fip_chip(f, fips, files) for f in m['fips'][:8])
        more = f' <span class="muted small">+{len(m["fips"]) - 8}</span>' if len(m['fips']) > 8 else ''
        topics = esc('; '.join(t.rstrip('.') for t in m['topics'][:3]))
        links = []
        if m['recording_url']:
            links.append(f'<a href="{esc(m["recording_url"])}" target="_blank" rel="noopener">Recording</a>'
                         + (f' <span class="passcode">({esc(m["passcode"])})</span>' if m['passcode'] else ''))
        if m['notes_url']:
            links.append(f'<a href="{esc(m["notes_url"])}" target="_blank" rel="noopener">{"Slides" if m["notes_kind"] == "slides" else "Notes"}</a>')
        if m['agenda_url']:
            links.append(f'<a href="{esc(m["agenda_url"])}" target="_blank" rel="noopener">Agenda</a>')
        note = f'<span class="pill">{esc(m["note"])}</span>' if m['note'] else ''
        search = ' '.join([str(m['number']), fmt_date(m['date']), ' '.join(m['topics']), ' '.join('FIP-' + f + ' FIP' + f + ' ' + str(int(f)) for f in m['fips']), m['note'] or '']).lower()
        rows.append(f'''<tr data-search="{esc(search)}"><td class="num"><strong>#{m["number"]}</strong></td>
<td class="nowrap">{fmt_date(m["date"])}</td>
<td class="title-cell">{topics or '<span class="muted">—</span>'} {note}</td>
<td><div class="chips">{chips}{more}</div></td>
<td class="nowrap">{" · ".join(links) or '<span class="muted">—</span>'}</td></tr>''')
    archive = f'''<section class="card" id="archive"><div class="card-head"><h2>All meetings ({len(meetings)})</h2>
<input class="search" type="search" placeholder="Filter by FIP, number or topic, e.g. 0100" aria-label="Filter meetings" oninput="filterMeetings(this.value)"></div>
<div class="card-body"><div class="table-scroll"><table class="data" id="meetings">
<thead><tr><th class="num">#</th><th>Date</th><th>Topics</th><th>FIPs mentioned</th><th>Links</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
<p class="empty" id="no-match" hidden>No meetings match.</p>
<p class="note">Recording, notes and agenda links come from the core-devs README and notes files. Some early meetings have no recording.</p></div></section>
<script>
function filterMeetings(q) {{
  q = (q || '').toLowerCase().trim();
  var rows = document.querySelectorAll('#meetings tbody tr'), shown = 0;
  rows.forEach(function (r) {{ var hit = !q || r.getAttribute('data-search').indexOf(q) !== -1; r.hidden = !hit; if (hit) shown++; }});
  document.getElementById('no-match').hidden = shown !== 0;
}}
</script>'''

    about = '''<section class="card"><div class="card-head"><h2>About Core Devs</h2></div><div class="card-body">
<p>Core Devs is the regular technical meeting where Filecoin implementation and research teams share updates, discuss FIP implementation and set priorities for network upgrades. Anyone can follow along; observers and FIP authors can ask to join.</p>
<div class="btn-row">''' + ext('https://github.com/filecoin-project/core-devs', 'core-devs repo') + ext('https://github.com/filecoin-project/core-devs/issues', 'Agendas') + ext('https://github.com/filecoin-project/core-devs#who-can-attend', 'Who can attend') + '</div></div></section>'

    body = '\n'.join([
        f'<div class="grid-2">{latest_meeting_card(latest, fips, files)}{about}</div>',
        agenda_card,
        archive,
    ])
    return page(
        title='Core Devs Meetings',
        description='Filecoin Core Devs meetings: latest topics, recordings, notes, agendas and which FIPs were discussed.',
        current='coredevs',
        subtitle='Every Core Devs meeting with its recording, notes and agenda, and the FIPs each one discussed.',
        body_html=body,
    )


# ---------------------------------------------------------------------------
# Network upgrades
# ---------------------------------------------------------------------------

def upgrade_convo_html(hits, open_=False, limit=12):
    """Collapsible list of the Core Devs meetings and implementers' calls that discussed an upgrade."""
    if not hits:
        return ''
    n_cd = sum(1 for c, _ in hits if c.get('kind') != 'implementers')
    n_im = len(hits) - n_cd
    parts = [p for p in (f'{n_cd} Core Devs' if n_cd else '', f"{n_im} implementers'" if n_im else '') if p]
    items = []
    for c, reason in hits[:limit]:
        kind, label, title = convo_label(c)
        items.append(f'<li><time>{fmt_date(c["date"])}</time><span class="kind {kind}">{label}</span>'
                     f'<span>{title} <span class="muted small">{esc(reason)}</span></span></li>')
    if len(hits) > limit:
        items.append(f'<li class="muted small">+{len(hits) - limit} earlier</li>')
    plural = 's' if len(hits) != 1 else ''
    return (f'<details class="up-convo"{" open" if open_ else ""}>'
            f'<summary>Discussed in {len(hits)} call{plural} <span class="muted small">({", ".join(parts)})</span></summary>'
            f'<ul class="convo-list">{"".join(items)}</ul></details>')


def implementers_page(ctx):
    """The Implementers tab: latest call, upgrade discussions and the full call log."""
    calls, source, upgrades = ctx['calls'], ctx['calls_source'], ctx['upgrades']
    now = datetime.now(timezone.utc)
    dated = [c for c in calls if c['date'] and c['date'] <= now]
    latest = dated[0] if dated else None
    recent = [c for c in dated if (now - c['date']).days <= FEED_DAYS]
    impl_hits = {n: [(c, r) for c, r in hits if c.get('kind') == 'implementers']
                 for n, hits in ctx['upgrade_conv'].items()}

    def stat(href, label, value, sub=''):
        return (f'<a class="stat" href="{href}"><div class="label">{esc(label)}</div>'
                f'<div class="value">{value}</div>{f"<div class=sub-value>{sub}</div>" if sub else ""}</a>')

    stats = '<section class="stats">' + ''.join([
        stat('#calls-log', 'Calls logged', len(calls) if source else '—', 'in the implementers\' log' if source else 'log not loaded'),
        stat('#latest-call', 'Latest call', fmt_date(latest['date'], False) if latest else '—',
             ago(latest['date']) if latest else ''),
        stat('#calls-log', f'Last {FEED_DAYS} days', len(recent) if source else '—', 'calls held'),
        stat('#upgrade-talk', 'Upgrades discussed', sum(1 for h in impl_hits.values() if h) if source else '—',
             'named or FIPs covered'),
    ]) + '</section>'

    # Latest call
    if latest:
        chips = ''.join(fip_chip(f) for f in latest['fips'])
        ups = [n for n, hits in impl_hits.items() if any(c is latest for c, _ in hits)]
        up_chips = ''.join(f'<a class="chip" href="network-upgrades.html#nv{esc(str(n))}">NV{esc(str(n))}</a>' for n in ups)
        links = call_links(latest)
        summary = f'<p>{esc(latest["summary"])}</p>' if latest['summary'] else ''
        tags = (f'<div class="chips" style="margin:8px 0 4px">{up_chips}{chips}</div>'
                '<p class="note" style="margin-top:4px">Upgrades and FIPs mentioned. Mentions are not decisions.</p>'
                if chips or up_chips else '')
        vid = ''
        if latest.get('youtube_id'):
            v = esc(latest['youtube_id'])
            vid = (f'<div class="video"><button type="button" data-yt="{v}" aria-label="Play recording">'
                   f'<img src="https://i.ytimg.com/vi/{v}/hqdefault.jpg" alt="" loading="lazy">'
                   '<span class="play" aria-hidden="true"></span></button></div>')
        latest_card = (f'<section class="card" id="latest-call"><div class="card-head"><h2>Latest implementers\' call</h2>'
                       f'<a class="hint" href="#calls-log">All calls →</a></div><div class="card-body">'
                       f'<div class="meeting-title">{esc(latest["title"])}</div>'
                       f'<div class="meeting-meta">{fmt_date(latest["date"])}{" · " + esc(", ".join(latest["types"])) if latest["types"] else ""}</div>'
                       f'{summary}{tags}{f"<div class=btn-row>{links}</div>" if links else ""}{vid}</div></section>')
    else:
        latest_card = ('<section class="card" id="latest-call"><div class="card-head"><h2>Latest implementers\' call</h2></div>'
                       '<div class="card-body"><p class="empty">No calls to show yet.</p></div></section>')

    about = ('<section class="card"><div class="card-head"><h2>About the implementers\' calls</h2></div><div class="card-body">'
             '<p>Filecoin implementation teams meet regularly to coordinate network upgrades: scope, timelines, '
             'test vectors, calibration and mainnet readiness, and blockers on accepted FIPs. Core Devs sets priorities; '
             'these calls are where implementers work out how and when they ship.</p>'
             '<div class="btn-row">' + ext('network-upgrades.html', 'Network upgrades') + ext('core-devs.html', 'Core Devs meetings') + '</div>'
             '</div></section>')

    # Upgrade discussions: upcoming plus the most recent live upgrades
    upcoming = [x for x in upgrades if x['mainnet'] and x['mainnet'] > now or not x['mainnet']]
    live = [x for x in upgrades if x['mainnet'] and x['mainnet'] <= now]
    shown = (upcoming + live)[:UPGRADES_SHOWN]
    blocks = []
    for x in shown:
        hits = impl_hits.get(x['number'], [])
        state = ('<span class="pill waiting">Upcoming</span>' if x['mainnet'] and x['mainnet'] > now else
                 '<span class="pill approved">Live</span>' if x['mainnet'] else '<span class="pill">Not scheduled</span>')
        items = ''.join(
            f'<li><time>{fmt_date(c["date"])}</time><span class="kind impl">Implementers</span>'
            f'<span>{convo_label(c)[2]} <span class="muted small">{esc(r)}</span></span></li>' for c, r in hits[:8])
        if len(hits) > 8:
            items += f'<li class="muted small">+{len(hits) - 8} earlier</li>'
        all_n = len(ctx['upgrade_conv'].get(x['number'], []))
        body = (f'<ul class="convo-list">{items}</ul>' if items else
                '<p class="muted small" style="margin-top:6px">No implementers\' calls in the log discussed this upgrade.</p>')
        blocks.append(f'<div class="up-card" id="impl-nv{esc(str(x["number"]))}"><div class="up-head">'
                      f'<h3><span class="nv">NV{esc(str(x["number"]))}</span>{esc(x["name"])}</h3>{state}</div>'
                      f'<div class="up-dates"><span>Mainnet: <strong>{fmt_date(x["mainnet"])}</strong></span>'
                      f'<span>{len(hits)} implementers\' call{"s" if len(hits) != 1 else ""}</span>'
                      f'<span><a href="network-upgrades.html#nv{esc(str(x["number"]))}">{"All " + str(all_n) + " calls" if all_n != 1 else "1 call"} incl. Core Devs →</a></span></div>'
                      f'{body}</div>')
    upgrade_card = (f'<section class="card" id="upgrade-talk"><div class="card-head"><h2>Network upgrade discussions</h2>'
                    '<span class="hint">Implementers\' calls that named each upgrade or discussed its FIPs before activation.</span></div>'
                    f'<div class="card-body"><div class="up-list">{"".join(blocks)}</div></div></section>'
                    if source and blocks else '')

    body = '\n'.join([
        stats,
        f'<div class="grid-2">{latest_card}{about}</div>',
        upgrade_card,
        implementers_card(ctx),
    ])
    return page(
        title="Implementers' Calls",
        description="Filecoin implementers' calls: recordings, notes and which network upgrades and FIPs each call discussed.",
        current='implementers',
        subtitle="Every implementers' call with its recording and notes, tied to the network upgrades and FIPs it discussed.",
        body_html=body,
    )


def implementers_card(ctx):
    """Full implementers' call log table."""
    calls, source = ctx['calls'], ctx['calls_source']
    head = "<section class=\"card\" id=\"calls-log\"><div class=\"card-head\"><h2>All implementers' calls"
    if source is None:
        return (head + '</h2></div><div class="card-body"><p class="empty">'
                "The implementers' call log couldn't be loaded on this run.</p></div></section>")
    up_by = {}
    for num, hits in ctx['upgrade_conv'].items():
        for c, _ in hits:
            up_by.setdefault(id(c), []).append(num)
    rows = []
    for c in calls[:CALLS_SHOWN]:
        ups_for = sorted(up_by.get(id(c), []), key=lambda n: (isinstance(n, int), n), reverse=True)
        chips = ''.join(f'<a class="chip" href="network-upgrades.html#nv{esc(str(n))}">NV{esc(str(n))}</a>' for n in ups_for[:3])
        chips += ''.join(fip_chip(f) for f in c['fips'][:6])
        search = ' '.join([c['title'], fmt_date(c['date']), c['summary'], ' '.join(c['types']),
                           ' '.join('FIP-' + f + ' ' + str(int(f)) for f in c['fips']),
                           ' '.join(f'nv{n}' for n in ups_for)]).lower()
        summary = f'<div class="muted small">{esc(c["summary"][:200])}</div>' if c['summary'] else ''
        rows.append(f'<tr data-search="{esc(search)}"><td class="nowrap">{fmt_date(c["date"])}</td>'
                    f'<td class="title-cell"><strong>{esc(c["title"])}</strong>{summary}</td>'
                    f'<td><div class="chips">{chips}</div></td>'
                    f'<td class="nowrap">{call_links(c) or "<span class=muted>—</span>"}</td></tr>')
    if rows:
        table = ('<div class="table-scroll"><table class="data" id="calls"><thead><tr><th>Date</th><th>Call</th>'
                 '<th>Upgrades and FIPs</th><th>Links</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'
                 '<p class="empty" id="no-call-match" hidden>No calls match.</p>')
    else:
        table = "<p class=\"empty\">No implementers' calls logged yet.</p>"
    src = {'public': "the implementers' public meeting notes "
                     "(<a href=\"https://filecoindev.notion.site/6e47427dee6c4095a90fec4bbe89929d\" target=\"_blank\" rel=\"noopener\">filecoindev.notion.site</a>)",
           'notion': "the implementers' meeting log in Notion"}.get(source, "an export of the implementers' meeting log")
    more = f' Showing the latest {CALLS_SHOWN} of {len(calls)}.' if len(calls) > CALLS_SHOWN else ''
    return (head + f' ({len(calls)})</h2>'
            '<input class="search" type="search" placeholder="Filter by FIP, NV or topic" '
            "aria-label=\"Filter implementers' calls\" oninput=\"filterCalls(this.value)\"></div>"
            f'<div class="card-body">{table}<p class="note">From {src}. An upgrade tag means the call named that '
            f'upgrade or discussed its FIPs; mentions are not decisions.{more}</p></div></section>'
            '<script>function filterCalls(q) { q = (q || "").toLowerCase().trim();'
            ' var rows = document.querySelectorAll("#calls tbody tr"), shown = 0;'
            ' rows.forEach(function (r) { var hit = !q || r.getAttribute("data-search").indexOf(q) !== -1; r.hidden = !hit; if (hit) shown++; });'
            ' var e = document.getElementById("no-call-match"); if (e) e.hidden = shown !== 0; }</script>')


# ---------------------------------------------------------------------------
# FIP lifecycle
# ---------------------------------------------------------------------------

# Paraphrased from FIP-0001 ("FIP Work Flow"). Keys are README statuses.
STAGES = [
    ('Discussion', 'Idea', 'An idea is raised and debated in FIP Discussions before anyone writes a draft.',
     'The author opens a draft PR on the FIPs repo when the idea has support.',
     'FIP Discussions'),
    ('Draft', 'Draft', 'The FIP editor has merged the draft and assigned a number. Authors keep refining it through follow-up PRs.',
     'The editor moves it to Last Call when it\'s mature and, for non-core FIPs, implemented.',
     'FIP Discussions, Core Devs, implementers\' calls'),
    ('Last Call', 'Last Call', 'A final review window, normally 14 days (the review-period-end date). Material changes send it back to Draft.',
     'A clean Last Call makes a core FIP Accepted, or any other FIP Final.',
     'The FIP\'s discussion thread'),
    ('Accepted', 'Accepted', 'Core FIPs only. The proposal is approved and in implementers\' hands; when it ships is decided in network upgrade planning, outside the FIP process.',
     'It becomes Final once implemented in at least two clients, the spec is updated and it\'s adopted, normally when its network upgrade activates.',
     'Upgrade scope planning, implementers\' calls, Core Devs'),
    ('Final', 'Final', 'The current state of the art. Only errata are fixed from here.',
     'Can later be Superseded by a newer Final FIP.',
     '—'),
]
SIDE_STAGES = [
    ('Deferred', 'Core FIPs put off for a future network upgrade. Can return to Draft.'),
    ('Rejected', 'Fundamentally broken, or a core FIP Core Devs won\'t implement.'),
    ('Withdrawn', 'The author has withdrawn the proposal.'),
    ('Superseded', 'Was Final, but another Final FIP has replaced it.'),
    ('Active', 'Informational or organizational FIPs that are never "done" and may be updated in place, such as FIP-0001.'),
]
TIMING_WINDOW_DAYS = 730


def _median(xs):
    xs = sorted(xs)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def lifecycle_page(ctx):
    fips, files, history = ctx['fips'], ctx['files'], ctx['history']
    now = datetime.now(timezone.utc)
    shipped = cd.fip_upgrades(ctx['upgrades'])
    md = cd.last_discussed(ctx['meetings'])
    impl_md = {}
    for c in ctx['calls']:
        for f in c['fips']:
            impl_md.setdefault(f, c)

    # Next upgrade's scope candidates, from the planning discussion
    live = [x['number'] for x in ctx['upgrades'] if x['mainnet'] and x['mainnet'] <= now and isinstance(x['number'], int)]
    latest_live = max(live) if live else 0
    plan = next((p for p in sorted(ctx.get('planning') or [], key=lambda p: p['nv']) if p['nv'] > latest_live), None)
    candidates = {r['fip']: r for r in (plan['scope'] if plan else []) if r['fip']}

    by_status = {}
    for n, f in fips.items():
        by_status.setdefault(f['status'], []).append(n)

    # Typical time in each stage: completed stints that ended in the window
    cutoff = now - timedelta(days=TIMING_WINDOW_DAYS)
    stint = {}
    for n, entries in history.items():
        for a, b in zip(entries, entries[1:]):
            if b['since'] >= cutoff and a['status'] != b['status']:
                stint.setdefault((a['status'], b['status']), []).append((b['since'] - a['since']).days)
    def typical(frm, *tos):
        xs = [d for to in tos for d in stint.get((frm, to), [])]
        med = _median(xs)
        return (f'{med:.0f} days', len(xs)) if med is not None else ('—', 0)

    discussions = ctx['discussions']
    counts = {'Discussion': len([d for d in discussions or [] if (now - d['updated']).days <= 30]) if discussions is not None else None}
    for key, *_ in STAGES[1:]:
        counts[key] = len(by_status.get(key, []))
    next_time = {
        'Draft': typical('Draft', 'Last Call'),
        'Last Call': typical('Last Call', 'Accepted', 'Final'),
        'Accepted': typical('Accepted', 'Final'),
    }

    # Flow strip
    steps = []
    for key, label, *_ in STAGES:
        n = counts.get(key)
        nt = next_time.get(key)
        sub = (f'median {nt[0]} to next' if nt and nt[1] else ('active in 30 days' if key == 'Discussion' else 'all time' if key == 'Final' else ''))
        cls = {'Draft': 'draft', 'Last Call': 'lastcall', 'Accepted': 'accepted', 'Final': 'final'}.get(key, 'idea')
        steps.append(f'<a class="stage {cls}" href="#stage-{key.lower().replace(" ", "-")}"><span class="stage-name">{label}</span>'
                     f'<span class="stage-n">{"—" if n is None else n}</span><span class="stage-sub">{sub}</span></a>')
    side = ''.join(f'<span class="side-stage">{esc(k)} <strong>{len(by_status.get(k, []))}</strong></span>' for k, _ in SIDE_STAGES)
    flow = (f'<section class="card"><div class="card-head"><h2>How a FIP moves</h2>'
            '<span class="hint">The path in FIP-0001, with how many FIPs are at each stage today.</span></div><div class="card-body">'
            f'<div class="flow">{"<span class=arrow aria-hidden=true>→</span>".join(steps)}</div>'
            f'<div class="side-stages"><span class="muted small">Off the main path:</span>{side}</div>'
            '<p class="note">Core FIPs go Last Call → Accepted → Final (when shipped in a network upgrade). '
            'Other FIPs go straight from Last Call to Final. Medians cover stage changes in the last 2 years.</p>'
            '</div></section>')

    # Board: where the open FIPs are now
    def since(n):
        d = u.current_status_since(history, n, fips[n]['status'])
        return d, (now - d).days if d else None

    def where_discussed(n):
        bits = []
        if n in md:
            m = md[n]
            bits.append(f'Core Devs #{m["number"]} · {fmt_date(m["date"], False)}')
        if n in impl_md:
            bits.append(f'Implementers · {fmt_date(impl_md[n]["date"], False)}')
        return ' · '.join(bits)

    def item(n, extra=''):
        d, days = since(n)
        age = f'{u.humanize_days(days)} in stage' if days is not None else ''
        disc = where_discussed(n)
        return (f'<li><div>{fip_a(n)} <span class="item-title">{esc(fips[n]["title"])}</span></div>'
                f'<div class="muted small">{" · ".join(x for x in (age, extra) if x)}</div>'
                f'{f"<div class=muted small>Last discussed: {esc(disc)}</div>" if disc else ""}</li>')

    def accepted_note(n):
        if n in shipped:
            x = shipped[n]
            return f'Shipped in NV{x["number"]} {esc(x["name"])}; awaiting Final'
        if n in candidates:
            r = candidates[n]
            return f'NV{plan["nv"]} candidate ({READY_SHORT[r["readiness"]].lower()})'
        return 'Not in an upgrade yet'

    def draft_note(n):
        if n in candidates:
            r = candidates[n]
            return f'NV{plan["nv"]} candidate ({READY_SHORT[r["readiness"]].lower()})'
        return ''

    lc_end = {w['number']: w for w in ctx['open_lc']}
    cols = [
        ('Draft', 'draft', lambda n: draft_note(n)),
        ('Last Call', 'lastcall', lambda n: (f'Review ends {fmt_date(lc_end[n]["end"], False)}' + (' (est.)' if lc_end[n]['estimated_end'] else '')) if n in lc_end else ''),
        ('Accepted', 'accepted', accepted_note),
        ('Deferred', 'deferred', lambda n: draft_note(n)),
    ]
    col_html = []
    for key, cls, note in cols:
        nums = sorted(by_status.get(key, []), key=lambda n: since(n)[0] or now)
        lis = ''.join(item(n, note(n)) for n in nums) or '<li class="muted small">None right now.</li>'
        col_html.append(f'<div class="board-col {cls}" id="stage-{key.lower().replace(" ", "-")}"><h3>{key} <span class="muted">{len(nums)}</span></h3><ul>{lis}</ul></div>')
    board = (f'<section class="card"><div class="card-head"><h2>Where open FIPs are now</h2>'
             '<span class="hint">Every FIP that hasn\'t reached a final outcome, longest in stage first.</span></div>'
             f'<div class="card-body"><div class="board">{"".join(col_html)}</div>'
             f'<p class="note">Time in stage is measured from when the FIPs README showed the change, which can lag the decision by a few days.'
             f'{" Upgrade candidates come from the NV" + str(plan["nv"]) + " planning discussion." if plan else ""}</p></div></section>')

    # Shipped but still Accepted: a nudge for editors
    waiting_final = [n for n in by_status.get('Accepted', []) if n in shipped and shipped[n]['mainnet'] and shipped[n]['mainnet'] <= now]
    nudge = ''
    if waiting_final:
        rows = ''.join(f'<tr><td>{fip_a(n)}</td><td class="title-cell">{esc(fips[n]["title"])}</td>'
                       f'<td class="nowrap">NV{shipped[n]["number"]} · {fmt_date(shipped[n]["mainnet"])}</td></tr>' for n in waiting_final)
        nudge = (f'<section class="card"><div class="card-head"><h2>Live on mainnet, still Accepted ({len(waiting_final)})</h2>'
                 '<span class="hint">Shipped in an activated upgrade but not yet marked Final. Flagged for editors; it may be intentional.</span></div>'
                 f'<div class="card-body"><div class="table-scroll"><table class="data"><thead><tr><th>FIP</th><th>Title</th><th>Shipped</th></tr></thead>'
                 f'<tbody>{rows}</tbody></table></div></div></section>')

    # Stage guide
    guide_rows = []
    for key, label, what, nxt, where in STAGES:
        n = counts.get(key)
        guide_rows.append(f'<tr><td class="nowrap"><strong>{label}</strong></td><td>{esc(what)}</td><td>{esc(nxt)}</td>'
                          f'<td class="small">{esc(where)}</td><td class="num">{"—" if n is None else n}</td></tr>')
    for key, what in SIDE_STAGES:
        guide_rows.append(f'<tr><td class="nowrap">{key}</td><td colspan="3">{esc(what)}</td><td class="num">{len(by_status.get(key, []))}</td></tr>')
    guide = (f'<section class="card"><div class="card-head"><h2>Stage guide</h2>'
             '<span class="hint">Paraphrased from <a href="https://github.com/filecoin-project/FIPs/blob/master/FIPS/fip-0001.md" target="_blank" rel="noopener">FIP-0001</a>, which is the authority.</span></div>'
             '<div class="card-body"><div class="table-scroll"><table class="data"><thead><tr><th>Stage</th><th>What it means</th><th>What moves it on</th><th>Where it\'s discussed</th><th class="num">Now</th></tr></thead>'
             f'<tbody>{"".join(guide_rows)}</tbody></table></div></div></section>')

    # Timing table
    trans = [('Draft', ('Last Call',), 'Draft → Last Call'), ('Last Call', ('Accepted',), 'Last Call → Accepted'),
             ('Last Call', ('Final',), 'Last Call → Final (non-core)'), ('Accepted', ('Final',), 'Accepted → Final'),
             ('Last Call', ('Draft',), 'Last Call → back to Draft'), ('Draft', ('Deferred',), 'Draft → Deferred'),
             ('Draft', ('Withdrawn',), 'Draft → Withdrawn')]
    trows = ''.join(f'<tr><td>{esc(lbl)}</td><td class="num">{typical(f, *t)[1]}</td><td class="num">{typical(f, *t)[0]}</td></tr>'
                    for f, t, lbl in trans if typical(f, *t)[1])
    timing = (f'<section class="card"><div class="card-head"><h2>How long stages take</h2>'
              '<span class="hint">Stage changes in the last 2 years, from the FIPs README history.</span></div>'
              '<div class="card-body"><div class="table-scroll"><table class="data"><thead><tr><th>Change</th><th class="num">FIPs</th><th class="num">Median time</th></tr></thead>'
              f'<tbody>{trows}</tbody></table></div>'
              '<p class="note">Every change, with dates and commits, is on the <a href="fips-timeline-tracker.html">Timeline</a>.</p></div></section>'
              ) if trows else ''

    body = '\n'.join([flow, board, nudge, timing, guide])
    return page(
        title='FIP Lifecycle',
        description='How a Filecoin Improvement Proposal moves from idea to Final, where every open FIP is now and how long each stage takes.',
        current='lifecycle',
        subtitle='How a FIP moves from idea to Final, where every open FIP is right now, and how long each stage usually takes.',
        body_html=body,
    )


# Old address of the lifecycle page, which is now the home page.
REDIRECT_HOME = '''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>FIP Lifecycle</title>
<meta http-equiv="refresh" content="0; url=./">
<link rel="canonical" href="./"></head>
<body><p>The FIP lifecycle is now the home page: <a href="./">open it</a>.</p></body></html>
'''


READY_PILL = {'ready': 'approved', 'risk': 'waiting', 'deferred-in': 'changes', 'deferred-out': '', 'none': '', 'unknown': ''}
READY_SHORT = {'ready': 'Ready', 'risk': 'At risk', 'deferred-in': 'Carried over', 'deferred-out': 'Next upgrade',
               'none': 'Not upgrade-bound', 'unknown': '—'}


def scope_planning_card(ctx):
    """Scope planning for upgrades that haven't shipped yet, from the core-devs planning discussions."""
    planning = ctx.get('planning')
    if planning is None:
        return ('<section class="card" id="scope"><div class="card-head"><h2>Scope planning</h2></div><div class="card-body">'
                '<p class="empty">The planning discussions couldn\'t be loaded on this run. '
                '<a href="https://github.com/filecoin-project/core-devs/discussions" target="_blank" rel="noopener">Browse them on GitHub</a>.</p>'
                '</div></section>')
    now = datetime.now(timezone.utc)
    live = [x['number'] for x in ctx['upgrades'] if x['mainnet'] and x['mainnet'] <= now and isinstance(x['number'], int)]
    latest_live = max(live) if live else 0
    plans = [p for p in planning if p['nv'] > latest_live]
    if not plans:
        return ''
    sections = []
    for p in plans:
        counts = {}
        for r in p['scope']:
            counts[r['readiness']] = counts.get(r['readiness'], 0) + 1
        tally = ' · '.join(f'{n} {READY_SHORT[k].lower()}' for k, n in counts.items() if k != 'unknown')
        rows = []
        for r in p['scope']:
            name = esc(r['name'])
            if r['fip']:
                name = re.sub(r'FIP-?\d+', fip_a(r['fip']), name, count=1)
            elif r['link']:
                name = f'<a href="{esc(r["link"])}" target="_blank" rel="noopener">{name}</a>'
            pill = f'<span class="pill {READY_PILL[r["readiness"]]}" title="{esc(r["readiness_label"])}">{READY_SHORT[r["readiness"]]}</span>'
            summary = f'<div class="muted small">{esc(r["summary"][:220])}</div>' if r['summary'] else ''
            notes = f'<div class="small" style="margin-top:4px"><strong>Open:</strong> {esc(r["notes"][:200])}</div>' if r['notes'] else ''
            rows.append(f'<tr><td class="nowrap">{pill}</td><td class="title-cell">{name}{summary}{notes}</td>'
                        f'<td class="small">{esc(r["status"])}</td><td class="small">{esc(r["timeline"])}</td>'
                        f'<td class="num">{esc(r["size"]) or "<span class=muted>—</span>"}</td></tr>')
        table = ('<div class="table-scroll"><table class="data"><thead><tr><th>Readiness</th><th>Candidate</th>'
                 '<th>Status &amp; progress</th><th>Timeline</th><th class="num">Size</th></tr></thead><tbody>'
                 + ''.join(rows) + '</tbody></table></div>') if rows else \
            '<p class="empty">No scope table in the planning discussion yet.</p>'
        ms = ''.join(f'<li><span>{esc(m["name"])}</span><strong>{esc(m["date"])}</strong></li>' for m in p['milestones'])
        ms_html = f'<h3 class="sub-h">Milestones</h3><ul class="milestones">{ms}</ul>' if ms else ''
        naming = f'<p class="small" style="margin-top:10px"><strong>Name:</strong> {esc(p["naming"])}</p>' if p['naming'] else ''
        hits = ctx['planning_conv'].get(p['nv'], [])
        convo = upgrade_convo_html(hits, open_=False) if hits else ''
        sections.append(
            f'<div class="up-card" id="plan-nv{p["nv"]}"><div class="up-head"><h3><span class="nv">NV{p["nv"]}</span>Scope planning</h3>'
            f'<span class="pill waiting">Planning</span></div>'
            f'<div class="up-dates"><span>{len(p["scope"])} candidates{": " + tally if tally else ""}</span>'
            f'<span>Updated {ago(p["updated"])}</span>'
            f'<span><a href="{esc(p["url"])}" target="_blank" rel="noopener">Planning discussion →</a></span></div>'
            f'{table}{ms_html}{naming}{convo}</div>')
    return (f'<section class="card" id="scope"><div class="card-head"><h2>Scope planning</h2>'
            '<span class="hint">What\'s being considered for the next upgrade, from the public planning discussions in core-devs. '
            'Candidates aren\'t commitments; scope is set by Core Devs and the implementers.</span></div>'
            f'<div class="card-body"><div class="up-list">{"".join(sections)}</div>'
            '<p class="note">Size: S under 2 engineer-weeks, M 2–4, L over 4.</p></div></section>')


def upgrades_page(ctx):
    fips, files, upgrades = ctx['fips'], ctx['files'], ctx['upgrades']
    now = datetime.now(timezone.utc)
    shipped = cd.fip_upgrades(upgrades)
    latest_live = next((x for x in upgrades if x['mainnet'] and x['mainnet'] <= now), None)

    cards = []
    for x in upgrades:
        upcoming = x['mainnet'] and x['mainnet'] > now
        state = ('<span class="pill waiting">Upcoming</span>' if upcoming else
                 '<span class="pill approved">Live</span>' if x['mainnet'] else '<span class="pill">Not scheduled</span>')
        fip_lines = ''.join(
            f'<div>{fip_link(f)} {esc((fips.get(f) or {}).get("title") or (files.get(f) or {}).get("title") or "")}</div>'
            for f in x['fips']) or '<div class="muted">No FIPs (implementation-only upgrade)</div>'
        actors = (f'<a href="https://github.com/filecoin-project/builtin-actors/releases/tag/{esc(x["actors"])}" target="_blank" rel="noopener">actors {esc(x["actors"])}</a>'
                  if x['actors'] else '')
        epoch = f' · epoch {x["mainnet_epoch"]:,}' if x['mainnet_epoch'] else ''
        doc = f'<a href="{esc(x["doc_url"])}" target="_blank" rel="noopener">Upgrade notes</a>' if x['doc_url'] else ''
        convo = upgrade_convo_html(ctx['upgrade_conv'].get(x['number'], []), open_=bool(upcoming or x is latest_live))
        cards.append(f'''<div class="up-card{" latest" if x is latest_live else ""}" id="nv{esc(str(x["number"]))}">
<div class="up-head"><h3><span class="nv">NV{esc(str(x["number"]))}</span>{esc(x["name"])}</h3>{state}</div>
<div class="up-dates"><span>Mainnet: <strong>{fmt_date(x["mainnet"])}</strong>{epoch}</span><span>Calibration: {fmt_date(x["calibration"])}</span>{f"<span>{actors}</span>" if actors else ""}{f"<span>{doc}</span>" if doc else ""}</div>
<div class="up-fips">{fip_lines}</div>{convo}</div>''')

    # Accepted FIPs not yet in any upgrade
    waiting = [n for n, f in sorted(fips.items()) if f['status'] == 'Accepted' and n not in shipped]
    md = cd.last_discussed(ctx['meetings'])
    waiting_rows = ''.join(f'''<tr><td>{fip_link(n)}</td><td class="title-cell">{esc(fips[n]["title"])}</td>
<td class="nowrap">{f'<a href="{esc(md[n]["notes_url"] or "#")}" target="_blank" rel="noopener">Core Devs #{md[n]["number"]}</a> · {fmt_date(md[n]["date"])}' if n in md else '<span class="muted">—</span>'}</td></tr>''' for n in waiting)
    waiting_card = f'''<section class="card"><div class="card-head"><h2>Accepted, not yet in an upgrade</h2>
<span class="hint">Accepted FIPs that aren't listed in any network upgrade so far.</span></div>
<div class="card-body">{f"""<div class="table-scroll"><table class="data"><thead><tr><th>FIP</th><th>Title</th><th>Last discussed</th></tr></thead><tbody>{waiting_rows}</tbody></table></div>""" if waiting_rows else '<p class="empty">Every Accepted FIP is in a network upgrade.</p>'}</div></section>'''

    body = '\n'.join([
        scope_planning_card(ctx),
        waiting_card,
        f'''<section class="card"><div class="card-head"><h2>All network upgrades ({len(upgrades)})</h2>
<span class="hint">From <a href="https://github.com/filecoin-project/core-devs/blob/master/upgrades.json" target="_blank" rel="noopener">upgrades.json</a> in the core-devs repo.</span></div>
<div class="card-body"><div class="up-list">{"".join(cards)}</div></div></section>''',
    ])
    return page(
        title='Network Upgrades',
        description='Every Filecoin network upgrade with activation dates, actors versions and the FIPs it shipped.',
        current='upgrades',
        subtitle='What shipped when: every network upgrade, its activation dates, the FIPs it included and the calls where it was discussed.',
        body_html=body,
    )


# ---------------------------------------------------------------------------

def load_context():
    print('Cloning / updating FIPs and core-devs repos...')
    fips_repo = u.get_fips_repo()
    cd_repo = cd.get_core_devs_repo()
    fips = {f['number']: f for f in u.parse_fip_table(u.read_readme(fips_repo))}
    history, events = u.build_status_history(fips_repo)
    files = u.load_fip_files(fips_repo)
    open_lc, _ = u.last_call_windows(history, files, fips)
    print('Fetching PRs, discussions and agenda issues (optional)...')
    raw_prs = u.fetch_open_prs()
    prs = u.process_prs(raw_prs, with_reviews=False) if raw_prs is not None else None
    return {
        'fips': fips, 'files': files, 'events': events, 'open_lc': open_lc, 'history': history,
        'meetings': cd.load_meetings(cd_repo), 'upgrades': cd.load_upgrades(cd_repo),
        'prs': prs,
        'prs_by_fip': u.prs_by_fip(prs) if prs else {},
        'discussions': u.fetch_discussions('filecoin-project', 'FIPs', 15),
        'agenda': cd.fetch_open_agenda(),
    }


def add_conversations(ctx):
    """Load implementers' calls and link them and Core Devs meetings to upgrades."""
    calls, source = impl.load_calls()
    for m in ctx['meetings']:
        m['kind'] = 'coredevs'
    for c in calls:
        c['kind'] = 'implementers'
    ctx['calls'], ctx['calls_source'] = calls, source
    ctx['upgrade_conv'] = cd.upgrade_conversations(ctx['upgrades'], ctx['meetings'] + calls)
    # Planned upgrades: only calls that name the upgrade count (its FIPs aren't settled yet).
    ctx['planning'] = sp.fetch_planning()
    planned = [{'number': p['nv'], 'name': '', 'fips': [], 'mainnet': None} for p in ctx['planning'] or []]
    ctx['planning_conv'] = cd.upgrade_conversations(planned, ctx['meetings'] + calls)


def main():
    ctx = load_context()
    add_conversations(ctx)
    CTX.update(ctx)
    if not ctx['fips']:
        print('ERROR: No FIPs parsed. Aborting to avoid overwriting pages.')
        return 1
    for name, fn in (('index.html', lifecycle_page), ('overview.html', overview),
                     ('fip-lifecycle.html', lambda _ctx: REDIRECT_HOME), ('core-devs.html', core_devs_page),
                     ('implementers.html', implementers_page),
                     ('network-upgrades.html', upgrades_page)):
        with open(name, 'w', encoding='utf-8') as f:
            f.write(fn(ctx))
        print(f'Generated {name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
