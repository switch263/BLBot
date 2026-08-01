"""Procedural "artist's rendering" of the mother in question.

Pure module (PIL only, no Discord, no DB) in the spirit of cogs/lootdrop_card.py,
but living at the repo root because bot.py tries to load every cogs/*.py as an
extension and a module without setup() just logs a failure on boot.

Every call produces a fresh, unique PNG: random palette, random background
style, random silhouette proportions, random face, random appraisal stamp, with
the joke lettered across the bottom like a museum placard. It is deliberately
crude — this is a drawing of a yo-mama joke, not a portrait.
"""

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

# (background top, background bottom, dress, skin, hair) — deliberately loud.
_PALETTES = [
    ((26, 22, 48), (72, 34, 96), (233, 84, 130), (247, 199, 154), (58, 38, 32)),
    ((10, 42, 54), (16, 92, 96), (250, 199, 72), (232, 178, 132), (28, 24, 22)),
    ((58, 18, 18), (128, 44, 30), (108, 176, 232), (240, 205, 172), (196, 148, 62)),
    ((18, 28, 20), (44, 84, 52), (226, 112, 60), (214, 160, 116), (44, 34, 30)),
    ((36, 20, 52), (108, 40, 108), (120, 224, 176), (250, 214, 180), (150, 60, 140)),
    ((44, 44, 52), (96, 96, 112), (232, 232, 240), (222, 176, 142), (110, 110, 120)),
]

_TITLES = [
    "ARTIST'S RENDERING",
    "EXHIBIT A",
    "OFFICIAL PORTRAIT",
    "FIELD SKETCH",
    "SURVEILLANCE STILL",
    "COMMISSIONED WORK",
    "MUSEUM ACQUISITION",
    "STATE EVIDENCE",
    "SCIENTIFIC DIAGRAM",
    "LAST KNOWN PHOTO",
]

_STAMPS = [
    "VERIFIED",
    "APPRAISED",
    "CLASSIFIED",
    "NOT TO SCALE",
    "TO SCALE",
    "UNRETOUCHED",
    "CENSORED",
    "PEER REVIEWED",
    "DO NOT FEED",
    "STRUCTURALLY UNSOUND",
]

# Fake instrument readouts printed down the left margin. (label, unit, low, high)
_STATS = [
    ("MASS", "t", 2, 400),
    ("WIDTH", "m", 3, 90),
    ("HEIGHT", "m", 1, 40),
    ("ORBIT", " moons", 1, 9),
    ("ODOR", " ppm", 400, 99000),
    ("AGE", " ka", 2, 900),
    ("IQ", "", 1, 60),
    ("NET WORTH", " coins", 0, 12),
    ("HAIR", " kg", 3, 220),
    ("THREAT", "/10", 7, 10),
]


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


# ---------- background styles ----------

def _bg_rays(draw, rng, accent):
    cx, cy = W // 2, int(H * 0.42)
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
            fill=_shade(accent, 0.32),
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
    col = _shade(accent, 0.35)
    for x in range(0, W, step):
        draw.line((x, 0, x, H), fill=col, width=1)
    for y in range(0, H, step):
        draw.line((0, y, W, y), fill=col, width=1)


def _bg_stripes(draw, rng, accent):
    step = rng.choice((40, 56, 72))
    col = _shade(accent, 0.3)
    for i in range(-H, W, step * 2):
        draw.polygon([(i, H), (i + step, H), (i + step + H, 0), (i + H, 0)], fill=col)


_BACKGROUNDS = (_bg_rays, _bg_dots, _bg_grid, _bg_stripes)


# ---------- the lady herself ----------

