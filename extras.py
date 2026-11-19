#!/usr/bin/env python3
"""Extra views built from the records the hub has already loaded.

  editors.html    Checklist for FIP editors: overdue Last Calls, README/file
                  status mismatches, shipped-but-Accepted FIPs, idle PRs,
                  quiet Drafts and FIPs with no discussion link
  data.json       Every FIP and upgrade as plain JSON, for anyone to build on

Also: what_next() (the "where it's at" line on each FIP page), affected()
(groups a FIP's own text mentions), upgrade_releases() and readiness_card()
(client releases named in each upgrade's notes), and the optional features
switched on in data/site.json.

Everything here reports what the records say. It doesn't decide or rank.
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import fip_utils as u
from fip_utils import html_escape as esc

IDLE_PR_DAYS = 30
QUIET_DRAFT_DAYS = 365
ISSUES_URL = 'https://github.com/FilecoinFoundationWeb/fips-dashboard/issues/new'
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'site.json')


# ---------------------------------------------------------------------------
# Site settings (data/site.json): optional features, all off by default
# ---------------------------------------------------------------------------

def config():
    try:
        with open(CONFIG_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def analytics_snippet():
    """Privacy-friendly page counts, only when data/site.json names a provider."""
    a = config().get('analytics') or {}
    provider = (a.get('provider') or '').lower()
    if provider == 'plausible' and a.get('domain'):
        return f'<script defer data-domain="{esc(a["domain"])}" src="https://plausible.io/js/script.js"></script>'
    if provider == 'goatcounter' and a.get('goatcounter_code'):
        code = esc(a['goatcounter_code'])
        return f'<script data-goatcounter="https://{code}.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script>'
    return ''


def digest_signup_url():
    return (config().get('digest_signup_url') or '').strip()


def giscus_embed(discussion_urls):
    """The FIP's own GitHub discussion, embedded with giscus, when it's set up.

    giscus posts as the visitor's own GitHub account. It needs the giscus app
    installed on the repo that holds the discussions, and its IDs in
    data/site.json; until then this returns ''.
    """
    g = config().get('giscus') or {}
    repo, repo_id, cat_id = g.get('repo'), g.get('repo_id'), g.get('category_id')
    if not (repo and repo_id and cat_id):
        return ''
    for url in discussion_urls or []:
        m = re.match(rf'https://github\.com/{re.escape(repo)}/discussions/(\d+)', url, re.I)
        if m:
            return ('<div class="giscus-wrap"><script src="https://giscus.app/client.js" '
                    f'data-repo="{esc(repo)}" data-repo-id="{esc(repo_id)}" data-category-id="{esc(cat_id)}" '
                    f'data-mapping="number" data-term="{m.group(1)}" data-reactions-enabled="1" data-emit-metadata="0" '
                    'data-input-position="top" data-theme="preferred_color_scheme" data-lang="en" data-loading="lazy" '
                    'crossorigin="anonymous" async></script></div>')
    return ''


def report_url(where, page_url=''):
    """Pre-filled GitHub issue for reporting a data problem."""
    title = f'Data problem: {where}'
    body = (f'Page: {page_url or where}\n\nWhat looks wrong:\n\n\nWhat the record says (link if you have one):\n')
    return f'{ISSUES_URL}?title={quote(title)}&body={quote(body)}&labels=data'


# ---------------------------------------------------------------------------
# Who a FIP's text mentions
# ---------------------------------------------------------------------------

AUDIENCES = [
    ('Storage providers', r'storage providers?|\bSPs?\b|miner actor|\bsectors?\b|PoRep|WindowPoSt|sealing'),
    ('Clients and data onboarding', r'\bclients?\b|\bdeals?\b|datacap|FIL\+|Filecoin Plus|\bpieces?\b'),
    ('Smart contract developers', r'FEVM|\bEVM\b|smart contracts?|Solidity|precompile'),
    ('Wallets and exchanges', r'\bwallets?\b|\bexchanges?\b|custod'),
    ('RPC and tooling', r'\bJSON-RPC\b|\bRPC\b|\bAPI\b|block explorers?|\btooling\b'),
]


def fip_body(repo, num):
    try:
        with open(os.path.join(repo or '', 'FIPS', f'fip-{num}.md'), encoding='utf-8', errors='replace') as f:
            text = f.read()
    except OSError:
        return ''
    return re.sub(r'^---\n.*?\n---\n', '', text, count=1, flags=re.S)


def affected(repo, num):
    """Groups the FIP's own text mentions at least twice. Not an impact assessment."""
    body = fip_body(repo, num)
    return [name for name, pat in AUDIENCES if len(re.findall(pat, body, re.I)) >= 2]


