#!/usr/bin/env python3
"""FRCs (Filecoin Requests for Comments): a list page and one page per FRC.

  frcs.html          every FRC, newest first, with status, authors and discussion
  frc/NNNN.html      one FRC: summary, status history, calls that mentioned it,
                     open PRs (same layout as the FIP pages, via fip_page_html)
  frc/index.html     redirect to frcs.html

FRCs share the FIP numbering but are standards and conventions (token
standards, APIs, data formats) rather than protocol changes, so they never
ship in a network upgrade. Read-only like the rest of the dashboard: it
reports the records in filecoin-project/FIPs, it doesn't decide anything.
"""

import os
import re
from collections import Counter

import extras
import fip_utils as u
import og_cards
from fip_pages import badge, ext, fip_page_html
from fip_utils import html_escape as esc
from theme import page

OUT_DIR = 'frc'
STATUS_ORDER = ['Last Call', 'Draft', 'Accepted', 'Final', 'Deferred', 'Withdrawn', 'Rejected', 'Superseded']
REDIRECT = ('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>FRCs</title>'
            '<meta http-equiv="refresh" content="0; url=../frcs.html"><link rel="canonical" href="../frcs.html">'
            '</head><body><p><a href="../frcs.html">All FRCs</a></p></body></html>')


def numbers(ctx):
    return sorted(set(ctx.get('frcs') or {}) | set(ctx.get('frc_files') or {}), key=int)


def frc_view(ctx):
    """The page context with FRC records in the slots fip_page_html reads."""
    view = dict(ctx)
    view.update(kind='FRC', fips=ctx.get('frcs') or {}, files=ctx.get('frc_files') or {},
                history=ctx.get('frc_history') or {}, open_lc=ctx.get('frc_open_lc') or [],
                past_lc=ctx.get('frc_past_lc') or [])
    return view


def _lv(v):
    return ', '.join(v) if isinstance(v, list) else (v or '')


def _authors(text):
    text = re.sub(r'\s*<[^>@\s]+@[^>\s]+>', '', text or '')   # drop email addresses
    return text.strip().strip('"').strip()


def info(ctx, n):
    row, f = (ctx.get('frcs') or {}).get(n) or {}, (ctx.get('frc_files') or {}).get(n) or {}
    return {
        'number': n,
        'title': (row.get('title') or f.get('title') or '').replace('`', ''),
        'status': row.get('status') or f.get('_status') or 'Draft',
        'file_status': f.get('_status') or '',
        'listed': bool(row),
        'authors': _authors(_lv(f.get('author')) or row.get('authors', '')),
        'created': _lv(f.get('created')),
        'discussions': f.get('_discussions') or [],
    }


def list_page(ctx):
    nums = numbers(ctx)
    rows = [info(ctx, n) for n in nums]
    counts = Counter(r['status'] for r in rows)
    open_lc = ctx.get('frc_open_lc') or []

    stats = [('FRCs in the repo', len(rows), False), ('In Last Call', len(open_lc), bool(open_lc))]
    stats += [(s, counts[s], False) for s in ('Draft', 'Accepted', 'Final') if counts[s] or s != 'Accepted']
    stats_html = '<section class="stats">' + ''.join(
        f'<div class="stat{" accent" if a else ""}"><div class="label">{esc(l)}</div><div class="value">{v}</div></div>'
        for l, v, a in stats) + '</section>'

    about = (
        '<section class="card"><div class="card-head"><h2>What an FRC is</h2></div><div class="card-body">'
        '<p>An FRC (Filecoin Request for Comments) sets out a standard or convention that tools, wallets, apps and node '
        'software can follow: token standards, APIs, data formats, message envelopes. FRCs don\'t change the protocol, '
        'so they never ship in a network upgrade, and adopting one is up to each project.</p>'
        '<p>FRCs go through the same stages as other FIPs (Draft, Last Call, then Final) and share the FIP numbering, '
        'which is why FIP numbers run higher than the FIP count. They live in the '
        f'{ext(u.FIPS_BASE_URL + "FRCs", "FRCs folder ↗", "")} of the FIPs repo, and '
        f'{ext(u.FIPS_BASE_URL + "FIPS/fip-0001.md", "FIP-0001 ↗", "")} describes the process.</p>'
        '</div></section>')

    lc_html = ''
    if open_lc:
        items = ''.join(f'<li>{u.fip_anchor(w["number"])} {esc(w["title"])} · review ends {w["end"].strftime("%b %-d, %Y")}'
                        f'{" (estimated)" if w["estimated_end"] else ""}</li>' for w in open_lc)
        lc_html = (f'<div class="cta"><span><strong>In Last Call.</strong> Comments are welcome in each FRC\'s discussion thread.'
                   f'<ul class="topics" style="margin-top:6px">{items}</ul></span></div>')

    trs = []
    for r in sorted(rows, key=lambda r: int(r['number']), reverse=True):
        n = r['number']
        notes = []
        if not r['listed']:
            notes.append('in the FRCs folder, not yet in the README table')
        elif r['file_status'] and r['file_status'] != r['status']:
            notes.append(f'the FRC file itself says {esc(r["file_status"])}')
        note = f'<div class="muted small">{"; ".join(notes)}</div>' if notes else ''
        disc = (ext(r['discussions'][0], 'Discussion ↗', '') if r['discussions'] else '<span class="muted">—</span>')
        trs.append(f'<tr data-status="{esc(r["status"])}"><td>{u.fip_anchor(n)}</td>'
                   f'<td><a href="frc/{n}.html">{esc(r["title"])}</a></td>'
                   f'<td class="small">{esc(r["authors"]) or "—"}</td>'
                   f'<td>{badge(r["status"])}{note}</td><td class="small">{disc}</td></tr>')
    order = [s for s in STATUS_ORDER if counts[s]] + sorted(s for s in counts if s not in STATUS_ORDER)
    chips = ''.join(f'<button class="chip" type="button" data-filter="{esc(s)}" aria-pressed="false">{esc(s)} '
                    f'<span class="muted">{counts[s]}</span></button>' for s in order)
    table = (
        '<section class="card" id="all-frcs"><div class="card-head"><h2>All FRCs</h2>'
        '<span class="hint">Newest first. Statuses come from the FIPs README table; where an FRC\'s own file says something '
        'different, both are shown.</span></div><div class="card-body">'
        f'<div class="chips frc-filter" role="group" aria-label="Filter by status">'
        f'<button class="chip" type="button" data-filter="" aria-pressed="true">All <span class="muted">{len(rows)}</span></button>{chips}</div>'
        '<div class="table-scroll"><table class="data"><thead><tr><th>FRC</th><th>Title</th><th>Authors</th><th>Status</th>'
        f'<th>Discussion</th></tr></thead><tbody>{"".join(trs)}</tbody></table></div></div></section>'
        + FILTER_JS)

    prs = {}
    for n in nums:
        for p in (ctx.get('prs_by_fip') or {}).get(n) or []:
            prs.setdefault(p['number'], (p, set()))[1].add(n)
    pr_html = ''
    if prs:
        items = ''.join(
            f'<div class="pr-item"><a href="{esc(p["url"])}" target="_blank" rel="noopener">#{p["number"]} {esc(p["title"])}</a>'
            f'<span class="pr-meta">{", ".join(u.fip_anchor(n) for n in sorted(ns))} · @{esc(p["author"])} · '
            f'{"draft · " if p["draft"] else ""}updated {esc(p["updated_at"][:10])}</span></div>'
            for p, ns in sorted(prs.values(), key=lambda x: x[0]['updated_at'], reverse=True))
        pr_html = (f'<section class="card"><div class="card-head"><h2>Open pull requests ({len(prs)})</h2>'
                   '<span class="hint">Proposed edits to FRCs on GitHub.</span></div>'
                   f'<div class="card-body">{items}</div></section>')

    body = '\n'.join(x for x in (stats_html, lc_html, table, pr_html, about) if x)
    return page(
        title='Filecoin Requests for Comments (FRCs)',
        description='Every Filecoin FRC: the standards and conventions (token standards, APIs, data formats) that tools '
                    'and apps can follow, with status, authors and discussion threads.',
        current='frcs',
        subtitle='Standards and conventions for the Filecoin ecosystem: token standards, APIs and data formats.',
        body_html=body, path='frcs.html',
    )


