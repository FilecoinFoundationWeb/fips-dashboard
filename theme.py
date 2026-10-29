#!/usr/bin/env python3
"""Shared page shell for the FIPs dashboard pages.

Colors follow the public Filecoin palette (Filecoin Blue #0090FF on Filecoin
Dark #091B2A) and Filecoin Foundation's Archivo typeface. Swap the tokens in
:root if the official FF brand guide differs.
"""

from datetime import datetime, timezone
from fip_utils import html_escape

FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800&display=swap" rel="stylesheet">'
)

CSS = r"""
:root {
  --fil-blue: #0090FF;
  --fil-blue-strong: #0072CC;
  --fil-navy: #091B2A;
  --fil-navy-2: #0F2A42;
  --fil-sky: #7CC4FF;

  --bg: #F3F7FB;
  --surface: #FFFFFF;
  --surface-2: #EEF4FA;
  --text: #091B2A;
  --muted: #4B6178;
  --border: #D7E2EE;
  --link: #0072CC;
  --shadow: 0 1px 2px rgba(9,27,42,.06), 0 8px 24px rgba(9,27,42,.06);

  --final-bg: #DDF5E8;   --final-fg: #0B6B3A;
  --accepted-bg: #DCEEFF;--accepted-fg: #00539A;
  --lastcall-bg: #FFF0D1;--lastcall-fg: #8A5300;
  --draft-bg: #E6EBF5;   --draft-fg: #34476B;
  --active-bg: #D7F3F5;  --active-fg: #0A6670;
  --deferred-bg: #F1EBDD;--deferred-fg: #6E5A2E;
  --rejected-bg: #FDE2E2;--rejected-fg: #A11A1A;
  --muted-bg: #ECEFF3;   --muted-fg: #55606C;
  --warn-bg: #FFF6E0;    --warn-border: #F2C45A;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #06131F;
    --surface: #0C2133;
    --surface-2: #10293F;
    --text: #E6F0F9;
    --muted: #9AB0C6;
    --border: #1D3A55;
    --link: #6CBBFF;
    --shadow: 0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.25);
    --final-bg: #0E3B27;   --final-fg: #7FE0AC;
    --accepted-bg: #0D3256;--accepted-fg: #8CC8FF;
    --lastcall-bg: #44310B;--lastcall-fg: #FFCB6B;
    --draft-bg: #1E2C45;   --draft-fg: #B4C4E4;
    --active-bg: #0C3A3F;  --active-fg: #7EDDE6;
    --deferred-bg: #3A3221;--deferred-fg: #E0CB97;
    --rejected-bg: #4A1717;--rejected-fg: #FFA3A3;
    --muted-bg: #1C2733;   --muted-fg: #A8B3BF;
    --warn-bg: #3A2E10;    --warn-border: #A8812A;
  }
}

* { margin: 0; padding: 0; box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  font-family: 'Archivo', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
  min-height: 100vh;
}
a { color: var(--link); }
a:hover { color: var(--fil-blue); }
.wrap { max-width: 1240px; margin: 0 auto; padding: 0 16px; }

/* ---------- Header ---------- */
.site-header {
  position: relative;
  overflow: hidden;
  color: #fff;
  background:
    radial-gradient(900px 300px at 85% -20%, rgba(0,144,255,.45), transparent 60%),
    radial-gradient(600px 260px at 0% 120%, rgba(124,196,255,.18), transparent 60%),
    var(--fil-navy);
  padding: 28px 0 118px;
}
.site-header .wrap { position: relative; z-index: 2; }
.eyebrow {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: .78rem; font-weight: 600; letter-spacing: .12em; text-transform: uppercase;
  color: var(--fil-sky);
}
.eyebrow::before { content: ''; width: 8px; height: 8px; border-radius: 50%; background: var(--fil-blue); box-shadow: 0 0 0 4px rgba(0,144,255,.25); }
.site-header h1 { font-size: clamp(1.7rem, 4vw, 2.6rem); font-weight: 800; letter-spacing: -.02em; margin: 10px 0 6px; }
.site-header p.sub { color: #B9CDE0; max-width: 680px; }
.header-meta { display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: center; margin-top: 18px; font-size: .88rem; color: #9FB6CC; }
.nav { display: flex; gap: 6px; flex-wrap: wrap; }
.nav a {
  color: #fff; text-decoration: none; font-weight: 600; font-size: .92rem;
  padding: 8px 14px; border-radius: 999px; border: 1px solid rgba(255,255,255,.18);
  background: rgba(255,255,255,.04); transition: background .2s, border-color .2s;
}
.nav a:hover { background: rgba(0,144,255,.18); border-color: rgba(0,144,255,.6); color: #fff; }
.nav a.current { background: var(--fil-blue); border-color: var(--fil-blue); }

/* ---------- Corgi ---------- */
.ground {
  position: absolute; left: 0; right: 0; bottom: 14px; height: 2px; z-index: 1;
  background: repeating-linear-gradient(90deg, rgba(124,196,255,.35) 0 14px, transparent 14px 26px);
}
.corgi-walk {
  position: absolute; bottom: 14px; left: -140px; width: 128px; z-index: 3;
  animation: corgi-walk 26s linear infinite;
  cursor: pointer;
}
.corgi-walk svg { display: block; width: 100%; height: auto; overflow: visible; }
.corgi-flip { animation: corgi-flip 26s steps(1) infinite; transform-origin: center; }
@keyframes corgi-walk {
  0%   { left: -140px; }
  48%  { left: calc(100% + 20px); }
  50%  { left: calc(100% + 20px); }
  98%  { left: -140px; }
  100% { left: -140px; }
}
@keyframes corgi-flip { 0% { transform: scaleX(1); } 49% { transform: scaleX(-1); } 99% { transform: scaleX(1); } }
.corgi-bob { animation: corgi-bob .36s ease-in-out infinite alternate; }
@keyframes corgi-bob { from { transform: translateY(0); } to { transform: translateY(-2.5px); } }
.leg { transform-box: fill-box; transform-origin: 50% 0; animation: corgi-step .36s ease-in-out infinite alternate; }
.leg.b { animation-direction: alternate-reverse; }
@keyframes corgi-step { from { transform: rotate(-22deg); } to { transform: rotate(22deg); } }
.tail { transform-box: fill-box; transform-origin: 100% 60%; animation: corgi-wag .22s ease-in-out infinite alternate; }
@keyframes corgi-wag { from { transform: rotate(-18deg); } to { transform: rotate(14deg); } }
.ear { transform-box: fill-box; transform-origin: 50% 100%; animation: corgi-ear 3.2s ease-in-out infinite; }
.ear.r { animation-delay: .15s; }
@keyframes corgi-ear { 0%, 88%, 100% { transform: rotate(0); } 92% { transform: rotate(-12deg); } 96% { transform: rotate(6deg); } }
.tongue { transform-box: fill-box; transform-origin: 50% 0; animation: corgi-pant .36s ease-in-out infinite alternate; }
@keyframes corgi-pant { from { transform: scaleY(.85); } to { transform: scaleY(1.1); } }
.woof {
  position: absolute; bottom: 100%; left: 50%; transform: translate(-50%, 4px) scale(.6);
  background: #fff; color: var(--fil-navy); font-weight: 800; font-size: .85rem;
  padding: 4px 10px; border-radius: 12px; opacity: 0; pointer-events: none; white-space: nowrap;
  transition: opacity .15s, transform .15s;
}
.woof::after { content: ''; position: absolute; top: 100%; left: 50%; margin-left: -6px; border: 6px solid transparent; border-top-color: #fff; }
.corgi-walk.barking .woof { opacity: 1; transform: translate(-50%, -6px) scale(1); }
.corgi-walk.barking .corgi-bob { animation: corgi-hop .5s ease-out 1; }
@keyframes corgi-hop { 0%,100% { transform: translateY(0); } 40% { transform: translateY(-16px); } }
@media (prefers-reduced-motion: reduce) {
  .corgi-walk { animation: none; left: auto; right: 24px; }
  .corgi-flip { animation: none; transform: scaleX(-1); }
  .corgi-bob, .leg, .tail, .ear, .tongue { animation: none; }
}

/* ---------- Content ---------- */
main { margin-top: 22px; position: relative; z-index: 4; padding-bottom: 48px; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.stats.compact { grid-template-columns: repeat(auto-fit, minmax(118px, 1fr)); }
.stats.compact .value { font-size: 1.6rem; }
.stat {
  background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
  padding: 16px 18px; box-shadow: var(--shadow);
}
.stat .label { font-size: .76rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.stat .value { font-size: 2rem; font-weight: 800; letter-spacing: -.02em; color: var(--text); line-height: 1.2; margin-top: 4px; }
.stat.accent { background: var(--fil-blue); border-color: var(--fil-blue); }
.stat.accent .label { color: rgba(255,255,255,.85); }
.stat.accent .value { color: #fff; }

.card {
  background: var(--surface); border: 1px solid var(--border); border-radius: 16px;
  box-shadow: var(--shadow); margin-top: 20px; overflow: hidden;
}
.card-head { padding: 18px 20px 12px; display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px 16px; align-items: baseline; }
.card-head h2 { font-size: 1.2rem; font-weight: 700; letter-spacing: -.01em; }
.card-head .hint { color: var(--muted); font-size: .88rem; max-width: 640px; }
.card-body { padding: 0 20px 20px; }
.empty { color: var(--muted); font-style: italic; padding: 8px 0 4px; }
.note { font-size: .85rem; color: var(--muted); margin-top: 12px; }

.table-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
table.data { width: 100%; border-collapse: collapse; font-size: .92rem; }
table.data th {
  text-align: left; font-size: .74rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
  color: var(--muted); padding: 10px 12px; border-bottom: 1px solid var(--border); white-space: nowrap;
  background: var(--surface-2);
}
table.data td { padding: 11px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }
table.data tr:last-child td { border-bottom: 0; }
table.data tbody tr:hover td { background: var(--surface-2); }
table.data .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
td.nowrap { white-space: nowrap; }
.fip-id { font-weight: 700; text-decoration: none; white-space: nowrap; }
.title-cell { min-width: 220px; }

.status-badge {
  display: inline-block; padding: 3px 10px; border-radius: 999px;
  font-size: .74rem; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; white-space: nowrap;
}
.status-final { background: var(--final-bg); color: var(--final-fg); }
.status-accepted { background: var(--accepted-bg); color: var(--accepted-fg); }
.status-last-call { background: var(--lastcall-bg); color: var(--lastcall-fg); }
.status-draft { background: var(--draft-bg); color: var(--draft-fg); }
.status-active { background: var(--active-bg); color: var(--active-fg); }
.status-deferred { background: var(--deferred-bg); color: var(--deferred-fg); }
.status-rejected { background: var(--rejected-bg); color: var(--rejected-fg); }
.status-withdrawn, .status-superseded { background: var(--muted-bg); color: var(--muted-fg); }

.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  display: inline-flex; align-items: center; gap: 4px; text-decoration: none;
  padding: 4px 10px; border-radius: 8px; font-size: .86rem; font-weight: 600;
  background: var(--surface-2); color: var(--text); border: 1px solid var(--border);
  transition: border-color .15s, color .15s;
}
.chip:hover { border-color: var(--fil-blue); color: var(--fil-blue); }
.pr-dot { font-size: .72rem; font-weight: 700; color: #fff; background: var(--fil-blue); border-radius: 999px; padding: 0 6px; }

.age { font-weight: 600; white-space: nowrap; }
.age.old { color: var(--rejected-fg); }
.age.mid { color: var(--lastcall-fg); }
.pill {
  display: inline-block; font-size: .74rem; font-weight: 700; padding: 2px 8px; border-radius: 6px;
  background: var(--surface-2); color: var(--muted); border: 1px solid var(--border); white-space: nowrap;
}
.pill.approved { background: var(--final-bg); color: var(--final-fg); border-color: transparent; }
.pill.changes { background: var(--rejected-bg); color: var(--rejected-fg); border-color: transparent; }
.pill.waiting { background: var(--lastcall-bg); color: var(--lastcall-fg); border-color: transparent; }
.pill.est { background: transparent; }

.callout {
  background: var(--warn-bg); border: 1px solid var(--warn-border); border-radius: 12px;
  padding: 12px 14px; font-size: .9rem;
}

.pr-group { border-top: 1px solid var(--border); padding: 14px 0; }
.pr-group:first-child { border-top: 0; padding-top: 0; }
.pr-group h3 { font-size: .95rem; margin-bottom: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.pr-item { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 6px 14px; padding: 8px 12px; border-left: 3px solid var(--fil-blue); background: var(--surface-2); border-radius: 0 8px 8px 0; margin-top: 6px; }
.pr-item a { font-weight: 600; text-decoration: none; }
.pr-meta { color: var(--muted); font-size: .84rem; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }

details.more > summary { cursor: pointer; color: var(--link); font-weight: 600; margin-top: 12px; }

.timeline { position: relative; padding-left: 22px; }
.timeline::before { content: ''; position: absolute; left: 6px; top: 6px; bottom: 6px; width: 2px; background: var(--border); }
.tl-month { position: relative; margin-bottom: 22px; }
.tl-month::before { content: ''; position: absolute; left: -21px; top: 6px; width: 12px; height: 12px; border-radius: 50%; background: var(--fil-blue); box-shadow: 0 0 0 4px var(--surface); }
.tl-month h3 { font-size: 1rem; display: flex; gap: 10px; align-items: baseline; }
.tl-month h3 span { color: var(--muted); font-size: .84rem; font-weight: 500; }
.tl-events { margin-top: 8px; display: grid; gap: 6px; }
.tl-event { display: grid; grid-template-columns: 64px 1fr; gap: 10px; align-items: start; padding: 8px 12px; background: var(--surface-2); border-radius: 8px; font-size: .9rem; }
.tl-event time { color: var(--muted); font-variant-numeric: tabular-nums; font-size: .82rem; padding-top: 2px; }
.tl-event .arrow { color: var(--muted); margin: 0 4px; }

footer.site-footer { color: var(--muted); font-size: .85rem; padding: 24px 0 40px; border-top: 1px solid var(--border); }
footer.site-footer p + p { margin-top: 6px; }

@media (max-width: 640px) {
  .site-header { padding-bottom: 104px; }
  .stat .value { font-size: 1.6rem; }
  .card-head, .card-body { padding-left: 14px; padding-right: 14px; }
  .corgi-walk { width: 104px; }
}
"""

