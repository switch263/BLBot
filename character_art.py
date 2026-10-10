"""Procedural per-user "character portrait" — a seeded RPG-style character card.

Pure module (PIL only, no Discord, no DB) in the spirit of yomama_art.py, and
living at the repo root for the same reason: bot.py tries to load every
cogs/*.py as an extension, and a module with no setup() just logs a failure on
boot. Keeping it at the root keeps it out of that path.

The whole point is that the portrait is *bound* to a user: every random choice
comes from ``rng = random.Random(seed)``, so the same seed always yields the
byte-identical card. Pass a stable per-user seed (a user id, say) and that user
gets one and only one face — their silhouette, palette, class and epithet never
drift. Two different seeds give two different characters.

The figure is a deliberate step up from the yo-mama blob: a framed character
card with a seeded class/epithet, a name banner, a short seeded stat block, and
a few feature flourishes (hat, glasses, visor, aura). It reuses yomama_art's
font loader, gradient, shading and background techniques.
"""

import colorsys
import io
import math
import os
import random
from typing import Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 640, 640

_FONT_PATHS_BOLD = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)
_FONT_PATHS_PLAIN = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)

# ~20 RPG-ish classes and ~20 titles/epithets. Picked via the seeded rng, so a
# user's class and epithet are as fixed as their face.
_CLASSES = [
    "Degenerate Gambler",
    "Coin Cultist",
    "Jackpot Paladin",
    "Vault Burglar",
    "Loan Shark",
    "Dice Druid",
    "Roulette Ranger",
    "Slot Summoner",
    "Bankruptcy Bard",
    "House Shareholder",
    "Jailbird Rogue",
    "Bounty Hunter",
    "Meth Gator Wrangler",
    "Raccoon Whisperer",
    "Bigfoot Tracker",
    "Tax Evader",
    "Pit Boss",
    "Grifter",
    "High Roller",
    "Chaos Merchant",
    "Minefield Marauder",
    "Pigeon Baron",
]

_TITLES = [
    "the Unlucky",
    "the Overdrawn",
    "the Broke",
    "the Ascendant",
    "the Insolvent",
    "the All-In",
    "of the Red Ledger",
    "the Jailed",
    "the Untaxable",
    "the Doubler",
    "the Busted",
    "the Whale",
    "the Cursed Dealer",
    "the Reckless",
    "the Last Chip",
    "the House Always Wins",
    "the Marked",
    "the Felonious",
    "the Ever-Betting",
    "the Minted",
    "the Degenerate",
    "the Unbanked",
]

# Fake character-sheet readouts printed down the left margin. (label, low, high)
_STATS = [
    ("LCK", 1, 99),
    ("GRD", 1, 99),
    ("CHA", 1, 99),
    ("RISK", 1, 99),
    ("TILT", 1, 99),
    ("NERVE", 1, 99),
    ("DEBT", 0, 99),
    ("RAP", 0, 99),
    ("EDGE", 1, 99),
    ("VIBE", 1, 99),
]

_RANKS = ("F", "E", "D", "C", "B", "A", "S", "SS")


def _font(size: int, bold: bool = True):
    for p in (_FONT_PATHS_BOLD if bold else _FONT_PATHS_PLAIN):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _clamp(n: float) -> int:
    n = int(n)
    return 0 if n < 0 else 255 if n > 255 else n


def _shade(c: Tuple[int, int, int], factor: float) -> Tuple[int, int, int]:
    return (_clamp(c[0] * factor), _clamp(c[1] * factor), _clamp(c[2] * factor))


def _hsv(h: float, s: float, v: float) -> Tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return (_clamp(r * 255), _clamp(g * 255), _clamp(b * 255))


def _gradient(top, bottom) -> Image.Image:
    img = Image.new("RGB", (1, H))
    px = img.load()
    for y in range(H):
        t = y / (H - 1)
        px[0, y] = (
            _clamp(top[0] + (bottom[0] - top[0]) * t),
            _clamp(top[1] + (bottom[1] - top[1]) * t),
            _clamp(top[2] + (bottom[2] - top[2]) * t),
        )
    return img.resize((W, H))


