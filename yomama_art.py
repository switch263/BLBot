"""Procedural "artist's rendering" of the mother in question.

Pure module (PIL only, no Discord, no DB) in the spirit of cogs/lootdrop_card.py,
but living at the repo root because bot.py tries to load every cogs/*.py as an
extension and a module without setup() just logs a failure on boot.

Every call produces a fresh, unique PNG: random palette, random background
style, random silhouette proportions, random face, random appraisal stamp, with
the joke lettered across the bottom like a museum placard. It is deliberately
crude — this is a drawing of a yo-mama joke, not a portrait.

Passing the joke's category (yomama.joke_with_category() reports it) makes the
portrait match the bit: a "fat" mama is drawn wide, a "tall" mama long, a
"hairy" mama shaggier, a "nasty" mama green with flies. Without a category the
figure rolls its proportions the old way — a generic mother of unknown flavor.
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

# Per-category profiles. A profile may override any of the base proportion
# ranges and/or name drawable features. Missing keys keep the base value, so a
# category is always a *bias* on top of the random figure, never a full redraw.
_PROFILE_DEFAULTS = {
    "body_w": (0.34, 0.86),   # W fraction
    "body_h": (0.26, 0.44),   # H fraction
    "head_r": (0.16, 0.30),   # fraction of min(body_w, body_h)
    "hair_r": (1.1, 1.5),     # multiple of head_r
    "leg": 0.10,              # H fraction for leg length
    "slouch": 0.0,            # 0..1, how far the head dips/hunches
    "skin": None,             # None -> palette skin, else an (r,g,b) override
    "features": (),
}

_PROFILES = {
    "fat":    {"body_w": (0.62, 0.98), "body_h": (0.30, 0.46), "head_r": (0.13, 0.20)},
    "tall":   {"body_w": (0.30, 0.55), "body_h": (0.40, 0.60), "leg": 0.16, "head_r": (0.14, 0.22)},
    "short":  {"body_w": (0.22, 0.44), "body_h": (0.18, 0.30), "head_r": (0.24, 0.34)},
    "hairy":  {"hair_r": (1.5, 2.3), "features": ("bangs",)},
    "old":    {"slouch": 0.35, "features": ("glasses", "wrinkles", "cane")},
    "stupid": {"features": ("crossed_eyes", "open_mouth")},
    "ugly":   {"features": ("lopsided", "warts")},
    "poor":   {"slouch": 0.20, "features": ("patches",)},
    "lazy":   {"slouch": 0.40, "features": ("half_eyes", "zzz")},
    "nasty":  {"skin": (126, 158, 92), "features": ("flies", "stink")},
}


def _profile(category: str | None) -> dict:
    prof = dict(_PROFILE_DEFAULTS)
    if category in _PROFILES:
        prof.update(_PROFILES[category])
    return prof


def _feat_glasses(draw, rng, p):
    col = (40, 40, 45)
    er = p["eye_er"] + 4
    for side in (-1, 1):
        ex = p["head_cx"] + side * p["eye_dx"]
        draw.ellipse((ex - er, p["eye_ey"] - er, ex + er, p["eye_ey"] + er), outline=col, width=3)
    draw.line((p["head_cx"] - p["eye_dx"] + er, p["eye_ey"],
               p["head_cx"] + p["eye_dx"] - er, p["eye_ey"]), fill=col, width=3)


def _feat_wrinkles(draw, rng, p):
    col = _shade(p["skin"], 0.7)
    for i in range(3):  # forehead
        y = p["head_cy"] - int(p["head_r"] * 0.5) + i * 6
        x0 = p["head_cx"] - int(p["head_r"] * 0.5)
        x1 = p["head_cx"] + int(p["head_r"] * 0.5)
        draw.arc((x0, y - 4, x1, y + 4), start=200, end=340, fill=col, width=2)
    for side in (-1, 1):  # under the eyes
        ex = p["head_cx"] + side * p["eye_dx"]
        draw.line((ex - p["eye_er"], p["eye_ey"] + p["eye_er"] + 3,
                   ex + p["eye_er"], p["eye_ey"] + p["eye_er"] + 3), fill=col, width=2)


def _feat_warts(draw, rng, p):
    col = _shade(p["skin"], 0.6)
    for _ in range(rng.randint(3, 6)):
        x = p["head_cx"] + rng.randint(-p["head_r"] + 6, p["head_r"] - 6)
        y = p["head_cy"] + rng.randint(-p["head_r"] // 2, p["head_r"])
        r = rng.randint(2, 4)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=col)


def _feat_bangs(draw, rng, p):
    col = p["hair"]
    for _ in range(rng.randint(5, 9)):
        x = p["head_cx"] + rng.randint(-p["head_r"], p["head_r"])
        y = p["head_cy"] - p["head_r"] + rng.randint(0, 10)
        w = rng.randint(6, 12)
        draw.ellipse((x - w, y - 4, x + w, y + 8), fill=col)


def _feat_flies(draw, rng, p):
    for _ in range(rng.randint(4, 7)):
        a = rng.uniform(0, math.tau)
        d = p["head_r"] + rng.randint(6, 26)
        x = p["head_cx"] + int(d * math.cos(a))
        y = p["head_cy"] - int(d * math.sin(a) * 0.6)
        draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(30, 25, 20))


def _feat_stink(draw, rng, p):
    col = (150, 150, 110)
    for i in range(3):
        x = p["head_cx"] - 10 + i * 12
        y = p["head_top"] - 6
        draw.arc((x - 6, y - 16, x + 6, y + 2), start=120, end=300, fill=col, width=2)


def _feat_zzz(draw, rng, p):
    f = _font(18, bold=True)
    x = p["head_cx"] + p["head_r"] + 8
    y = p["head_top"] + 6
    for i, c in enumerate("zZz"):
        draw.text((x + i * 14, y - i * 16), c, font=f, fill=(240, 240, 250))


def _feat_cane(draw, rng, p):
    col = (90, 60, 35)
    hx, hy = p["hand_r"]
    x = hx + 14
    y1 = p["base_y"] + int(H * 0.05)
    draw.line((x, hy - 6, x, y1), fill=col, width=6)
    draw.arc((x - 14, hy - 20, x + 14, hy - 2), start=180, end=320, fill=col, width=6)


def _feat_patches(draw, rng, p):
    for _ in range(rng.randint(3, 5)):
        x = p["cx"] + rng.randint(-p["body_w"] // 2 + 14, p["body_w"] // 2 - 14)
        y = p["top_y"] + rng.randint(14, max(16, p["body_h"] - 28))
        w, h = rng.randint(14, 30), rng.randint(10, 22)
        draw.rounded_rectangle((x - w, y - h, x + w, y + h), radius=4,
                               fill=_shade(p["dress"], 0.72), outline=_shade(p["dress"], 0.5), width=2)


_FEATURE_DRAWERS = {
    "glasses": _feat_glasses, "wrinkles": _feat_wrinkles, "warts": _feat_warts,
    "bangs": _feat_bangs, "flies": _feat_flies, "stink": _feat_stink,
    "zzz": _feat_zzz, "cane": _feat_cane, "patches": _feat_patches,
}


def _draw_face(draw, rng, p):
    """Pupils + mouth + every named feature, drawn over the base head.

    Pupils and mouth are feature-aware (crossed/half/lopsided eyes, open
    mouth); everything else dispatches to FEATURE_DRAWERS.
    """
    feats = p["features"]
    skin = p["skin"]
    for side in (-1, 1):
        ex = p["head_cx"] + side * p["eye_dx"]
        ey = p["eye_ey"]
        er = p["eye_er"]
        if "crossed_eyes" in feats:
            px, py = ex - side * max(3, int(er * 0.9)), ey
        elif "half_eyes" in feats:
            draw.rectangle((ex - er, ey - er, ex + er, ey + int(er * 0.9)), fill=skin)
            draw.arc((ex - er, ey - er, ex + er, ey + er), start=0, end=180,
                     fill=_shade(skin, 0.7), width=2)
            px, py = ex + rng.randint(-er // 3, er // 3), ey + int(er * 0.35)
        elif "lopsided" in feats and side == 1:
            er = int(er * 1.25)
            px, py = ex + rng.randint(-er // 3, er // 3) + int(er * 0.4), ey + int(er * 0.5)
        else:
            px, py = ex + rng.randint(-er // 2, er // 2), ey + rng.randint(-er // 3, er // 3)
        pr = max(2, er // 2)
        draw.ellipse((px - pr, py - pr, px + pr, py + pr), fill=(20, 20, 20))

    # mouth — "open_mouth" overrides the base roll with a big open jaw
    my, mw = p["mouth_my"], p["mouth_mw"]
    if "open_mouth" in feats:
        draw.ellipse((p["head_cx"] - mw // 2, my - mw // 3,
                      p["head_cx"] + mw // 2, my + mw // 2), fill=(120, 30, 40))
        draw.ellipse((p["head_cx"] - mw // 3, my - mw // 6,
                      p["head_cx"] + mw // 3, my + int(mw * 0.3)), fill=(70, 16, 22))
    else:
        mode = p["mouth_mode"]
        if mode < 0.4:
            draw.arc((p["head_cx"] - mw, my - mw // 2, p["head_cx"] + mw, my + mw),
                     start=200, end=340, fill=(120, 30, 40), width=max(3, p["head_r"] // 10))
        elif mode < 0.75:
            draw.ellipse((p["head_cx"] - mw // 2, my - mw // 3, p["head_cx"] + mw // 2, my + mw // 2),
                         fill=(120, 30, 40))
        else:
            draw.line((p["head_cx"] - mw, my, p["head_cx"] + mw, my),
                      fill=(120, 30, 40), width=max(3, p["head_r"] // 9))

    for name in feats:
        if name in _FEATURE_DRAWERS:
            _FEATURE_DRAWERS[name](draw, rng, p)


def _figure(draw, rng, palette, category: str | None = None):
    _, _, dress, skin, hair = palette
    prof = _profile(category)

    # Proportions swing wildly on purpose — she is a different disaster each time,
    # and the category, when present, pushes the swing in its direction.
    body_w = int(W * rng.uniform(*prof["body_w"]))
    body_h = int(H * rng.uniform(*prof["body_h"]))
    cx = W // 2 + rng.randint(-14, 14)
    base_y = int(H * 0.68)
    top_y = base_y - body_h

    head_r = int(min(body_w, body_h) * rng.uniform(*prof["head_r"]))
    head_r = max(26, min(head_r, 92))
    head_cx, head_cy = cx, top_y - head_r + rng.randint(-6, 6)
    if prof["slouch"]:
        head_cy += int(head_r * prof["slouch"] * 0.8)
        head_cx += int(head_r * prof["slouch"] * 0.5)
    if prof["skin"]:
        skin = prof["skin"]

    # legs
    leg_w = max(9, min(26, body_w // 12))
    leg_len = int(H * prof["leg"])
    for side in (-1, 1):
        lx = cx + side * max(leg_w * 2, body_w // 6)
        draw.rounded_rectangle(
            (lx - leg_w, base_y - 20, lx + leg_w, base_y + leg_len),
            radius=leg_w, fill=skin,
        )
        draw.ellipse(
            (lx - leg_w - 6, base_y + leg_len - int(H * 0.015),
             lx + leg_w + 12, base_y + leg_len + int(H * 0.04)),
            fill=_shade(dress, 0.5),
        )

    # neck
    draw.rectangle((head_cx - head_r // 3, head_cy, head_cx + head_r // 3, top_y + 12),
                   fill=_shade(skin, 0.9))

    # arms — thin, hanging just outside the body, drawn before it so the
    # shoulder end disappears under the dress.
    arm_w = max(9, min(22, body_w // 14))
    arm_drop = rng.uniform(0.55, 0.95)
    hands = {}
    for side in (-1, 1):
        ax = cx + side * (body_w // 2 - arm_w)
        ay = top_y + int(body_h * 0.12)
        by = ay + int(body_h * arm_drop) + 24
        hands[side] = (ax, by)
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
    hair_r = int(head_r * rng.uniform(*prof["hair_r"]))
    draw.ellipse(
        (head_cx - hair_r, head_cy - hair_r, head_cx + hair_r, head_cy + int(hair_r * 0.5)),
        fill=hair,
    )
    if rng.random() < 0.35:  # curlers / bun
        for _ in range(rng.randint(3, 7)):
            bx = head_cx + rng.randint(-hair_r, hair_r)
            by = head_cy - hair_r + rng.randint(-10, 10)
            br = rng.randint(6, 14)
            draw.ellipse((bx - br, by - br, bx + br, by + br), fill=_shade(hair, 1.25))

    # head
    draw.ellipse((head_cx - head_r, head_cy - head_r, head_cx + head_r, head_cy + head_r), fill=skin)

    # sclera only — _draw_face places the pupils (feature-aware)
    eye_dx = int(head_r * 0.42)
    eye_er = max(5, int(head_r * rng.uniform(0.16, 0.26)))
    eye_ey = head_cy - int(head_r * 0.12)
    for side in (-1, 1):
        ex = head_cx + side * eye_dx
        draw.ellipse((ex - eye_er, eye_ey - eye_er, ex + eye_er, eye_ey + eye_er), fill=(250, 250, 250))

    # mouth geometry (the drawing itself is feature-aware in _draw_face)
    my = head_cy + int(head_r * 0.38)
    mw = int(head_r * rng.uniform(0.4, 0.75))
    mouth_mode = rng.random()

    p = {
        "cx": cx, "base_y": base_y, "top_y": top_y,
        "body_w": body_w, "body_h": body_h,
        "head_r": head_r, "head_cx": head_cx, "head_cy": head_cy,
        "head_top": head_cy - head_r, "head_bottom": head_cy + head_r,
        "skin": skin, "dress": dress, "hair": hair,
        "eye_dx": eye_dx, "eye_ey": eye_ey, "eye_er": eye_er,
        "mouth_my": my, "mouth_mw": mw, "mouth_mode": mouth_mode,
        "hand_r": hands[1], "hand_l": hands[-1],
        "features": prof["features"],
    }

    if rng.random() < 0.4:  # earrings
        for side in (-1, 1):
            ex = head_cx + side * head_r
            draw.ellipse((ex - 6, head_cy + 4, ex + 6, head_cy + 16), fill=(240, 200, 60))
    if rng.random() < 0.25:  # cigarette
        draw.line((head_cx + mw, my, head_cx + mw + 34, my - 6), fill=(240, 240, 235), width=5)
        draw.ellipse((head_cx + mw + 30, my - 12, head_cx + mw + 40, my - 2), fill=(240, 120, 40))

    _draw_face(draw, rng, p)


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


def render_joke_image(joke_text: str, category: str | None = None,
                      *, seed: int | None = None) -> io.BytesIO:
    """Render the joke as a framed portrait PNG. Returns a rewound BytesIO.

    Pass the joke's category and the portrait is drawn to match the bit —
    "fat" comes out wide, "tall" comes out long, "nasty" comes out green and
    buzzing. Unknown categories are ignored and the figure rolls its
    proportions the base way.
    """
    rng = random.Random(seed)  # None -> OS entropy, unique per call
    palette = rng.choice(_PALETTES)
    top, bottom, dress, skin, hair = palette

    img = _gradient(top, bottom)
    draw = ImageDraw.Draw(img)
    rng.choice(_BACKGROUNDS)(draw, rng, dress)
    _figure(draw, rng, palette, category)

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


if __name__ == "__main__":  # python3 -m yomama_art -> category-matched sample to /tmp
    import yomama
    name, joke = yomama.joke_with_category()
    out = "/tmp/yomama_sample.png"
    with open(out, "wb") as f:
        f.write(render_joke_image(joke, name).read())
    print(out, f"({name})")