# An original, hand-drawn Pembroke corgi (facing right). Pure SVG, no assets.
CORGI_SVG = """
<svg viewBox="0 0 170 112" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="A cartoon corgi trotting">
  <ellipse cx="82" cy="106" rx="54" ry="4" fill="rgba(0,0,0,.28)"/>
  <g class="corgi-bob">
    <!-- far legs -->
    <g class="leg b"><rect x="38" y="66" width="12" height="30" rx="6" fill="#C46F22"/><ellipse cx="44" cy="96" rx="7" ry="4" fill="#E9E2D8"/></g>
    <g class="leg a"><rect x="98" y="66" width="12" height="30" rx="6" fill="#C46F22"/><ellipse cx="104" cy="96" rx="7" ry="4" fill="#E9E2D8"/></g>
    <!-- tail -->
    <g class="tail"><ellipse cx="22" cy="50" rx="13" ry="9" fill="#E58A33"/><ellipse cx="13" cy="48" rx="6" ry="5" fill="#FFF7EC"/></g>
    <!-- body -->
    <ellipse cx="74" cy="60" rx="50" ry="24" fill="#E58A33"/>
    <ellipse cx="80" cy="72" rx="36" ry="11" fill="#FFF7EC"/>
    <ellipse cx="114" cy="62" rx="16" ry="17" fill="#FFF7EC"/>
    <!-- near legs -->
    <g class="leg a"><rect x="50" y="68" width="13" height="30" rx="6.5" fill="#E58A33"/><ellipse cx="56.5" cy="98" rx="7.5" ry="4.5" fill="#FFF7EC"/></g>
    <g class="leg b"><rect x="110" y="68" width="13" height="30" rx="6.5" fill="#FFF7EC"/><ellipse cx="116.5" cy="98" rx="7.5" ry="4.5" fill="#FFFFFF"/></g>
    <!-- collar (Filecoin blue) -->
    <path d="M106 44 q12 10 26 2" stroke="#0090FF" stroke-width="6" fill="none" stroke-linecap="round"/>
    <circle cx="120" cy="53" r="4.2" fill="#7CC4FF" stroke="#0072CC" stroke-width="1.2"/>
    <!-- head -->
    <g>
      <g class="ear"><path d="M109 30 L113 2 L128 24 Z" fill="#E58A33"/><path d="M113 25 L115 10 L123 23 Z" fill="#F7B8B0"/></g>
      <g class="ear r"><path d="M124 23 L138 0 L144 27 Z" fill="#D4782A"/><path d="M129 22 L137 8 L140 24 Z" fill="#F7B8B0"/></g>
      <ellipse cx="128" cy="38" rx="23" ry="19" fill="#E58A33"/>
      <path d="M128 21 q-3 10 2 20 q8 10 22 6 l-4 -12 q-10 -4 -14 -14 z" fill="#FFF7EC"/>
      <ellipse cx="146" cy="46" rx="16" ry="10" fill="#FFF7EC"/>
      <ellipse cx="160" cy="42" rx="4.6" ry="3.6" fill="#1A1A1A"/>
      <circle cx="159" cy="40.8" r="1.1" fill="#fff"/>
      <circle cx="137" cy="33" r="3" fill="#091B2A"/>
      <circle cx="138" cy="32" r="1" fill="#fff"/>
      <ellipse cx="132" cy="44" rx="4.5" ry="2.8" fill="#F7A59B" opacity=".7"/>
      <path d="M148 51 q5 4 10 -1" stroke="#5A3A22" stroke-width="1.6" fill="none" stroke-linecap="round"/>
      <path class="tongue" d="M150 52 q3 9 7 0 z" fill="#F0727F"/>
    </g>
  </g>
</svg>
"""

