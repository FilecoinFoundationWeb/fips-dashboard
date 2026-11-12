#!/usr/bin/env python3
"""Twice-weekly governance digest email.

Short summary first (what leadership needs), then details (what the
governance lead needs): the realistic scope of the active network upgrade
and where each item stands, the timeline, FIP status changes, comment
activity on discussions and PRs, Last Call windows, and calls.

Scope comes from data/digest-scope.json (edit it when scope changes). If
that file names a different upgrade than the active planning discussion,
the digest falls back to the planning thread's green rows and says so.

Recipients are never stored in this repo. They come from the
DIGEST_RECIPIENTS secret (comma- or newline-separated) and are sent as
Bcc, so no recipient sees another's address and nothing appears in logs.

Environment (Actions secrets / variables):
  DIGEST_RECIPIENTS   addresses, comma/newline separated (secret)
  SMTP_HOST           e.g. smtp.gmail.com
  SMTP_PORT           465 (SSL) or 587 (STARTTLS); default 465
  SMTP_USERNAME       login for the sending account (secret)
  SMTP_PASSWORD       app password / API key (secret)
  DIGEST_FROM         From: address; defaults to SMTP_USERNAME
  DIGEST_HOURS        look-back window; default 168 (one week)
  GITHUB_TOKEN        for discussion and comment data (GraphQL)

Without SMTP settings it writes digest-preview.html and skips sending.
"""

import html as htmllib
import json
import os
import re
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import fip_utils as u
from fip_utils import html_escape as esc

SITE = 'https://thatguyllc.github.io/fips-dashboard/'
SCOPE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'digest-scope.json')
BATCH = 90          # stay under per-message recipient caps (Gmail SMTP: 100)
STALE_DAYS = 21     # scoped item with no activity this long is flagged

C = {
    'ink': '#0B1B2E', 'muted': '#5B6B80', 'line': '#E3E8EF', 'bg': '#F4F7FB', 'blue': '#0090FF',
    'amber_bg': '#FFF0D1', 'amber_fg': '#8A5300', 'green_bg': '#DDF5E8', 'green_fg': '#0B6B3A',
    'red_bg': '#FDE2E1', 'red_fg': '#A1251B', 'grey_bg': '#E6EBF5', 'grey_fg': '#34476B',
    'blue_bg': '#DCEEFF', 'blue_fg': '#0B4F8A',
}
STAGE = {  # pipeline stage -> (label, colour, order)
    'Final': ('Final', 'green', 0), 'Accepted': ('Accepted', 'green', 1), 'Last Call': ('Last Call', 'blue', 2),
    'Draft': ('Draft', 'amber', 3), 'PR': ('Draft PR, no number', 'amber', 4), 'Discussion': ('Discussion only', 'red', 5),
}


# ---------------------------------------------------------------------------
# HTML helpers (inline styles: email clients ignore <style> unevenly)
# ---------------------------------------------------------------------------

def pill(text, kind='grey'):
    return (f'<span style="display:inline-block;font-size:11px;font-weight:700;padding:2px 7px;border-radius:5px;'
            f'background:{C[kind + "_bg"]};color:{C[kind + "_fg"]};white-space:nowrap">{esc(text)}</span>')


def a(url, text, bold=True):
    w = '600' if bold else '400'
    return f'<a href="{esc(url)}" style="color:{C["blue"]};text-decoration:none;font-weight:{w}">{esc(text)}</a>'


def fip_a(num):
    return a(u.fip_url(num), f'FIP-{num}')


def muted(text):
    return f'<span style="color:{C["muted"]}">{esc(text)}</span>'


def day(d):
    return f'{d:%b} {d.day}'


def section(title, inner, hint=''):
    h = f'<p style="margin:0 0 6px;font-size:12px;color:{C["muted"]}">{hint}</p>' if hint else ''
    return (f'<tr><td style="padding:20px 24px 4px"><h2 style="margin:0 0 4px;font-size:16px;color:{C["ink"]}">{esc(title)}</h2>'
            f'{h}{inner}</td></tr>')


