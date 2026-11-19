#!/usr/bin/env python3
"""Extra views built from the records the hub has already loaded.

  data.json       Every FIP and upgrade as plain JSON, for anyone to build on

Also: affected() (groups a FIP's own text mentions), upgrade_releases() and readiness_card()
(client releases named in each upgrade's notes), and the optional features
switched on in data/site.json.

Everything here reports what the records say. It doesn't decide or rank, and
it doesn't single out FIPs for how long they've been in a stage: editor-facing
checks live in the unpublished internal report (internal_report.py).
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import fip_utils as u
from fip_utils import html_escape as esc

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