# ---------------------------------------------------------------------------
# Where a FIP is at, from the records
# ---------------------------------------------------------------------------

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


def what_next(n, ctx, base=''):
    """Short lines on what the records show this FIP is waiting on."""
    now = datetime.now(timezone.utc)
    fip, f = ctx['fips'].get(n) or {}, ctx['files'].get(n) or {}
    status = fip.get('status') or f.get('_status') or ''
    lines = []
    lc = next((w for w in ctx['open_lc'] if w['number'] == n), None)
    if lc:
        if lc['end'] < now:
            lines.append(f'Review period ended {lc["end"]:%b %-d}; waiting on the FIP editors to move it on.')
        else:
            lines.append(f'In final review until {lc["end"]:%b %-d}.')
    shipped = next((x for x in ctx['upgrades'] if n in x['fips']), None)
    if status == 'Accepted':
        if shipped and shipped['mainnet'] and shipped['mainnet'] <= now:
            lines.append(f'Shipped in NV{shipped["number"]}; waiting to be marked Final.')
        elif shipped:
            lines.append(f'Scheduled for NV{shipped["number"]}.')
        elif not any(r.get('fip') == n for p in ctx.get('planning') or [] for r in p['scope']):
            lines.append('Accepted but not yet in a network upgrade or its planning.')
    for p in (ctx.get('prs_by_fip') or {}).get(n) or []:
        if p['idle_days'] >= 7:
            lines.append(f'<a href="{esc(p["url"])}" target="_blank" rel="noopener">PR #{p["number"]}</a> '
                         f'has had no activity for {_days(p["idle_days"])}.')
    if f.get('_status') and status and f['_status'] != status:
        lines.append(f'The README says {esc(status)} but the FIP file says {esc(f["_status"])}.')
    if status == 'Draft':
        last = _last_activity(n, ctx)
        if last and (now - last).days >= 180:
            lines.append(f'No recorded activity since {last:%b %Y}.')
    if not (f.get('_discussions')):
        lines.append('No discussion link in the FIP file.')
    return lines


