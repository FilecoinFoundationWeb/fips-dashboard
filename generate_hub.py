#!/usr/bin/env python3
"""Generate the governance hub pages:

  index.html             Overview: latest meeting, what's open, activity feed
  core-devs.html         Core Devs meetings, recordings, FIPs on the agenda
  network-upgrades.html  Network upgrades and the FIPs they shipped

Reads public data only (FIPs and core-devs repos, plus optional GitHub API
calls for discussions and open agenda issues).
"""

import re
from datetime import datetime, timedelta, timezone

import fip_utils as u
import core_devs as cd
from fip_utils import html_escape as esc
from theme import page
from generate_fips_dashboard import badge, fip_link, date_str

FEED_DAYS = 90
AGENDA_WINDOW = 6  # meetings


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
<span class="hint">Last {FEED_DAYS} days across FIPs, Core Devs and network upgrades.</span></div>
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
        cards.append(f'''<div class="up-card{" latest" if x is latest_live else ""}" id="nv{esc(str(x["number"]))}">
<div class="up-head"><h3><span class="nv">NV{esc(str(x["number"]))}</span>{esc(x["name"])}</h3>{state}</div>
<div class="up-dates"><span>Mainnet: <strong>{fmt_date(x["mainnet"])}</strong>{epoch}</span><span>Calibration: {fmt_date(x["calibration"])}</span>{f"<span>{actors}</span>" if actors else ""}{f"<span>{doc}</span>" if doc else ""}</div>
<div class="up-fips">{fip_lines}</div></div>''')

    # Accepted FIPs not yet in any upgrade
    waiting = [n for n, f in sorted(fips.items()) if f['status'] == 'Accepted' and n not in shipped]
    md = cd.last_discussed(ctx['meetings'])
    waiting_rows = ''.join(f'''<tr><td>{fip_link(n)}</td><td class="title-cell">{esc(fips[n]["title"])}</td>
<td class="nowrap">{f'<a href="{esc(md[n]["notes_url"] or "#")}" target="_blank" rel="noopener">Core Devs #{md[n]["number"]}</a> · {fmt_date(md[n]["date"])}' if n in md else '<span class="muted">—</span>'}</td></tr>''' for n in waiting)
    waiting_card = f'''<section class="card"><div class="card-head"><h2>Accepted, not yet in an upgrade</h2>
<span class="hint">Accepted FIPs that aren't listed in any network upgrade so far.</span></div>
<div class="card-body">{f"""<div class="table-scroll"><table class="data"><thead><tr><th>FIP</th><th>Title</th><th>Last discussed</th></tr></thead><tbody>{waiting_rows}</tbody></table></div>""" if waiting_rows else '<p class="empty">Every Accepted FIP is in a network upgrade.</p>'}</div></section>'''

    body = '\n'.join([
        waiting_card,
        f'''<section class="card"><div class="card-head"><h2>All network upgrades ({len(upgrades)})</h2>
<span class="hint">From <a href="https://github.com/filecoin-project/core-devs/blob/master/upgrades.json" target="_blank" rel="noopener">upgrades.json</a> in the core-devs repo.</span></div>
<div class="card-body"><div class="up-list">{"".join(cards)}</div></div></section>''',
    ])
    return page(
        title='Network Upgrades',
        description='Every Filecoin network upgrade with activation dates, actors versions and the FIPs it shipped.',
        current='upgrades',
        subtitle='What shipped when: every network upgrade, its activation dates and the FIPs it included.',
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
        'fips': fips, 'files': files, 'events': events, 'open_lc': open_lc,
        'meetings': cd.load_meetings(cd_repo), 'upgrades': cd.load_upgrades(cd_repo),
        'prs': prs,
        'prs_by_fip': u.prs_by_fip(prs) if prs else {},
        'discussions': u.fetch_discussions('filecoin-project', 'FIPs', 15),
        'agenda': cd.fetch_open_agenda(),
    }


def main():
    ctx = load_context()
    CTX.update(ctx)
    if not ctx['fips']:
        print('ERROR: No FIPs parsed. Aborting to avoid overwriting pages.')
        return 1
    for name, fn in (('index.html', overview), ('core-devs.html', core_devs_page),
                     ('network-upgrades.html', upgrades_page)):
        with open(name, 'w', encoding='utf-8') as f:
            f.write(fn(ctx))
        print(f'Generated {name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
