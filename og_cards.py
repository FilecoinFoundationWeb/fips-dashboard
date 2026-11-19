#!/usr/bin/env python3
"""Link-preview images (1200x630 PNG) for Slack, X, Discord and the like.

  og/site.png      used by every page
  og/NNNN.png      one per FIP: number, title and status

Optional: needs Pillow (the workflow installs it). Without Pillow nothing is
drawn and pages simply don't advertise an image. Uses Archivo when
ARCHIVO_FONT points at the font file (the workflow downloads it), otherwise
DejaVu Sans, which GitHub's Ubuntu runners have.
"""

import os

OUT_DIR = 'og'
W, H = 1200, 630
NAVY, NAVY2, BLUE, SKY, WHITE, MUTED = '#091B2A', '#0F2A42', '#0090FF', '#7CC4FF', '#FFFFFF', '#9FB6CC'
STATUS = {  # background, text: the site's status colours
    'Final': ('#DDF5E8', '#0B6B3A'), 'Accepted': ('#DCEEFF', '#00539A'), 'Last Call': ('#FFF0D1', '#8A5300'),
    'Draft': ('#E6EBF5', '#34476B'), 'Active': ('#D7F3F5', '#0A6670'), 'Deferred': ('#F1EBDD', '#6E5A2E'),
    'Rejected': ('#FDE2E2', '#A11A1A'), 'Withdrawn': ('#ECEFF3', '#55606C'), 'Superseded': ('#ECEFF3', '#55606C'),
}
FALLBACK_FONTS = ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                  '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf']


def available():
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def _font(size, weight=700):
    from PIL import ImageFont
    path = os.environ.get('ARCHIVO_FONT')
    if path and os.path.exists(path):
        f = ImageFont.truetype(path, size)
        try:  # variable font: set the weight axis by name, leave the others at default
            values = []
            for ax in f.get_variation_axes():
                name = ax.get('name')
                name = name.decode() if isinstance(name, bytes) else str(name)
                values.append(max(ax['minimum'], min(ax['maximum'], weight)) if 'weight' in name.lower()
                              else ax.get('default', ax['minimum']))
            f.set_variation_by_axes(values)
        except Exception:
            pass  # static font or no variation support: use as is
        return f
    for p in FALLBACK_FONTS:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


def _wrap(draw, text, font, width, max_lines):
    words, lines, cur = text.split(), [], ''
    for w in words:
        test = (cur + ' ' + w).strip()
        if draw.textlength(test, font=font) <= width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and ' '.join(lines) != ' '.join(words):
        last = lines[-1]
        while last and draw.textlength(last + '…', font=font) > width:
            last = last.rsplit(' ', 1)[0] if ' ' in last else last[:-1]
        lines[-1] = last + '…'
    return lines


def _base():
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (W, H), NAVY)
    d = ImageDraw.Draw(img)
    # soft blue glow, top right, like the site header
    for r in range(420, 0, -6):
        a = int(70 * (1 - r / 420) ** 2)
        d.ellipse([W - 260 - r, -180 - r, W - 260 + r, -180 + r], fill=_mix(NAVY, BLUE, a / 255))
    d.rectangle([0, H - 10, W, H], fill=BLUE)
    # eyebrow
    d.ellipse([72, 70, 88, 86], fill=BLUE)
    d.text((104, 64), 'FILECOIN GOVERNANCE', font=_font(26, 600), fill=SKY)
    return img, d


def _mix(a, b, t):
    a, b = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def fip_card(path, number, title, status, kind='FIP'):
    img, d = _base()
    d.text((72, 140), f'{kind}-{number}', font=_font(96, 800), fill=WHITE)
    y = 270
    for line in _wrap(d, title, _font(52, 700), W - 144, 3):
        d.text((72, y), line, font=_font(52, 700), fill=WHITE)
        y += 66
    bg, fg = STATUS.get(status, STATUS['Draft'])
    f = _font(30, 700)
    label = status.upper()
    tw = d.textlength(label, font=f)
    d.rounded_rectangle([72, H - 120, 72 + tw + 44, H - 66], radius=27, fill=bg)
    d.text((94, H - 113), label, font=f, fill=fg)
    d.text((W - 72 - d.textlength('filecoinfoundationweb.github.io/fips-dashboard', font=_font(24, 500)), H - 104),
           'filecoinfoundationweb.github.io/fips-dashboard', font=_font(24, 500), fill=MUTED)
    img.save(path, optimize=True)


def site_card(path, n_fips):
    img, d = _base()
    d.text((72, 150), 'Filecoin Governance Hub', font=_font(80, 800), fill=WHITE)
    y = 270
    for line in _wrap(d, f'Every FIP, Core Devs meeting and network upgrade in one place. {n_fips} FIPs, updated every 6 hours.',
                      _font(40, 500), W - 144, 3):
        d.text((72, y), line, font=_font(40, 500), fill='#B9CDE0')
        y += 54
    d.text((72, H - 104), 'filecoinfoundationweb.github.io/fips-dashboard', font=_font(26, 600), fill=SKY)
    img.save(path, optimize=True)


def write_all(ctx):
    if not available():
        print('Pillow not installed: skipping link-preview images')
        return False
    os.makedirs(OUT_DIR, exist_ok=True)
    nums = sorted(set(ctx['fips']) | set(ctx['files']), key=int)
    keep = {f'{n}.png' for n in nums} | {'site.png'}
    for name in os.listdir(OUT_DIR):
        if name.endswith('.png') and name not in keep:
            os.remove(os.path.join(OUT_DIR, name))
    site_card(os.path.join(OUT_DIR, 'site.png'), len(nums))
    for n in nums:
        fip, f = ctx['fips'].get(n) or {}, ctx['files'].get(n) or {}
        fip_card(os.path.join(OUT_DIR, f'{n}.png'), n, fip.get('title') or f.get('title') or '',
                 fip.get('status') or f.get('_status') or 'Draft')
    print(f'Generated {len(nums) + 1} link-preview images')
    return True