# ---------------------------------------------------------------------------
# Editors' checklist
# ---------------------------------------------------------------------------

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

    overdue = sorted((w for w in ctx['open_lc'] if w['end'] < now), key=lambda w: w['end'])
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
    s3, n3 = section('mismatch', 'README and FIP file disagree',
                     'The README table and the FIP\'s own <code>status:</code> line differ, or the FIP is in only one of them. The dashboard doesn\'t say which is right.',
                     ['FIP', 'Title', 'README', 'FIP file', 'Note'],
                     [f'<tr><td>{fip_a(m["number"])}</td><td class="title-cell">{esc(m["title"])}</td>'
                      f'<td>{esc(m["readme"] or "—")}</td><td>{esc(m["file"] or "—")}</td><td class="small">{esc(m["note"])}</td></tr>'
                      for m in mism], 'The README and every FIP file agree.')

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
    s5, n5 = section('quiet', f'Drafts with no activity for a year',
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

    counts = [('overdue', 'Last Calls over', n1), ('final', 'Awaiting Final', n2), ('mismatch', 'Status mismatches', n3),
              ('idle-prs', 'Idle PRs', n4 if ctx.get('prs') is not None else '—'), ('quiet', 'Quiet Drafts', n5),
              ('no-discussion', 'No discussion link', n6)]
    stats = '<section class="stats">' + ''.join(
        f'<a class="stat{" accent" if isinstance(v, int) and v and k in ("overdue", "mismatch") else ""}" href="#{k}">'
        f'<div class="label">{esc(lbl)}</div><div class="value">{v}</div></a>' for k, lbl, v in counts) + '</section>'
    intro = ('<section class="card"><div class="card-body" style="padding-top:18px">'
             '<p>Signals from the public records that may need an editor\'s attention. They are prompts, not judgments: '
             'each one links to the FIP so you can check the context. Editors decide status changes under '
             '<a href="https://github.com/filecoin-project/FIPs/blob/master/FIPS/fip-0001.md" target="_blank" rel="noopener">FIP-0001</a>.</p>'
             '</div></section>')
    body = '\n'.join([stats, intro, s1, s2, s3, s4, s5, s6])
    return page(title='Editor checklist',
                description='Signals for FIP editors from the public records: overdue Last Calls, status mismatches, idle PRs and FIPs awaiting Final.',
                current='editors', subtitle='What the records suggest may need a FIP editor\'s attention, gathered in one place.',
                body_html=body)


# ---------------------------------------------------------------------------
# Network upgrade readiness
# ---------------------------------------------------------------------------

CLIENTS = [('Lotus', r'filecoin-project/lotus'), ('Venus', r'filecoin-project/venus'),
           ('Forest', r'ChainSafe/forest'), ('Curio', r'filecoin-project/curio')]


def upgrade_releases(cd_repo, number):
    """[(client, version, url)] named in core-devs 'Network Upgrades/vNN.md'."""
    path = os.path.join(cd_repo or '', 'Network Upgrades', f'v{number}.md')
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            text = f.read()
    except OSError:
        return []
    out, seen = [], set()
    for name, repo in CLIENTS:
        for m in re.finditer(rf'https://github\.com/{repo}/releases/tag/([^\s)\]>]+)', text, re.I):
            key = (name, m.group(1))
            if key not in seen:
                seen.add(key)
                out.append((name, m.group(1), m.group(0)))
    return out


def readiness_card(ctx, fmt_date, fip_link):
    """'Get ready' checklist for the next upgrade (or the one that just shipped)."""
    now = datetime.now(timezone.utc)
    ups = ctx['upgrades']
    upcoming = sorted((x for x in ups if x['mainnet'] and x['mainnet'] > now), key=lambda x: x['mainnet'])
    recent = [x for x in ups if x['mainnet'] and now - timedelta(days=30) <= x['mainnet'] <= now]
    x = upcoming[0] if upcoming else (recent[0] if recent else None)
    if not x:
        return ''
    rel = upgrade_releases(ctx.get('cd_repo'), x['number'])
    live = x['mainnet'] <= now
    when = (f'activated on mainnet {fmt_date(x["mainnet"])}' if live else
            f'activates on mainnet {fmt_date(x["mainnet"])}, in {(x["mainnet"] - now).days} days')
    epoch = f' at epoch {x["mainnet_epoch"]:,}' if x.get('mainnet_epoch') else ''
    cal = (f'<li><strong>Calibration:</strong> {"activated" if x["calibration"] and x["calibration"] <= now else "activates"} '
           f'{fmt_date(x["calibration"])}. Test there first.</li>' if x.get('calibration') else '')
    rel_html = (''.join(f'<li><strong>{esc(c)}:</strong> <a href="{esc(url)}" target="_blank" rel="noopener">{esc(v)}</a> or later</li>'
                        for c, v, url in rel)
                or '<li class="muted">No client releases are named in the upgrade notes yet. They\'re usually announced in the implementers\' calls.</li>')
    fips = ''.join(f'<li>{fip_link(f)} {esc((ctx["fips"].get(f) or {}).get("title", ""))}</li>' for f in x['fips']) \
        or '<li class="muted">No FIPs (implementation-only upgrade).</li>'
    doc = (f'<a class="btn" href="{esc(x["doc_url"])}" target="_blank" rel="noopener">Upgrade notes ↗</a>' if x.get('doc_url') else '')
    return (f'<section class="card" id="readiness"><div class="card-head"><h2>Get ready for NV{x["number"]} {esc(x["name"])}</h2>'
            f'<span class="hint">For node operators and storage providers. From the core-devs upgrade notes; your client\'s release notes are the authority.</span></div>'
            f'<div class="card-body"><div class="grid-2"><div>'
            f'<p><strong>NV{x["number"]}</strong> {when}{epoch}.</p>'
            f'<h3 class="sub-h">Upgrade your node to at least</h3><ul class="topics">{rel_html}</ul>'
            f'<h3 class="sub-h">Dates</h3><ul class="topics">{cal}<li><strong>Mainnet:</strong> {fmt_date(x["mainnet"])}{epoch}</li>'
            f'{"<li><strong>Actors:</strong> " + esc(x["actors"]) + "</li>" if x.get("actors") else ""}</ul></div>'
            f'<div><h3 class="sub-h">What changes</h3><ul class="topics">{fips}</ul>'
            f'<div class="btn-row">{doc}<a class="btn" href="implementers.html">Implementers\' calls</a></div></div></div></div></section>')


# ---------------------------------------------------------------------------
# data.json
# ---------------------------------------------------------------------------

def _iso(d):
    return d.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') if d else None


def data_json(ctx):
    now = datetime.now(timezone.utc)
    shipped = {}
    for x in ctx['upgrades']:
        for f in x['fips']:
            shipped.setdefault(f, x)
    lc = {w['number']: w for w in ctx['open_lc']}
    out = []
    for n in sorted(set(ctx['fips']) | set(ctx['files']), key=int):
        fip, f = ctx['fips'].get(n) or {}, ctx['files'].get(n) or {}

        def lv(v):
            return v if isinstance(v, str) else ', '.join(v or [])
        status = fip.get('status') or f.get('_status')
        hist = ctx['history'].get(n) or []
        x = shipped.get(n)
        out.append({
            'number': n, 'title': fip.get('title') or f.get('title'), 'status': status,
            'file_status': f.get('_status'), 'type': lv(f.get('type')) or fip.get('type'), 'category': lv(f.get('category')) or None,
            'authors': lv(f.get('author')) or fip.get('authors'), 'created': lv(f.get('created')) or None,
            'discussions': f.get('_discussions') or [],
            'status_since': _iso(u.current_status_since(ctx['history'], n, status)),
            'history': [{'status': h['status'], 'since': _iso(h['since']), 'commit': h['sha']} for h in hist],
            'last_call': ({'start': _iso(lc[n]['start']), 'end': _iso(lc[n]['end']), 'estimated_end': lc[n]['estimated_end']}
                          if n in lc else None),
            'network_upgrade': x['number'] if x else None,
            'mentions': affected(ctx.get('fips_repo'), n),
            'file_url': u.fip_url(n), 'page_url': f'{u.SITE_URL}fip/{n}.html',
        })
    ups = [{'number': x['number'], 'name': x['name'], 'actors': x.get('actors'), 'fips': x['fips'],
            'mainnet': _iso(x['mainnet']), 'mainnet_epoch': x.get('mainnet_epoch'), 'calibration': _iso(x['calibration']),
            'releases': [{'client': c, 'version': v, 'url': url} for c, v, url in upgrade_releases(ctx.get('cd_repo'), x['number'])],
            'notes_url': x.get('doc_url')} for x in ctx['upgrades']]
    return json.dumps({
        'about': 'Filecoin FIPs and network upgrades from the public records in filecoin-project/FIPs and '
                 'filecoin-project/core-devs. Unofficial; the repos are the authority. "mentions" lists groups '
                 'the FIP text mentions, not an impact assessment.',
        'generated_at': _iso(now), 'site': u.SITE_URL, 'fips': out, 'network_upgrades': ups,
    }, ensure_ascii=False, indent=1)