# ---------- seeded palette ----------

# Hand-picked tones so the figure still reads as a "character" rather than a
# random blob; the hues around them are generated so no two users share a card.
_SKIN_TONES = [
    (247, 199, 154), (232, 178, 132), (214, 160, 116), (176, 124, 84),
    (138, 96, 66), (96, 66, 48), (126, 158, 92), (150, 196, 210),
]
_HAIR_TONES = [
    (58, 38, 32), (28, 24, 22), (196, 148, 62), (150, 60, 140),
    (210, 70, 70), (70, 120, 200), (60, 170, 150), (230, 230, 235),
]


def _palette(rng) -> dict:
    base = rng.random()
    return {
        "top": _hsv(base, rng.uniform(0.35, 0.6), rng.uniform(0.18, 0.30)),
        "bottom": _hsv((base + rng.uniform(0.05, 0.18)) % 1.0,
                       rng.uniform(0.45, 0.7), rng.uniform(0.38, 0.52)),
        "outfit": _hsv((base + 0.5) % 1.0, rng.uniform(0.55, 0.9), rng.uniform(0.6, 0.9)),
        "accent": _hsv((base + rng.uniform(0.28, 0.4)) % 1.0, rng.uniform(0.7, 0.95),
                       rng.uniform(0.85, 1.0)),
        "skin": rng.choice(_SKIN_TONES),
        "hair": rng.choice(_HAIR_TONES),
    }


# ---------- background styles ----------

def _bg_rays(draw, rng, accent):
    cx, cy = W // 2, int(H * 0.40)
    n = rng.randrange(12, 26, 2)
    off = rng.uniform(0, math.tau)
    for i in range(n):
        if i % 2:
            continue
        a1 = off + i * math.tau / n
        a2 = a1 + math.tau / n
        far = W * 1.6
        draw.polygon(
            [(cx, cy),
             (cx + far * math.cos(a1), cy + far * math.sin(a1)),
             (cx + far * math.cos(a2), cy + far * math.sin(a2))],
            fill=_shade(accent, 0.30),
        )


def _bg_dots(draw, rng, accent):
    step = rng.choice((32, 40, 52))
    r = step // 6
    for y in range(0, H, step):
        for x in range(0, W, step):
            jx = rng.randint(-3, 3)
            draw.ellipse((x + jx - r, y - r, x + jx + r, y + r), fill=_shade(accent, 0.4))


def _bg_grid(draw, rng, accent):
    step = rng.choice((28, 36, 44))
    col = _shade(accent, 0.33)
    for x in range(0, W, step):
        draw.line((x, 0, x, H), fill=col, width=1)
    for y in range(0, H, step):
        draw.line((0, y, W, y), fill=col, width=1)


def _bg_stripes(draw, rng, accent):
    step = rng.choice((40, 56, 72))
    col = _shade(accent, 0.3)
    for i in range(-H, W, step * 2):
        draw.polygon([(i, H), (i + step, H), (i + step + H, 0), (i + H, 0)], fill=col)


def _bg_rings(draw, rng, accent):
    cx, cy = W // 2, int(H * 0.42)
    step = rng.choice((34, 44, 54))
    for r in range(step, W, step):
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=_shade(accent, 0.32), width=2)


_BACKGROUNDS = (_bg_rays, _bg_dots, _bg_grid, _bg_stripes, _bg_rings)


# ---------- feature flourishes ----------