def _figure(draw, rng, palette):
    _, _, dress, skin, hair = palette

    # Proportions swing wildly on purpose — she is a different disaster each time.
    body_w = int(W * rng.uniform(0.34, 0.86))
    body_h = int(H * rng.uniform(0.26, 0.44))
    cx = W // 2 + rng.randint(-14, 14)
    base_y = int(H * 0.68)
    top_y = base_y - body_h

    head_r = int(min(body_w, body_h) * rng.uniform(0.16, 0.30))
    head_r = max(26, min(head_r, 92))
    head_cy = top_y - head_r + rng.randint(-6, 6)

    # legs
    leg_w = max(9, min(26, body_w // 12))
    for side in (-1, 1):
        lx = cx + side * max(leg_w * 2, body_w // 6)
        draw.rounded_rectangle(
            (lx - leg_w, base_y - 20, lx + leg_w, base_y + int(H * 0.10)),
            radius=leg_w, fill=skin,
        )
        draw.ellipse(
            (lx - leg_w - 6, base_y + int(H * 0.085), lx + leg_w + 12, base_y + int(H * 0.125)),
            fill=_shade(dress, 0.5),
        )

    # neck
    draw.rectangle((cx - head_r // 3, head_cy, cx + head_r // 3, top_y + 12), fill=_shade(skin, 0.9))

    # arms — thin, hanging just outside the body, drawn before it so the
    # shoulder end disappears under the dress.
    arm_w = max(9, min(22, body_w // 14))
    arm_drop = rng.uniform(0.55, 0.95)
    for side in (-1, 1):
        ax = cx + side * (body_w // 2 - arm_w)
        ay = top_y + int(body_h * 0.12)
        by = ay + int(body_h * arm_drop) + 24
        draw.rounded_rectangle((ax - arm_w, ay, ax + arm_w, by), radius=arm_w, fill=skin)
        hr = arm_w + 4
        draw.ellipse((ax - hr, by - hr, ax + hr, by + hr), fill=_shade(skin, 0.94))

    # body
    draw.ellipse((cx - body_w // 2, top_y, cx + body_w // 2, base_y), fill=dress)
    draw.ellipse(
        (cx - body_w // 2 + 8, top_y + 8, cx + body_w // 2 - 8, base_y - 8),
        outline=_shade(dress, 0.75), width=3,
    )
    if rng.random() < 0.5:  # polka dots on the dress
        for _ in range(rng.randint(6, 18)):
            dx = rng.randint(cx - body_w // 2 + 20, cx + body_w // 2 - 20)
            dy = rng.randint(top_y + 20, base_y - 20)
            dr = rng.randint(4, 11)
            draw.ellipse((dx - dr, dy - dr, dx + dr, dy + dr), fill=_shade(dress, 0.72))

    # hair (behind the head)
    hair_r = int(head_r * rng.uniform(1.1, 1.5))
    draw.ellipse(
        (cx - hair_r, head_cy - hair_r, cx + hair_r, head_cy + int(hair_r * 0.5)),
        fill=hair,
    )
    if rng.random() < 0.35:  # curlers / bun
        for _ in range(rng.randint(3, 7)):
            bx = cx + rng.randint(-hair_r, hair_r)
            by = head_cy - hair_r + rng.randint(-10, 10)
            br = rng.randint(6, 14)
            draw.ellipse((bx - br, by - br, bx + br, by + br), fill=_shade(hair, 1.25))

    # head
    draw.ellipse((cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r), fill=skin)

    # eyes
    eye_dx = int(head_r * 0.42)
    eye_r = max(5, int(head_r * rng.uniform(0.16, 0.26)))
    for side in (-1, 1):
        ex = cx + side * eye_dx
        ey = head_cy - int(head_r * 0.12)
        draw.ellipse((ex - eye_r, ey - eye_r, ex + eye_r, ey + eye_r), fill=(250, 250, 250))
        pr = max(2, eye_r // 2)
        px = ex + rng.randint(-eye_r // 2, eye_r // 2)
        draw.ellipse((px - pr, ey - pr, px + pr, ey + pr), fill=(20, 20, 20))

    # mouth
    my = head_cy + int(head_r * 0.38)
    mw = int(head_r * rng.uniform(0.4, 0.75))
    mode = rng.random()
    if mode < 0.4:
        draw.arc((cx - mw, my - mw // 2, cx + mw, my + mw), start=200, end=340,
                 fill=(120, 30, 40), width=max(3, head_r // 10))
    elif mode < 0.75:
        draw.ellipse((cx - mw // 2, my - mw // 3, cx + mw // 2, my + mw // 2), fill=(120, 30, 40))
    else:
        draw.line((cx - mw, my, cx + mw, my), fill=(120, 30, 40), width=max(3, head_r // 9))

    if rng.random() < 0.4:  # earrings
        for side in (-1, 1):
            ex = cx + side * head_r
            draw.ellipse((ex - 6, head_cy + 4, ex + 6, head_cy + 16), fill=(240, 200, 60))
    if rng.random() < 0.25:  # cigarette
        draw.line((cx + mw, my, cx + mw + 34, my - 6), fill=(240, 240, 235), width=5)
        draw.ellipse((cx + mw + 30, my - 12, cx + mw + 40, my - 2), fill=(240, 120, 40))


# ---------- text ----------

def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and draw.textlength(trial, font=font) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def _centered(draw, text, font, y, fill, shadow=(0, 0, 0)):
    x = (W - draw.textlength(text, font=font)) / 2
    if shadow is not None:
        draw.text((x + 2, y + 2), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)


def render_joke_image(joke_text: str, *, seed: int | None = None) -> io.BytesIO:
    """Render the joke as a framed portrait PNG. Returns a rewound BytesIO."""
    rng = random.Random(seed)  # None -> OS entropy, unique per call
    palette = rng.choice(_PALETTES)
    top, bottom, dress, skin, hair = palette

    img = _gradient(top, bottom)
    draw = ImageDraw.Draw(img)
    rng.choice(_BACKGROUNDS)(draw, rng, dress)
    _figure(draw, rng, palette)

    # Caption placard — sized to however many lines the joke needs.
    plain = joke_text.replace("*", "")
    cap_font = _font(26, bold=True)
    lines = _wrap(draw, plain, cap_font, W - 72)
    while len(lines) > 4 and cap_font.size > 16:
        cap_font = _font(cap_font.size - 2, bold=True)
        lines = _wrap(draw, plain, cap_font, W - 72)
    line_h = cap_font.size + 8
    panel_h = line_h * len(lines) + 28
    panel_top = H - panel_h

    panel = Image.new("RGB", (W, panel_h), (12, 12, 16))
    img.paste(Image.blend(img.crop((0, panel_top, W, H)), panel, 0.82), (0, panel_top))
    draw.line((0, panel_top, W, panel_top), fill=_shade(dress, 1.1), width=3)
    for i, line in enumerate(lines):
        _centered(draw, line, cap_font, panel_top + 14 + i * line_h, (245, 245, 250))

    # Title banner.
    title_font = _font(30, bold=True)
    title = rng.choice(_TITLES)
    draw.rectangle((0, 0, W, 54), fill=(12, 12, 16))
    draw.line((0, 54, W, 54), fill=_shade(dress, 1.1), width=3)
    _centered(draw, title, title_font, 12, (245, 245, 250))

    # Instrument readouts down the left margin.
    stat_font = _font(15, bold=False)
    for i, (label, unit, lo, hi) in enumerate(rng.sample(_STATS, 4)):
        val = rng.randint(lo, hi)
        draw.text((14, 70 + i * 20), f"{label}: {val:,}{unit}",
                  font=stat_font, fill=(255, 255, 255))

    # Appraisal stamp, rotated, top-right-ish.
    stamp_font = _font(26, bold=True)
    stamp = rng.choice(_STAMPS)
    sw = int(draw.textlength(stamp, font=stamp_font)) + 28
    layer = Image.new("RGBA", (sw, 52), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(layer)
    stamp_col = (220, 60, 60, 235)
    sdraw.rectangle((2, 2, sw - 3, 49), outline=stamp_col, width=4)
    sdraw.text((14, 12), stamp, font=stamp_font, fill=stamp_col)
    layer = layer.rotate(rng.uniform(-22, 22), expand=True, resample=Image.BICUBIC)
    img.paste(layer, (W - layer.width - rng.randint(10, 40), rng.randint(64, 100)), layer)

    # Vignette + frame.
    vign = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vign).ellipse((-W // 3, -H // 3, W + W // 3, H + H // 3), fill=255)
    vign = vign.filter(ImageFilter.GaussianBlur(90))
    img = Image.composite(img, Image.new("RGB", (W, H), (0, 0, 0)), vign)
    ImageDraw.Draw(img).rectangle((0, 0, W - 1, H - 1), outline=_shade(dress, 1.15), width=6)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


if __name__ == "__main__":  # python3 -m yomama_art -> sample to /tmp
    import yomama
    out = "/tmp/yomama_sample.png"
    with open(out, "wb") as f:
        f.write(render_joke_image(yomama.joke()).read())
    print(out)