def rows(items, empty):
    if not items:
        return f'<p style="margin:6px 0 0;color:{C["muted"]};font-size:14px">{esc(empty)}</p>'
    return ('<table role="presentation" width="100%" cellspacing="0" cellpadding="0">' + ''.join(
        f'<tr><td style="padding:9px 0;border-top:1px solid {C["line"]};font-size:14px;line-height:1.45">{i}</td></tr>'
        for i in items) + '</table>')


def snippet(text, n=170):
    t = re.sub(r'\s+', ' ', text or '').strip()
    return t if len(t) <= n else t[:n].rsplit(' ', 1)[0] + '…'


# ---------------------------------------------------------------------------
# GitHub data
# ---------------------------------------------------------------------------

def _dt(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00')) if s else None


def _who(node):
    return ((node or {}).get('author') or {}).get('login') or 'ghost'


def _comments(node):
    out = []
    for c in (node.get('comments') or {}).get('nodes') or []:
        out.append({'who': _who(c), 'at': _dt(c['createdAt']), 'url': c['url'], 'text': c['bodyText']})
        for r in (c.get('replies') or {}).get('nodes') or []:
            out.append({'who': _who(r), 'at': _dt(r['createdAt']), 'url': r['url'], 'text': r['bodyText']})
    for r in (node.get('reviews') or {}).get('nodes') or []:
        if r.get('submittedAt'):
            label = {'APPROVED': 'approved', 'CHANGES_REQUESTED': 'requested changes'}.get(r['state'], 'reviewed')
            out.append({'who': _who(r), 'at': _dt(r['submittedAt']), 'url': r['url'], 'text': r['bodyText'] or f'({label})'})
    return out


COMMENT = 'author { login } createdAt url bodyText'

RECENT_DISCUSSIONS = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    discussions(first: 25, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes { number title url createdAt updatedAt author { login }
        comments(last: 40) { totalCount nodes { %s replies(last: 20) { nodes { %s } } } } }
    }
  }
}""" % (COMMENT, COMMENT)


def recent_discussions(owner, name):
    """Recently updated discussions with their comments and replies, or None."""
    data = u.github_graphql(RECENT_DISCUSSIONS, {'owner': owner, 'name': name})
    try:
        nodes = data['repository']['discussions']['nodes']
    except (TypeError, KeyError):
        return None
    return [{'kind': 'discussion', 'repo': name, 'number': n['number'], 'title': n['title'], 'url': n['url'],
             'created': _dt(n['createdAt']), 'updated': _dt(n['updatedAt']), 'author': _who(n), 'state': None,
             'comments': _comments(n)} for n in nodes]


def scoped_threads(prs, discussions):
    """PRs and discussions on filecoin-project/FIPs by number, with comments and reviews."""
    parts = []
    for n in prs:
        parts.append(f'pr{n}: pullRequest(number: {n}) {{ number title url state isDraft merged createdAt updatedAt author {{ login }} '
                     f'comments(last: 40) {{ nodes {{ {COMMENT} }} }} '
                     f'reviews(last: 30) {{ nodes {{ author {{ login }} state submittedAt url bodyText }} }} }}')
    for n in discussions:
        parts.append(f'd{n}: discussion(number: {n}) {{ number title url createdAt updatedAt author {{ login }} '
                     f'comments(last: 40) {{ nodes {{ {COMMENT} replies(last: 20) {{ nodes {{ {COMMENT} }} }} }} }} }}')
    if not parts:
        return {}
    data = u.github_graphql('query { repository(owner: "filecoin-project", name: "FIPs") { %s } }' % ' '.join(parts))
    out = {}
    for key, node in ((data or {}).get('repository') or {}).items():
        if not node:
            continue
        kind = 'pr' if key.startswith('pr') else 'discussion'
        out[(kind, node['number'])] = {
            'kind': kind, 'repo': 'FIPs', 'number': node['number'], 'title': node['title'], 'url': node['url'],
            'created': _dt(node['createdAt']), 'updated': _dt(node['updatedAt']), 'author': _who(node),
            'state': ('merged' if node.get('merged') else (node.get('state') or '').lower()) if kind == 'pr' else None,
            'comments': _comments(node),
        }
    return out


def _disc_number(url):
    m = re.search(r'filecoin-project/FIPs/discussions/(\d+)', url or '', re.I)
    return int(m.group(1)) if m else None


def _key(name):
    name = re.sub(r'^(FIP|FRC)-?(\d+|X+)\s*:\s*', '', name or '', flags=re.I)
    return re.sub(r'[^a-z0-9]+', ' ', name.lower()).strip()


STOP = {'the', 'a', 'an', 'of', 'to', 'in', 'and', 'or', 'by', 'for', 'fip', 'frc', 'xxxx', 'remove', 'entirely', 'variant'}


def _same(row, item):
    """Is this planning-thread row the same proposal as a scope item?"""
    if row.get('fip') and row['fip'] == item.get('fip'):
        return True
    links = {re.sub(r'[#?].*$', '', x).rstrip('/').lower() for x in row.get('links') or []}
    mine = {x.rstrip('/').lower() for x in item.get('discussions', [])} | {
        f'https://github.com/filecoin-project/fips/pull/{n}' for n in item.get('prs', [])}
    if links & mine:
        return True
    a = set(_key(row['name']).split()) - STOP
    b = set(_key(item['name']).split()) - STOP
    return bool(a) and len(a & b) / len(a) >= 0.6


# ---------------------------------------------------------------------------
# Collect
# ---------------------------------------------------------------------------

def load_scope():
    try:
        with open(SCOPE_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        print(f'Warning: could not read {SCOPE_FILE}: {e}')
        return {}


def collect(hours):
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    d = {'now': now, 'since': since, 'hours': hours}

    repo = u.get_fips_repo()
    fips = {f['number']: f for f in u.parse_fip_table(u.read_readme(repo))}
    history, events = u.build_status_history(repo)
    files = u.load_fip_files(repo)
    open_lc, _ = u.last_call_windows(history, files, fips)
    d.update(fips=fips, files=files, last_call=open_lc,
             status_changes=sorted((e for e in events if e['date'] >= since and e['from'] != e['to']),
                                   key=lambda e: e['date'], reverse=True))

    raw = u.fetch_open_prs()
    prs = u.process_prs(raw, with_reviews=False) if raw is not None else []
    for p in prs:
        p['created'], p['updated'] = _dt(p['created_at']), _dt(p['updated_at'])
    d['new_prs'] = sorted((p for p in prs if p['created'] >= since), key=lambda p: p['created'], reverse=True)

    # Planning, meetings, calls
    d.update(plan=None, meetings=[], calls=[], agenda=[])
    try:
        import core_devs as cd
        cd_repo = cd.get_core_devs_repo()
        upgrades = cd.load_upgrades(cd_repo)
        d['meetings'] = [m for m in cd.load_meetings(cd_repo) if m.get('date') and m['date'] >= since - timedelta(days=1)]
        d['agenda'] = cd.fetch_open_agenda() or []
        import scope_planning as sp
        plans = sp.active(sp.fetch_planning(), upgrades)
        d['plan'] = plans[0] if plans else None
    except Exception as e:
        print(f'Warning: core-devs / planning data unavailable: {e}')
    try:
        import implementers as impl
        calls, _ = impl.load_calls()
        d['calls'] = [c for c in calls if c.get('date') and c['date'] >= since - timedelta(days=1)]
    except Exception as e:
        print(f'Warning: implementers calls unavailable: {e}')

    # Scope: the file if it matches the active upgrade, else the planning thread's green rows.
    cfg = load_scope()
    nv = d['plan']['nv'] if d['plan'] else cfg.get('upgrade')
    if cfg.get('upgrade') == nv and cfg.get('items'):
        d['scope_source'] = 'file'
        items = [dict(x) for x in cfg['items']]
    else:
        d['scope_source'] = 'planning'
        items = [{'name': re.sub(r'^(FIP|FRC)-?(\d+|X+)\s*:\s*', '', r['name']), 'fip': r['fip'],
                  'prs': [int(m) for m in re.findall(r'/FIPs/pull/(\d+)', ' '.join(r.get('links') or []))],
                  'discussions': [x for x in r.get('links') or [] if '/discussions/' in x]}
                 for r in (d['plan'] or {}).get('scope', []) if r['readiness'] == 'ready']
    d['nv'] = nv
    d['target'] = cfg.get('target') if cfg.get('upgrade') == nv else None
    for it in items:
        it.setdefault('prs', [])
        it.setdefault('discussions', [])
        if it.get('fip') and it['fip'] in files:
            it['discussions'] = list(dict.fromkeys(it['discussions'] + files[it['fip']].get('_discussions', [])))
        it['disc_numbers'] = [n for n in (_disc_number(x) for x in it['discussions']) if n]

    # Comment activity: recent discussions in both repos, every scoped thread, and PRs opened this week.
    threads = {}
    d['discussions_loaded'] = False
    for owner, name in (('filecoin-project', 'FIPs'), ('filecoin-project', 'core-devs')):
        got = recent_discussions(owner, name)
        if got is not None:
            d['discussions_loaded'] = True
            for t in got:
                threads[(name, 'discussion', t['number'])] = t
    want_prs = sorted({n for it in items for n in it['prs']} | {p['number'] for p in d['new_prs']})
    want_disc = sorted({n for it in items for n in it['disc_numbers']} - {k[2] for k in threads if k[0] == 'FIPs'})
    for (kind, n), t in scoped_threads(want_prs, want_disc).items():
        threads[('FIPs', kind, n)] = t
    for t in threads.values():
        t['recent'] = sorted((c for c in t['comments'] if c['at'] and c['at'] >= since), key=lambda c: c['at'])
    d['threads'] = threads
    d['active_threads'] = sorted(
        (t for t in threads.values() if t['recent'] or (t['created'] and t['created'] >= since)),
        key=lambda t: max([c['at'] for c in t['recent']] + [t['created']]), reverse=True)

    # Per-item stage, activity and next step.
    lc_by = {w['number']: w for w in open_lc}
    for it in items:
        its = ([threads.get(('FIPs', 'pr', n)) for n in it['prs']]
               + [threads.get(('FIPs', 'discussion', n)) for n in it['disc_numbers']])
        its = [t for t in its if t]
        it['threads'] = its
        it['recent'] = sorted((c for t in its for c in t['recent']), key=lambda c: c['at'])
        stamps = [t['updated'] for t in its if t['updated']] + [c['at'] for t in its for c in t['comments'] if c['at']]
        it['last_activity'] = max(stamps) if stamps else None
        fip = it.get('fip')
        status = fips[fip]['status'] if fip in fips else (files.get(fip, {}).get('_status') if fip else None)
        open_prs = [t for t in its if t['kind'] == 'pr' and t['state'] == 'open']
        it['stage'] = status if status in STAGE else ('Draft' if fip else 'PR' if open_prs or it['prs'] else 'Discussion')
        it['readme'] = fip in fips
        it['lc'] = lc_by.get(fip)
        if it['stage'] == 'Last Call' and it['lc']:
            w = it['lc']
            it['next'] = f'Last Call review ends {day(w["end"])}{" (est.)" if w["estimated_end"] else ""}; then Accepted or back to Draft'
        elif it['stage'] in ('Accepted', 'Final'):
            it['next'] = 'Implementation in builtin-actors and clients'
        elif it['stage'] == 'Draft':
            it['next'] = 'Finish review, then Last Call' + ('' if it['readme'] else ' (draft not in the README yet)')
        elif it['stage'] == 'PR':
            it['next'] = 'Needs a FIP number and the draft merged'
        else:
            it['next'] = 'Needs an author and a draft FIP'
        it['stale'] = bool(it['last_activity'] and (now - it['last_activity']).days >= STALE_DAYS)
    d['items'] = sorted(items, key=lambda x: STAGE[x['stage']][2])

    d['also'] = [r for r in (d['plan'] or {}).get('scope', []) if not any(_same(r, it) for it in items)]
    return d


# ---------------------------------------------------------------------------
# Summary (rule-based: predictable, never invents anything)
# ---------------------------------------------------------------------------

def summarize(d):
    items, now = d['items'], d['now']
    counts = {}
    for it in items:
        counts[it['stage']] = counts.get(it['stage'], 0) + 1
    phr = {'Final': 'Final', 'Accepted': 'Accepted', 'Last Call': 'in Last Call', 'Draft': 'Draft',
           'PR': 'draft PR without a FIP number', 'Discussion': 'discussion only'}
    pipeline = ', '.join(f'{counts[s]} {phr[s]}' for s in sorted(counts, key=lambda s: STAGE[s][2]))
    accepted = counts.get('Accepted', 0) + counts.get('Final', 0)
    nv = f'NV{d["nv"]}' if d['nv'] else 'Next upgrade'
    target = f' (target {d["target"]})' if d['target'] else ''

    bullets = []
    if items:
        bullets.append(f'<strong>{nv}{esc(target)}:</strong> {len(items)} items in realistic scope: {esc(pipeline)}. '
                       + ('None accepted yet.' if not accepted else f'{accepted} accepted.'))
    else:
        bullets.append(f'<strong>{nv}{esc(target)}:</strong> no realistic scope set yet.')

    ch = d['status_changes']
    n_comments = sum(len(t['recent']) for t in d['active_threads'])
    n_threads = sum(1 for t in d['active_threads'] if t['recent'])
    week = [f'{len(ch)} FIP status change{"s" if len(ch) != 1 else ""} ('
            + ', '.join(f'FIP-{e["number"]} → {e["to"] or "removed"}' for e in ch[:3]) + (', …' if len(ch) > 3 else '') + ')'
            if ch else 'no FIP status changes',
            f'{n_comments} new comment{"s" if n_comments != 1 else ""} across {n_threads} thread{"s" if n_threads != 1 else ""}']
    if d['new_prs']:
        week.append(f'{len(d["new_prs"])} new FIP PR{"s" if len(d["new_prs"]) != 1 else ""}')
    bullets.append('<strong>This week:</strong> ' + esc('; '.join(week)) + '.')

    attn = []
    for w in sorted(d['last_call'], key=lambda w: w['end']):
        left = (w['end'] - now).days
        if left <= 7:
            attn.append(f'FIP-{w["number"]} Last Call closes {day(w["end"])} ({max(left, 0)} days)')
    undrafted = [it['name'] for it in items if it['stage'] == 'Discussion']
    if undrafted:
        attn.append(f'{len(undrafted)} scoped item{"s have" if len(undrafted) != 1 else " has"} no draft FIP yet: '
                    + '; '.join(undrafted))
    stale = [it['name'] for it in items if it['stale']]
    if stale:
        quiet = [n for n in stale if n not in undrafted]
        if quiet:
            attn.append(f'Quiet for {STALE_DAYS}+ days: ' + '; '.join(quiet))
        if len(quiet) < len(stale):
            attn[-1 if not quiet else -2] += f' (no activity in {STALE_DAYS}+ days)'
    if attn:
        bullets.append('<strong>Needs attention:</strong> ' + esc('. '.join(attn)) + '.')

    nxt = []
    ms = (d['plan'] or {}).get('milestones') or []
    dated = [m for m in ms if m['date'] and m['date'].upper() != 'TBD']
    if dated:
        nxt.append(f'next dated milestone: {dated[0]["name"]}, {dated[0]["date"]}')
    elif d['plan']:
        nxt.append('milestone dates not set yet')
    if d['agenda']:
        nxt.append(d['agenda'][0]['title'])
    if nxt:
        bullets.append('<strong>Coming up:</strong> ' + esc('; '.join(nxt)) + '.')
    return bullets, n_comments


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render(d):
    now, hours = d['now'], d['hours']
    window = ('the last 7 days' if hours == 168 else
              f'the last {hours // 24} days' if hours % 24 == 0 else f'the last {hours} hours')
    bullets, n_comments = summarize(d)
    nv = f'NV{d["nv"]}' if d['nv'] else 'Next upgrade'

    summary = (f'<tr><td style="padding:20px 24px 4px"><div style="background:{C["bg"]};border-radius:10px;padding:16px 18px">'
               f'<div style="font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:{C["muted"]};margin-bottom:8px">Summary</div>'
               f'<ul style="margin:0;padding-left:18px;font-size:14px;line-height:1.5;color:{C["ink"]}">'
               + ''.join(f'<li style="margin:0 0 8px">{b}</li>' for b in bullets) + '</ul></div></td></tr>')

    # Scope tracker
    cards = []
    for it in d['items']:
        label, colour, _ = STAGE[it['stage']]
        if it['stage'] == 'Last Call' and it['lc']:
            label = f'Last Call · ends {day(it["lc"]["end"])}'
        title = (fip_a(it['fip']) + ' ' if it.get('fip') else '') + esc(it['name'])
        links = [a(t['url'], ('PR #' if t['kind'] == 'pr' else 'Discussion #') + str(t['number']), bold=False)
                 for t in it['threads']]
        last = it['last_activity']
        if it['recent']:
            who = ', '.join(sorted({'@' + c['who'] for c in it['recent']}))
            activity = f'{len(it["recent"])} comment{"s" if len(it["recent"]) != 1 else ""} this week from {who}'
        else:
            activity = f'No comments this week · last activity {day(last)}' if last else 'No activity found'
        quote = ''
        if it['recent']:
            c = it['recent'][-1]
            quote = (f'<div style="margin-top:6px;padding:6px 10px;border-left:3px solid {C["line"]};color:{C["muted"]};font-size:13px">'
                     f'@{esc(c["who"])}: {esc(snippet(c["text"]))} {a(c["url"], "→", bold=False)}</div>')
        stale = ' ' + pill(f'quiet {STALE_DAYS}+ days', 'red') if it['stale'] else ''
        cards.append(f'{pill(label, colour)}{stale}<div style="margin-top:4px;font-weight:600">{title}</div>'
                     f'<div style="font-size:13px;margin-top:2px">{muted(activity)}</div>'
                     f'<div style="font-size:13px;margin-top:2px"><strong>Next:</strong> {esc(it["next"])}'
                     + (f' · {" · ".join(links)}' if links else '') + f'</div>{quote}')
    if d['scope_source'] == 'file':
        src = 'Realistic scope as set in data/digest-scope.json'
    elif d['plan']:
        src = f'Scope file is for another upgrade; showing green rows from {a(d["plan"]["url"], "the planning thread", bold=False)}'
    else:
        src = 'No scope set'
    scope_html = section(f'{nv} scope: where each item stands', rows(cards, 'No items in scope yet.'),
                         f'{src}. Furthest along first.')

    # Timeline
    tl = []
    if d['target']:
        tl.append(f'<strong>Target mainnet:</strong> {esc(d["target"])}')
    ms = (d['plan'] or {}).get('milestones') or []
    for m in ms:
        tl.append(f'{esc(m["name"])}: <strong>{esc(m["date"])}</strong>')
    if not ms:
        tl.append(muted('Milestone dates (scope lock, actor code freeze, Calibnet, mainnet) are not set in the planning thread yet.'))
    if d['items']:
        accepted = sum(1 for it in d['items'] if it['stage'] in ('Accepted', 'Final'))
        tl.append(muted(f'{accepted} of {len(d["items"])} scoped items are Accepted. '
                        'Items generally need to be Accepted before the actor code freeze to ship in the upgrade.'))
    timeline_html = section('Timeline', rows(tl, ''), a(d['plan']['url'], 'Planning discussion', bold=False) if d['plan'] else '')

    # Status changes
    changes = [f'{fip_a(e["number"])} {esc(e["title"])}<br>{muted((e["from"] or "new") + " → ")}'
               f'<strong>{esc(e["to"] or "removed")}</strong> {muted("· " + day(e["date"]))}'
               for e in d['status_changes']]
    changes_html = section('FIP status changes', rows(changes, f'No FIP changed status in {window}.'))

    # Comment activity
    convo = []
    for t in d['active_threads'][:12]:
        kind = 'PR' if t['kind'] == 'pr' else 'Discussion'
        new = pill('New', 'green') + ' ' if t['created'] and t['created'] >= d['since'] else ''
        who = sorted({'@' + c['who'] for c in t['recent']})
        meta = (f'{t["repo"]} {kind} #{t["number"]} · {len(t["recent"])} new comment{"s" if len(t["recent"]) != 1 else ""}'
                + (f' from {", ".join(who)}' if who else ''))
        last = ''
        if t['recent']:
            c = t['recent'][-1]
            last = (f'<div style="margin-top:4px;color:{C["muted"]};font-size:13px">Latest, @{esc(c["who"])} ({day(c["at"])}): '
                    f'{esc(snippet(c["text"]))}</div>')
        convo.append(f'{new}{a(t["url"], t["title"])}<br>{muted(meta)}{last}')
    if len(d['active_threads']) > 12:
        convo.append(muted(f'…and {len(d["active_threads"]) - 12} more threads.'))
    convo_empty = f'No comments in {window}.' if d['discussions_loaded'] else 'Comment activity could not be loaded on this run.'
    convo_html = section('Comments on discussions and PRs', rows(convo, convo_empty),
                         f'{n_comments} comments in {window}, most recent first.')

    # Last Call
    lc = []
    for w in sorted(d['last_call'], key=lambda w: w['end']):
        left = (w['end'] - now).days
        when = f'{left} days left' if left > 1 else ('1 day left' if left == 1 else 'ends today' if left == 0 else 'overdue')
        disc = f' · {a(w["discussions"][0], "comment", bold=False)}' if w['discussions'] else ''
        lc.append(f'{fip_a(w["number"])} {esc(w["title"])} {pill(when, "red" if left <= 3 else "amber")}<br>'
                  f'{muted("Review ends " + day(w["end"]) + (" (est.)" if w["estimated_end"] else ""))}{disc}')
    lc_html = section('Last Call', rows(lc, 'No FIPs are in Last Call.'))

    # Also in planning thread
    also = []
    for r in d['also']:
        name = esc(r['name'])
        if r['fip']:
            name = re.sub(r'FIP-?\d+', fip_a(r['fip']), name, count=1)
        also.append(name + (' ' + muted('· ' + r['status'][:100]) if r['status'] else ''))
    also_html = section(f'Also in the {nv} planning thread, not in realistic scope', rows(also, 'Nothing else listed.')) if d['plan'] else ''

    # Calls
    calls = []
    for m in d['meetings']:
        link = m.get('notes_url') or m.get('recording_url') or m.get('agenda_url')
        title = f'Core Devs #{m["number"]}'
        calls.append(f'{pill("Core Devs")} {a(link, title) if link else esc(title)} {muted("· " + day(m["date"]))}'
                     + (f'<br>{muted("FIPs: " + ", ".join("FIP-" + f for f in m["fips"][:8]))}' if m.get('fips') else ''))
    for c in d['calls']:
        link = c.get('notes_url') or c.get('page_url')
        calls.append(f'{pill("Implementers")} {a(link, c["title"]) if link else esc(c["title"])} {muted("· " + day(c["date"]))}'
                     + (f'<br>{muted(snippet(c["summary"], 200))}' if c.get('summary') else ''))
    for g in d['agenda'][:2]:
        calls.append(f'{pill("Upcoming", "amber")} {a(g["url"], g["title"])}')
    calls_html = section('Calls', rows(calls, f'No Core Devs or Implementers calls in {window}.'))

    date_label = f'{now:%A}, {now:%B} {now.day}, {now:%Y}'
    html = f'''<!doctype html><html><body style="margin:0;padding:0;background:{C["bg"]};font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:{C["ink"]}">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:{C["bg"]}"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="640" cellspacing="0" cellpadding="0" style="max-width:640px;width:100%;background:#fff;border:1px solid {C["line"]};border-radius:12px;overflow:hidden">
<tr><td style="background:{C["ink"]};padding:20px 24px">
<div style="font-size:11px;font-weight:700;letter-spacing:.12em;color:#7FC4FF;text-transform:uppercase">Filecoin governance · twice-weekly digest</div>
<div style="font-size:22px;font-weight:800;color:#fff;margin-top:4px">FIPs and {esc(nv)}: {esc(date_label)}</div>
<div style="font-size:13px;color:#B9C6D6;margin-top:4px">Activity in {esc(window)}, from the FIPs and core-devs repos.</div>
</td></tr>
{summary}
<tr><td style="padding:14px 24px 0"><div style="font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:{C["muted"]};border-bottom:2px solid {C["ink"]};padding-bottom:4px">Details</div></td></tr>
{scope_html}{timeline_html}{changes_html}{convo_html}{lc_html}{also_html}{calls_html}
<tr><td style="padding:20px 24px 22px;border-top:1px solid {C["line"]};font-size:12px;color:{C["muted"]};line-height:1.5">
{a(SITE, "Dashboard")} · {a(SITE + "network-upgrades.html", "Upgrades")} · {a(SITE + "fips-dashboard-static.html", "All FIPs")}<br>
Community digest generated from public GitHub data; it doesn't change FIP status.
You're receiving this because you were added to the digest list; reply to the sender to be removed.
</td></tr></table></td></tr></table></body></html>'''

    def strip(s):
        s = re.sub(r'<br\s*/?>|</div>', ' — ', s)
        return htmllib.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', s))).strip(' —')
    text = [f'FIPs and {nv}: {date_label}', f'Activity in {window}.', '', 'SUMMARY']
    text += [f'- {strip(b)}' for b in bullets] + ['', 'DETAILS', '']
    for title, items in ((f'{nv} SCOPE', cards), ('TIMELINE', tl), ('FIP STATUS CHANGES', changes),
                         ('COMMENTS', convo), ('LAST CALL', lc), ('ALSO IN PLANNING THREAD', also), ('CALLS', calls)):
        text.append(title)
        text += [f'- {strip(i)}' for i in items] or ['- none']
        text.append('')
    text.append(f'Dashboard: {SITE}')

    parts = [f'{nv} {len(d["items"])} items in scope']
    if d['status_changes']:
        parts.append(f'{len(d["status_changes"])} status change{"s" if len(d["status_changes"]) != 1 else ""}')
    parts.append(f'{n_comments} comments')
    soon = sorted((w for w in d['last_call'] if (w['end'] - now).days <= 7), key=lambda w: w['end'])
    if soon:
        parts.append(f'FIP-{soon[0]["number"]} Last Call closes {day(soon[0]["end"])}')
    subject = f'FIP digest {day(now)}: ' + ' · '.join(parts)
    return subject, html, '\n'.join(text)


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------

def recipients():
    raw = os.environ.get('DIGEST_RECIPIENTS', '')
    return [r.strip() for r in re.split(r'[,\n;]', raw) if '@' in r]


def send(subject, html, text):
    host, user, pw = os.environ.get('SMTP_HOST'), os.environ.get('SMTP_USERNAME'), os.environ.get('SMTP_PASSWORD')
    port = int(os.environ.get('SMTP_PORT') or 465)
    sender = os.environ.get('DIGEST_FROM') or user
    to = recipients()
    if not (host and user and pw and to):
        missing = [k for k, v in (('SMTP_HOST', host), ('SMTP_USERNAME', user), ('SMTP_PASSWORD', pw),
                                  ('DIGEST_RECIPIENTS', to)) if not v]
        print(f'Not sending: missing {", ".join(missing)}. Wrote digest-preview.html instead.')
        return False
    ctx = ssl.create_default_context()
    server = smtplib.SMTP_SSL(host, port, context=ctx) if port == 465 else smtplib.SMTP(host, port)
    with server:
        if port != 465:
            server.starttls(context=ctx)
        server.login(user, pw)
        for i in range(0, len(to), BATCH):
            msg = EmailMessage()
            msg['Subject'], msg['From'], msg['To'] = subject, sender, sender
            msg['Date'], msg['Message-ID'] = formatdate(localtime=False), make_msgid()
            msg.set_content(text)
            msg.add_alternative(html, subtype='html')
            # Bcc only: addresses go in the SMTP envelope, never in headers.
            server.send_message(msg, from_addr=sender, to_addrs=to[i:i + BATCH])
    print(f'Sent digest to {len(to)} recipient(s) in {(len(to) + BATCH - 1) // BATCH} message(s).')
    return True


def main():
    hours = int(os.environ.get('DIGEST_HOURS') or 168)
    d = collect(hours)
    subject, html, text = render(d)
    print(f'Subject: {subject}')
    with open('digest-preview.html', 'w', encoding='utf-8') as f:
        f.write(html)
    send(subject, html, text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