# Status filter chips on frcs.html (the table works without it).
FILTER_JS = """
<script>
(function () {
  var bar = document.querySelector('.frc-filter');
  if (!bar) return;
  bar.addEventListener('click', function (e) {
    var b = e.target.closest('button'); if (!b) return;
    var want = b.getAttribute('data-filter');
    bar.querySelectorAll('button').forEach(function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
    document.querySelectorAll('#all-frcs tbody tr').forEach(function (tr) {
      tr.hidden = !!want && tr.getAttribute('data-status') !== want;
    });
  });
})();
</script>
"""


def search_entries(ctx):
    """Entries for fips-index.json; 'k' marks them as FRCs for the search box."""
    out = []
    for n in reversed(numbers(ctx)):
        r = info(ctx, n)
        out.append({'n': n, 't': r['title'], 's': r['status'], 'a': r['authors'], 'k': 'FRC'})
    return out


def data_entries(ctx):
    out = []
    for n in numbers(ctx):
        r = info(ctx, n)
        hist = (ctx.get('frc_history') or {}).get(n) or []
        out.append({
            'number': n, 'title': r['title'], 'status': r['status'], 'file_status': r['file_status'] or None,
            'authors': r['authors'], 'created': r['created'] or None, 'discussions': r['discussions'],
            'history': [{'status': h['status'], 'since': extras._iso(h['since']), 'commit': h['sha']} for h in hist],
            'file_url': u.frc_url(n), 'page_url': f'{u.SITE_URL}frc/{n}.html',
        })
    return out


def write_all(ctx):
    nums = numbers(ctx)
    if not nums:
        print('No FRCs found: skipping FRC pages')
        return
    view = frc_view(ctx)
    os.makedirs(OUT_DIR, exist_ok=True)
    keep = {f'{n}.html' for n in nums} | {'index.html'}
    for name in os.listdir(OUT_DIR):
        if name.endswith('.html') and name not in keep:
            os.remove(os.path.join(OUT_DIR, name))
    for i, n in enumerate(nums):
        prev_n = nums[i - 1] if i > 0 else None
        next_n = nums[i + 1] if i + 1 < len(nums) else None
        with open(os.path.join(OUT_DIR, f'{n}.html'), 'w', encoding='utf-8') as f:
            f.write(fip_page_html(n, view, prev_n, next_n))
    with open(os.path.join(OUT_DIR, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(REDIRECT)
    with open('frcs.html', 'w', encoding='utf-8') as f:
        f.write(list_page(ctx))
    if og_cards.available():
        os.makedirs(og_cards.OUT_DIR, exist_ok=True)
        for n in nums:
            r = info(ctx, n)
            og_cards.fip_card(os.path.join(og_cards.OUT_DIR, f'{n}.png'), n, r['title'], r['status'], kind='FRC')
    print(f'Generated frcs.html and {len(nums)} FRC pages')