# GitHub Pages serves pages with a 10-minute browser cache that can't be
# changed. On load, re-fetch this page from the network (cache: 'reload' also
# refreshes the browser's cached copy) and, if a newer build exists, reload
# once so visitors never sit on a stale version.
FRESHNESS_JS = """
<script>
(function () {
  if (!window.fetch || location.protocol === 'file:') return;
  var meta = document.querySelector('meta[name="generated-at"]');
  if (!meta) return;
  var mine = meta.getAttribute('content');
  fetch(location.pathname, { cache: 'reload' })
    .then(function (r) { return r.ok ? r.text() : ''; })
    .then(function (html) {
      var m = html.match(/<meta name="generated-at" content="([^"]+)"/);
      if (!m || m[1] <= mine) return;
      var key = 'fips-reloaded-for';
      try { if (sessionStorage.getItem(key) === m[1]) return; sessionStorage.setItem(key, m[1]); } catch (e) {}
      location.reload();
    })
    .catch(function () {});
})();
</script>
"""

CORGI_JS = """
<script>
(function () {
  var c = document.querySelector('.corgi-walk');
  if (!c) return;
  function bark() {
    c.classList.remove('barking'); void c.offsetWidth; c.classList.add('barking');
    clearTimeout(c._t); c._t = setTimeout(function () { c.classList.remove('barking'); }, 900);
  }
  c.addEventListener('click', bark);
  c.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); bark(); } });
})();
</script>
"""