def _feat_hat(draw, rng, p):
    col = p["accent"]
    hr = p["head_r"]
    cx, top = p["head_cx"], p["head_top"]
    style = rng.random()
    if style < 0.4:  # wizard / party cone
        draw.polygon(
            [(cx - int(hr * 0.9), top + int(hr * 0.2)),
             (cx + int(hr * 0.9), top + int(hr * 0.2)),
             (cx + rng.randint(-10, 10), top - int(hr * 1.6))],
            fill=col,
        )
        draw.ellipse((cx - 8, top - int(hr * 1.6) - 8, cx + 8, top - int(hr * 1.6) + 8),
                     fill=_shade(col, 1.3))
    elif style < 0.7:  # top hat
        brim = int(hr * 1.2)
        draw.rectangle((cx - brim, top, cx + brim, top + 6), fill=(24, 24, 28))
        draw.rectangle((cx - int(hr * 0.8), top - int(hr * 1.1), cx + int(hr * 0.8), top + 4),
                       fill=(24, 24, 28))
        draw.rectangle((cx - int(hr * 0.8), top - int(hr * 0.3), cx + int(hr * 0.8), top),
                       fill=col)
    else:  # crown
        pts = []
        base = top + 2
        for k in range(5):
            x = cx - hr + k * (2 * hr) // 4
            pts.append((x, base))
            pts.append((x + hr // 4, base - rng.randint(14, 24)))
        pts.append((cx + hr, base))
        draw.polygon(pts, fill=(240, 200, 60))


def _feat_glasses(draw, rng, p):
    col = (30, 30, 36)
    er = p["eye_er"] + 4
    for side in (-1, 1):
        ex = p["head_cx"] + side * p["eye_dx"]
        draw.ellipse((ex - er, p["eye_ey"] - er, ex + er, p["eye_ey"] + er), outline=col, width=3)
    draw.line((p["head_cx"] - p["eye_dx"] + er, p["eye_ey"],
               p["head_cx"] + p["eye_dx"] - er, p["eye_ey"]), fill=col, width=3)


def _feat_visor(draw, rng, p):
    col = p["accent"]
    ex0 = p["head_cx"] - int(p["head_r"] * 0.8)
    ex1 = p["head_cx"] + int(p["head_r"] * 0.8)
    ey = p["eye_ey"]
    draw.rounded_rectangle((ex0, ey - 12, ex1, ey + 12), radius=10, fill=_shade(col, 0.6))
    draw.line((ex0 + 4, ey, ex1 - 4, ey), fill=_shade(col, 1.6), width=3)


def _feat_eyepatch(draw, rng, p):
    ex = p["head_cx"] + rng.choice((-1, 1)) * p["eye_dx"]
    ey = p["eye_ey"]
    er = p["eye_er"] + 5
    draw.ellipse((ex - er, ey - er, ex + er, ey + er), fill=(20, 20, 22))
    draw.line((ex - er, ey - er - 6, p["head_cx"] + p["head_r"], p["head_top"] + 4),
              fill=(20, 20, 22), width=3)
    draw.line((ex + er, ey - er - 6, p["head_cx"] - p["head_r"], p["head_top"] + 4),
              fill=(20, 20, 22), width=3)


def _feat_scar(draw, rng, p):
    ex = p["head_cx"] + rng.choice((-1, 1)) * int(p["head_r"] * 0.45)
    y0 = p["head_cy"] - int(p["head_r"] * 0.3)
    draw.line((ex, y0, ex, y0 + int(p["head_r"] * 0.7)), fill=_shade(p["skin"], 0.6), width=2)
    for k in range(3):
        yy = y0 + k * int(p["head_r"] * 0.3)
        draw.line((ex - 5, yy, ex + 5, yy), fill=_shade(p["skin"], 0.6), width=2)


_FEATURE_DRAWERS = {
    "hat": _feat_hat, "glasses": _feat_glasses, "visor": _feat_visor,
    "eyepatch": _feat_eyepatch, "scar": _feat_scar,
}


# ---------- the character ----------

def _aura(base_img, rng, p):
    """A soft glow ring behind the head, blended under the figure."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    r = int(p["head_r"] * rng.uniform(1.6, 2.4))
    col = p["accent"]
    ld.ellipse((p["head_cx"] - r, p["head_cy"] - r, p["head_cx"] + r, p["head_cy"] + r),
               fill=(col[0], col[1], col[2], 150))
    layer = layer.filter(ImageFilter.GaussianBlur(rng.randint(18, 34)))
    base_img.paste(Image.alpha_composite(base_img.convert("RGBA"), layer).convert("RGB"), (0, 0))


def _figure(img, draw, rng, palette):
    """Draw the avatar centered on the card. Returns the feature dict used."""
    outfit, skin, hair, accent = (
        palette["outfit"], palette["skin"], palette["hair"], palette["accent"],
    )

    body_w = int(W * rng.uniform(0.34, 0.52))
    body_h = int(H * rng.uniform(0.26, 0.36))
    cx = W // 2 + rng.randint(-10, 10)
    base_y = int(H * 0.70)
    top_y = base_y - body_h

    head_r = int(min(body_w, body_h) * rng.uniform(0.30, 0.44))
    head_r = max(40, min(head_r, 100))
    head_cx, head_cy = cx, top_y - head_r + rng.randint(-4, 6)

    # pick feature flourishes up front so geometry (hat vs hair) can coexist
    feats = []
    if rng.random() < 0.55:
        feats.append("hat")
    if rng.random() < 0.5:
        feats.append(rng.choice(("glasses", "visor", "eyepatch")))
    if rng.random() < 0.3:
        feats.append("scar")
    has_aura = rng.random() < 0.5

    # legs
    leg_w = max(9, min(24, body_w // 10))
    leg_len = int(H * 0.10)
    for side in (-1, 1):
        lx = cx + side * max(leg_w * 2, body_w // 6)
        draw.rounded_rectangle(
            (lx - leg_w, base_y - 20, lx + leg_w, base_y + leg_len),
            radius=leg_w, fill=skin,
        )
        draw.ellipse(
            (lx - leg_w - 6, base_y + leg_len - int(H * 0.015),
             lx + leg_w + 12, base_y + leg_len + int(H * 0.04)),
            fill=_shade(outfit, 0.5),
        )

    # aura (behind everything but the background)
    p_pre = {"head_cx": head_cx, "head_cy": head_cy, "head_r": head_r, "accent": accent}
    if has_aura:
        _aura(img, rng, p_pre)

    # neck
    draw.rectangle((head_cx - head_r // 3, head_cy, head_cx + head_r // 3, top_y + 12),
                   fill=_shade(skin, 0.9))

    # arms
    arm_w = max(9, min(20, body_w // 12))
    arm_drop = rng.uniform(0.55, 0.9)
    for side in (-1, 1):
        ax = cx + side * (body_w // 2 - arm_w)
        ay = top_y + int(body_h * 0.12)
        by = ay + int(body_h * arm_drop) + 24
        draw.rounded_rectangle((ax - arm_w, ay, ax + arm_w, by), radius=arm_w, fill=outfit)
        hr = arm_w + 4
        draw.ellipse((ax - hr, by - hr, ax + hr, by + hr), fill=_shade(skin, 0.94))

    # body / torso
    draw.ellipse((cx - body_w // 2, top_y, cx + body_w // 2, base_y), fill=outfit)
    draw.ellipse(
        (cx - body_w // 2 + 8, top_y + 8, cx + body_w // 2 - 8, base_y - 8),
        outline=_shade(outfit, 0.75), width=3,
    )
    # a class sigil on the chest
    if rng.random() < 0.6:
        sr = max(8, body_w // 8)
        sy = top_y + body_h // 2
        draw.ellipse((cx - sr, sy - sr, cx + sr, sy + sr), fill=_shade(accent, 1.0))
        draw.ellipse((cx - sr + 4, sy - sr + 4, cx + sr - 4, sy + sr - 4),
                     outline=_shade(accent, 0.6), width=3)

    # hair (behind head) unless a hat hides it entirely
    hair_r = int(head_r * rng.uniform(1.05, 1.5))
    draw.ellipse(
        (head_cx - hair_r, head_cy - hair_r, head_cx + hair_r, head_cy + int(hair_r * 0.5)),
        fill=hair,
    )

    # head
    draw.ellipse((head_cx - head_r, head_cy - head_r, head_cx + head_r, head_cy + head_r),
                 fill=skin)

    # eyes (sclera + pupil)
    eye_dx = int(head_r * 0.42)
    eye_er = max(5, int(head_r * rng.uniform(0.16, 0.24)))
    eye_ey = head_cy - int(head_r * 0.08)
    for side in (-1, 1):
        ex = head_cx + side * eye_dx
        draw.ellipse((ex - eye_er, eye_ey - eye_er, ex + eye_er, eye_ey + eye_er),
                     fill=(250, 250, 250))
        pr = max(2, eye_er // 2)
        px = ex + rng.randint(-eye_er // 3, eye_er // 3)
        py = eye_ey + rng.randint(-eye_er // 3, eye_er // 3)
        draw.ellipse((px - pr, py - pr, px + pr, py + pr), fill=(20, 20, 24))

    # mouth
    my = head_cy + int(head_r * 0.42)
    mw = int(head_r * rng.uniform(0.4, 0.7))
    mode = rng.random()
    if mode < 0.45:
        draw.arc((head_cx - mw, my - mw // 2, head_cx + mw, my + mw),
                 start=200, end=340, fill=(120, 40, 50), width=max(3, head_r // 10))
    elif mode < 0.75:
        draw.line((head_cx - mw, my, head_cx + mw, my),
                  fill=(120, 40, 50), width=max(3, head_r // 9))
    else:
        draw.ellipse((head_cx - mw // 2, my - mw // 3, head_cx + mw // 2, my + mw // 2),
                     fill=(120, 40, 50))

    p = {
        "head_cx": head_cx, "head_cy": head_cy, "head_r": head_r,
        "head_top": head_cy - head_r,
        "eye_dx": eye_dx, "eye_ey": eye_ey, "eye_er": eye_er,
        "skin": skin, "outfit": outfit, "hair": hair, "accent": accent,
        "features": tuple(feats),
    }
    for name in feats:
        if name in _FEATURE_DRAWERS:
            _FEATURE_DRAWERS[name](draw, rng, p)
    return p


# ---------- text ----------

def _centered(draw, text, font, y, fill, shadow=(0, 0, 0)):
    x = (W - draw.textlength(text, font=font)) / 2
    if shadow is not None:
        draw.text((x + 2, y + 2), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)


def _fit_centered(draw, text, y, fill, start_size, min_size=14):
    """Pick the largest bold font (<= start_size) that fits within the margins."""
    size = start_size
    font = _font(size, bold=True)
    while size > min_size and draw.textlength(text, font=font) > W - 72:
        size -= 2
        font = _font(size, bold=True)
    _centered(draw, text, font, y, fill)
    return size


def _render(display_name: str, rng) -> Image.Image:
    palette = _palette(rng)
    img = _gradient(palette["top"], palette["bottom"])
    draw = ImageDraw.Draw(img)
    rng.choice(_BACKGROUNDS)(draw, rng, palette["accent"])

    _figure(img, draw, rng, palette)
    draw = ImageDraw.Draw(img)  # figure may have pasted a new base; refresh

    char_class = rng.choice(_CLASSES)
    title = rng.choice(_TITLES)

    # Top banner: the class.
    draw.rectangle((0, 0, W, 54), fill=(12, 12, 16))
    draw.line((0, 54, W, 54), fill=_shade(palette["accent"], 1.1), width=3)
    _centered(draw, char_class.upper(), _font(30, bold=True), 12, (245, 245, 250))

    # Bottom placard: the name + epithet.
    panel_h = 112
    panel_top = H - panel_h
    panel = Image.new("RGB", (W, panel_h), (12, 12, 16))
    img.paste(Image.blend(img.crop((0, panel_top, W, H)), panel, 0.82), (0, panel_top))
    draw.line((0, panel_top, W, panel_top), fill=_shade(palette["accent"], 1.1), width=3)

    name = (display_name or "Unknown").strip() or "Unknown"
    _fit_centered(draw, name, panel_top + 16, (245, 245, 250), 40)
    _centered(draw, title, _font(24, bold=False), panel_top + 68, _shade(palette["accent"], 1.3))

    # Character-sheet stat block down the left margin.
    stat_font = _font(16, bold=True)
    for i, (label, lo, hi) in enumerate(rng.sample(_STATS, 5)):
        val = rng.randint(lo, hi)
        rank = _RANKS[min(len(_RANKS) - 1, val * len(_RANKS) // 100)]
        draw.text((14, 70 + i * 22), f"{label} {val:>2}  {rank}",
                  font=stat_font, fill=(255, 255, 255))

    # "Level" badge, rotated, top-right-ish.
    badge_font = _font(24, bold=True)
    badge = f"LV {rng.randint(1, 99)}"
    sw = int(draw.textlength(badge, font=badge_font)) + 28
    layer = Image.new("RGBA", (sw, 48), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(layer)
    bc = (*_shade(palette["accent"], 1.0), 235)
    sdraw.rectangle((2, 2, sw - 3, 45), outline=bc, width=4)
    sdraw.text((14, 10), badge, font=badge_font, fill=bc)
    layer = layer.rotate(rng.uniform(-18, 18), expand=True, resample=Image.BICUBIC)
    img.paste(layer, (W - layer.width - rng.randint(12, 36), rng.randint(64, 96)), layer)

    # Vignette + frame.
    vign = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vign).ellipse((-W // 3, -H // 3, W + W // 3, H + H // 3), fill=255)
    vign = vign.filter(ImageFilter.GaussianBlur(90))
    img = Image.composite(img, Image.new("RGB", (W, H), (0, 0, 0)), vign)
    ImageDraw.Draw(img).rectangle((0, 0, W - 1, H - 1),
                                  outline=_shade(palette["accent"], 1.15), width=6)
    return img


def _fallback(display_name: str, rng) -> Image.Image:
    """A plain but valid card, used if the full render raises on odd input."""
    try:
        bg = _hsv(rng.random(), 0.4, 0.3)
    except Exception:
        bg = (30, 30, 40)
    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, W - 1, H - 1), outline=(220, 220, 230), width=6)
    name = (display_name or "Unknown").strip() or "Unknown"
    try:
        _centered(draw, name[:40], _font(36, bold=True), H // 2 - 24, (245, 245, 250))
    except Exception:
        pass
    return img


def render_character_image(display_name: str, *, seed: int) -> io.BytesIO:
    """Render a unique, seed-bound character portrait. Returns a rewound BytesIO.

    Every random choice is drawn from ``random.Random(seed)``, so the same seed
    always produces the byte-identical PNG — that is what binds a card to a
    user. Never raises on odd input: a failure in the full render falls back to
    a plain-but-valid card so the caller always gets a PNG.
    """
    rng = random.Random(seed)
    try:
        img = _render(display_name, rng)
    except Exception:
        img = _fallback(display_name, random.Random(seed))

    buf = io.BytesIO()
    try:
        img.save(buf, "PNG", optimize=True)
    except Exception:
        buf = io.BytesIO()
        Image.new("RGB", (W, H), (30, 30, 40)).save(buf, "PNG")
    buf.seek(0)
    return buf


if __name__ == "__main__":  # python3 -m character_art -> sample card to /tmp
    out = "/tmp/character_sample.png"
    with open(out, "wb") as f:
        f.write(render_character_image("Sample Hero", seed=1234).read())
    print(out)
