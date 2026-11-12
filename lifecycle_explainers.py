#!/usr/bin/env python3
"""Explainers for the FIP Lifecycle page, based on the FIPs repo.

The wording paraphrases FIP-0001 ("FIP Types", "FIP Work Flow", "What belongs
in a successful FIP?", "FIP Editors") and proposing.md, and links back to them;
FIP-0001 stays the authority. Counts and the editors list are read from the
repo on every build, so they follow changes there.
"""

import os
import re

from fip_utils import html_escape as esc

REPO = 'https://github.com/filecoin-project/FIPs'
FIP1 = f'{REPO}/blob/master/FIPS/fip-0001.md'


def _a(url, label):
    return f'<a href="{esc(url)}" target="_blank" rel="noopener">{label}</a>'


# ---------------------------------------------------------------------------
# Data from the repo
# ---------------------------------------------------------------------------

def editors(repo):
    """[(name, handle)] from FIP-0001's "FIP Editors" section."""
    path = os.path.join(repo, 'FIPS', 'fip-0001.md')
    try:
        text = open(path, encoding='utf-8', errors='replace').read()
    except OSError:
        return []
    m = re.search(r'^##\s+FIP Editors\s*$(.*?)^##\s', text, re.M | re.S)
    out = []
    for line in (m.group(1) if m else '').split('\n'):
        mm = re.match(r'\s*[*-]\s+(.+?)\s*\(@([A-Za-z0-9-]+)\)', line)
        if mm:
            out.append((mm.group(1).strip(), mm.group(2)))
    return out


def fip_kind(f):
    both = f'{f.get("type") or ""} {f.get("category") or ""}'.lower()
    for key, name in (('organi', 'Organizational'), ('recover', 'Recovery'), ('interface', 'Interface'),
                      ('network', 'Networking'), ('informational', 'Informational'), ('core', 'Core')):
        if key in both:
            return name
    return 'Technical'


def frc_count(repo):
    d = os.path.join(repo, 'FRCs')
    return len([x for x in os.listdir(d) if x.lower().endswith('.md')]) if os.path.isdir(d) else None


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def intro(repo, fips):
    eds = editors(repo)
    ed_html = ', '.join(_a(f'https://github.com/{h}', esc(n)) for n, h in eds) if eds else 'listed in FIP-0001'
    return f'''<section class="card explainer" id="what-is-a-fip"><div class="card-head"><h2>What is a FIP?</h2>
<span class="hint">From {_a(FIP1, "FIP-0001")} and the {_a(REPO, "FIPs repo")}.</span></div>
<div class="card-body">
<p class="lead">A Filecoin Improvement Proposal is a design document for changing Filecoin: the protocol, the standards clients share, or the governance process itself. It sets out the change precisely and argues for it, and its git history becomes the permanent record of how the decision was made. A change to a single client doesn't need a FIP; anything that affects several implementations, or that they all need to agree on, does.</p>
<div class="roles">
<div class="role"><strong>Author (champion)</strong><span>Writes the FIP, leads the discussion, builds consensus and records objections. Requests each status change with a pull request.</span></div>
<div class="role"><strong>FIP editors</strong><span>Check a FIP is complete and sound, assign its number, merge it and process status changes. They handle the editorial side and don't judge proposals. Currently: {ed_html}.</span></div>
<div class="role"><strong>Core Devs</strong><span>Discuss core FIPs in {_a("core-devs.html", "Core Devs meetings")} and decide which ones go into a network upgrade.</span></div>
<div class="role"><strong>Implementers</strong><span>Build accepted FIPs into the clients and agree upgrade scope and timing on the {_a("implementers.html", "implementers' calls")}.</span></div>
</div>
<p class="note">{len(fips)} FIPs are in the repo today. The rest of this page follows them through the process.</p>
</div></section>'''


TYPES = [
    ('Core', 'Technical', 'Changes that need a consensus upgrade (a network upgrade), or that will matter for one. These are the FIPs that go through Accepted and ship in an upgrade.'),
    ('Networking', 'Technical', 'Changes to how data propagates or to Filecoin\'s network protocols.'),
    ('Interface', 'Technical', 'Client API and RPC standards, and conventions such as method names.'),
    ('Informational', 'Technical (FRC)', 'Design notes, guidelines or conventions that don\'t propose a protocol change. Following them is optional. Kept as FRCs (Filecoin Request for Comments) in their own folder.'),
    ('Organizational', 'FOP', 'Changes to processes around Filecoin, including governance and the FIP process itself. Usually need community consensus.'),
    ('Recovery', 'FRP', 'A one-off state change to fix something the normal protocol can\'t, such as a bug that destroyed value. Only allowed under tightly defined criteria.'),
]