def page(title, description, current, subtitle, body_html, generated_at=None):
    """Wrap page content in the shared FF-themed shell with the corgi header."""
    generated_at = generated_at or datetime.now(timezone.utc)
    stamp = generated_at.strftime('%Y-%m-%d %H:%M UTC')

    def nav_link(href, label, key):
        cls = ' class="current" aria-current="page"' if key == current else ''
        return f'<a href="{href}"{cls}>{label}</a>'

    nav = ''.join([
        nav_link('fips-dashboard-static.html', 'Dashboard', 'dashboard'),
        nav_link('fips-timeline-tracker.html', 'Timeline', 'timeline'),
        '<a href="https://github.com/filecoin-project/FIPs" target="_blank" rel="noopener">FIPs repo ↗</a>',
    ])

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="{html_escape(description)}">
<meta name="color-scheme" content="light dark">
<meta name="generated-at" content="{generated_at.strftime('%Y-%m-%dT%H:%M:%SZ')}">
<meta http-equiv="Cache-Control" content="no-cache">
<title>{html_escape(title)}</title>
{FRESHNESS_JS}
{FONT_LINK}
<style>{CSS}</style>
</head>
<body>
<header class="site-header">
  <div class="wrap">
    <span class="eyebrow">Filecoin governance</span>
    <h1>{html_escape(title)}</h1>
    <p class="sub">{subtitle}</p>
    <div class="header-meta">
      <nav class="nav" aria-label="Pages">{nav}</nav>
      <span>Updated {stamp}</span>
    </div>
  </div>
  <div class="ground" aria-hidden="true"></div>
  <div class="corgi-walk" tabindex="0" role="button" aria-label="Pet the corgi">
    <span class="woof">Woof!</span>
    <div class="corgi-flip">{CORGI_SVG}</div>
  </div>
</header>
<main>
  <div class="wrap">
{body_html}
  </div>
</main>
<footer class="site-footer">
  <div class="wrap">
    <p>Read-only view of <a href="https://github.com/filecoin-project/FIPs" target="_blank" rel="noopener">filecoin-project/FIPs</a>. Status dates come from the README's git history; nothing here changes a FIP's status or decides an outcome. That stays with authors, FIP editors and the process in <a href="https://github.com/filecoin-project/FIPs/blob/master/FIPS/fip-0001.md" target="_blank" rel="noopener">FIP-0001</a>.</p>
    <p>Generated {stamp}. Unofficial community tool.</p>
  </div>
</footer>
{CORGI_JS}
</body>
</html>'''