def types_card(repo, files):
    counts = {}
    for f in files.values():
        k = fip_kind(f)
        counts[k] = counts.get(k, 0) + 1
    frcs = frc_count(repo)
    cards = []
    for name, family, what in TYPES:
        n = frcs if name == 'Informational' else counts.get(name, 0)
        cards.append(f'<div class="type-card"><div class="type-head"><strong>{name}</strong><span class="muted small">{family}</span>'
                     f'<span class="type-n">{"—" if n is None else n}</span></div><p>{esc(what)}</p></div>')
    other = counts.get('Technical', 0)
    other_note = f' {other} technical FIPs don\'t name a subcategory in their header.' if other else ''
    return f'''<section class="card explainer" id="types"><div class="card-head"><h2>Types of FIP</h2>
<span class="hint">Set in each FIP's <code>type</code> and <code>category</code> headers.</span></div>
<div class="card-body"><div class="type-grid">{"".join(cards)}</div>
<p class="note">Counts come from the FIP files' headers{" and the FRCs folder" if frcs is not None else ""}.{other_note} Keeping a FIP to one focused idea makes it more likely to succeed.</p></div></section>'''


STEPS = [
    ('Test the idea', 'Ask the community first, in {disc}, whether the idea is new and has support. It saves writing a proposal that prior work already ruled out.'),
    ('Write the draft', 'Fork the FIPs repo and write the proposal from the {tmpl}. Add a <code>discussions-to</code> link so people know where to comment (it can\'t be a pull request).'),
    ('Open a pull request', 'An editor reviews the first PR, checks it\'s complete and well formed, assigns a number and merges it. The FIP is now a Draft.'),
    ('Iterate', 'Refine the Draft with follow-up PRs. Non-core FIPs need an implementation before moving on. For core FIPs, ask for a slot on a {cd} agenda and prepare the matching change to the {spec}.'),
    ('Last Call', 'When the Draft is mature, ask for Last Call. The editor sets a <code>review-period-end</code>, normally 14 days out. Material changes or unresolved objections send it back to Draft.'),
    ('Accepted or Final', 'A clean Last Call makes a core FIP Accepted and any other FIP Final. Accepted core FIPs go to the implementers and into {up}.'),
    ('Ship it', 'A core FIP becomes Final once at least two clients implement it, the spec is updated and the community adopts it, which normally means its network upgrade has activated.'),
]


def steps_card():
    links = {
        'disc': _a(f'{REPO}/discussions', 'FIP Discussions'),
        'tmpl': _a(f'{REPO}/tree/master/templates', 'template'),
        'cd': _a('https://github.com/filecoin-project/core-devs/issues', 'Core Devs'),
        'spec': _a('https://github.com/filecoin-project/specs', 'Filecoin spec'),
        'up': _a('network-upgrades.html#scope', 'upgrade scope planning'),
    }
    lis = ''.join(f'<li><strong>{t}</strong><span>{d.format(**links)}</span></li>' for t, d in STEPS)
    return f'''<section class="card explainer" id="proposing"><div class="card-head"><h2>Proposing a FIP, step by step</h2>
<span class="hint">From FIP-0001's work flow and {_a(f"{REPO}/blob/master/proposing.md", "proposing.md")}.</span></div>
<div class="card-body"><ol class="steps">{lis}</ol>
<p class="note">Each status change is a pull request from the author, reviewed by an editor. If an author steps away, they or the editors can hand the FIP to a new champion.</p></div></section>'''


SECTIONS = [
    ('Preamble', True, 'Header fields: number, short title, authors, status, type, category, <code>discussions-to</code>, and where relevant <code>requires</code>, <code>replaces</code> or <code>review-period-end</code>.'),
    ('Simple Summary', True, 'A plain-language explanation anyone can follow.'),
    ('Abstract', True, 'About 200 words on the technical issue.'),
    ('Motivation', False, 'Why the current protocol falls short. Optional in the template, but protocol changes without it may be rejected.'),
    ('Specification', True, 'Detailed enough that independent teams can build interoperable implementations.'),
    ('Rationale', True, 'Why this design: alternatives considered, related work, and how objections were handled.'),
    ('Backwards Compatibility', True, 'Required whenever something breaks: what, how badly and how it\'s handled.'),
    ('Test Cases', True, 'Required for consensus changes; linked where useful for others.'),
    ('Security Considerations', True, 'Required for every FIP. A FIP can\'t become Final until reviewers judge this section sufficient.'),
    ('Implementations', True, 'Needed before Final, not before Draft: "rough consensus and running code".'),
    ('Copyright Waiver', True, 'FIPs are public domain (CC0).'),
]


def contents_card():
    rows = ''.join(f'<li><strong>{n}</strong>{"" if req else " <span class=\"muted small\">(optional)</span>"}<span>{d}</span></li>'
                   for n, req, d in SECTIONS)
    return f'''<section class="card explainer" id="contents"><div class="card-head"><h2>What goes in a FIP</h2>
<span class="hint">FIP-0001's required sections, in order. Start from the {_a(f"{REPO}/blob/master/templates/template.md", "template")}.</span></div>
<div class="card-body"><ul class="sections-list">{rows}</ul></div></section>'''
