"""Procedural trading-card renderer for lootdrop.

Each call to render_card() produces a fresh, unique PNG. Six art styles are
randomly selected per drop; the rarity color tints the art and the frame.
Mythic gets an extra chromatic shimmer pass so it visually outranks Legendary.

Run this module directly to render a sample card to /tmp:
    python3 -m cogs.lootdrop_card
"""
import io
import math
import os
import random
from datetime import datetime, timezone
from typing import Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont


CARD_W = 420
CARD_H = 588

ART_X = 24
ART_Y = 80
ART_W = CARD_W - 48      # 372
ART_H = 320

# Render the procedural art at low res then upscale — pure-Python pixel loops
# at full size are too slow for a Discord interaction.
ART_SCALE = 4
ART_LOW_W = ART_W // ART_SCALE
ART_LOW_H = ART_H // ART_SCALE

_FONT_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)


def _font(size: int):
    for p in _FONT_PATHS:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _color_tuple(c) -> Tuple[int, int, int]:
    """Accept a discord.Color, an int, or a tuple. Return (r, g, b)."""
    if isinstance(c, tuple):
        return (int(c[0]), int(c[1]), int(c[2]))
    val = getattr(c, "value", c)
    val = int(val)
    return ((val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF)


def _clamp(n: int) -> int:
    return 0 if n < 0 else 255 if n > 255 else n


# ---------- Procedural art styles (each operates on a small ART_LOW canvas) ----------

def _art_static(rng: random.Random, color):
    """Pure RGB noise tinted toward the rarity color."""
    img = Image.new("RGB", (ART_LOW_W, ART_LOW_H))
    px = img.load()
    r0, g0, b0 = color
    for y in range(ART_LOW_H):
        for x in range(ART_LOW_W):
            v = rng.randint(60, 255)
            j = rng.randint(-25, 25)
            px[x, y] = (
                _clamp(r0 * v // 255 + j),
                _clamp(g0 * v // 255 + j),
                _clamp(b0 * v // 255 + j),
            )
    return img


def _art_plasma(rng: random.Random, color):
    """Layered sin-wave plasma field."""
    img = Image.new("RGB", (ART_LOW_W, ART_LOW_H))
    px = img.load()
    r0, g0, b0 = color
    px_off = rng.uniform(0, 50)
    py_off = rng.uniform(0, 50)
    freq1 = rng.uniform(0.08, 0.18)
    freq2 = rng.uniform(0.05, 0.12)
    for y in range(ART_LOW_H):
        for x in range(ART_LOW_W):
            v = (
                math.sin((x + px_off) * freq1)
                + math.cos((y + py_off) * freq2)
                + math.sin(((x + y) * freq1 * 0.6) + px_off)
            ) / 3.0
            t = 0.35 + 0.65 * (v + 1) / 2
            px[x, y] = (
                _clamp(int(r0 * t)),
                _clamp(int(g0 * t)),
                _clamp(int(b0 * t)),
            )
    return img


def _art_voronoi(rng: random.Random, color):
    """Voronoi cells — each cell tinted with rarity + random accent."""
    img = Image.new("RGB", (ART_LOW_W, ART_LOW_H))
    px = img.load()
    r0, g0, b0 = color
    n_seeds = rng.randint(12, 24)
    seeds = [
        (
            rng.randint(0, ART_LOW_W),
            rng.randint(0, ART_LOW_H),
            rng.randint(40, 220),
            rng.randint(40, 220),
            rng.randint(40, 220),
        )
        for _ in range(n_seeds)
    ]
    for y in range(ART_LOW_H):
        for x in range(ART_LOW_W):
            best_d = 1 << 30
            best = (0, 0, 0)
            for sx, sy, sr, sg, sb in seeds:
                d = (sx - x) * (sx - x) + (sy - y) * (sy - y)
                if d < best_d:
                    best_d = d
                    best = (sr, sg, sb)
            sr, sg, sb = best
            px[x, y] = ((r0 + sr) // 2, (g0 + sg) // 2, (b0 + sb) // 2)
    return img


def _art_starfield(rng: random.Random, color):
    """Dark void with bright tier-tinted stars."""
    r0, g0, b0 = color
    img = Image.new("RGB", (ART_LOW_W, ART_LOW_H))
    px = img.load()
    for y in range(ART_LOW_H):
        for x in range(ART_LOW_W):
            v = rng.randint(2, 18)
            px[x, y] = (
                _clamp(r0 // 10 + v),
                _clamp(g0 // 10 + v),
                _clamp(b0 // 10 + v),
            )
    draw = ImageDraw.Draw(img)
    for _ in range(rng.randint(50, 110)):
        x = rng.randint(0, ART_LOW_W - 1)
        y = rng.randint(0, ART_LOW_H - 1)
        bright = rng.randint(180, 255)
        draw.point((x, y), fill=(bright, bright, bright))
        if rng.random() < 0.15:
            # bigger anchor star
            draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill=(bright, bright, bright))
    return img


def _art_bubbles(rng: random.Random, color):
    """Overlapping translucent bubbles in tier color + random accents."""
    r0, g0, b0 = color
    base = (max(0, r0 // 4), max(0, g0 // 4), max(0, b0 // 4))
    img = Image.new("RGBA", (ART_LOW_W, ART_LOW_H), base + (255,))
    overlay = Image.new("RGBA", (ART_LOW_W, ART_LOW_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for _ in range(rng.randint(20, 40)):
        cx = rng.randint(-10, ART_LOW_W + 10)
        cy = rng.randint(-10, ART_LOW_H + 10)
        radius = rng.randint(8, 28)
        a = rng.randint(60, 150)
        if rng.random() < 0.25:
            cr, cg, cb = rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255)
        else:
            cr, cg, cb = r0, g0, b0
        draw.ellipse(
            (cx - radius, cy - radius, cx + radius, cy + radius),
            fill=(cr, cg, cb, a),
        )
    out = Image.alpha_composite(img, overlay)
    return out.convert("RGB")


def _art_grid(rng: random.Random, color):
    """Pixel grid: each cell a random tier-tinted shade."""
    r0, g0, b0 = color
    img = Image.new("RGB", (ART_LOW_W, ART_LOW_H))
    px = img.load()
    cell = rng.choice([3, 4, 5, 6])
    for cy in range(0, ART_LOW_H, cell):
        for cx in range(0, ART_LOW_W, cell):
            t = rng.uniform(0.2, 1.0)
            j = rng.randint(-20, 20)
            r = _clamp(int(r0 * t) + j)
            g = _clamp(int(g0 * t) + j)
            b = _clamp(int(b0 * t) + j)
            for yy in range(cy, min(cy + cell, ART_LOW_H)):
                for xx in range(cx, min(cx + cell, ART_LOW_W)):
                    px[xx, yy] = (r, g, b)
    return img


_ART_STYLES = (
    ("static",    _art_static),
    ("plasma",    _art_plasma),
    ("voronoi",   _art_voronoi),
    ("starfield", _art_starfield),
    ("bubbles",   _art_bubbles),
    ("grid",      _art_grid),
)


# ---------- BLBot creature generator ----------
# Procedural cute robo-creatures composited on top of the background art.
# Build a binary silhouette mask from primitive shapes, derive the outline ring
# via dilation, then fill body color + paint details (eyes / mouth / belly /
# spots) on top. Everything is rendered at 2× and downsampled for clean edges.

_NAME_TITLES = (
    "Sir", "Lady", "Lord", "Madam", "Captain", "Doctor", "Professor", "King",
    "Queen", "Baron", "Duchess", "Saint", "Master", "Empress", "Chief", "Prince",
    "Mayor", "Sergeant", "Admiral", "Reverend", "Colonel", "Sister", "Brother",
    "Uncle", "Auntie", "Officer", "Jester", "Wizard", "General", "Cardinal",
    "Astro-", "Mecha-", "Lil",
)

_NAME_HEADS = (
    "Zap", "Boop", "Glitch", "Pix", "Blip", "Zorp", "Mecha", "Quib", "Snib",
    "Glow", "Flux", "Twit", "Whirl", "Buzz", "Crank", "Skib", "Vex", "Doink",
    "Mox", "Plip", "Snorp", "Quark", "Wisp", "Yip", "Snoot", "Glim", "Bork",
    "Drib", "Fizz", "Zog", "Nyx", "Pog", "Lump", "Goo", "Tato", "Beep", "Wuv",
    "Snug", "Rumb", "Plonk", "Chomp", "Wibb", "Floof", "Klonk", "Sploot",
    "Bink", "Pluf", "Zib", "Twink", "Frob", "Hork", "Smibble", "Zarg", "Whiff",
    "Plink", "Yobb", "Gronk", "Doof", "Chub", "Snart", "Glob", "Kloop", "Mooch",
    "Vop", "Squee", "Zeb", "Hop", "Chibb", "Worp", "Nizz", "Tonk", "Jib",
    "Glunk", "Snip", "Plorp", "Krill", "Munt", "Wug", "Tobby", "Sneezle",
    "Quip", "Frund", "Pob", "Klap", "Mick", "Ploop", "Snorf", "Thrim", "Burb",
    "Klink", "Vorp", "Rud", "Snopp", "Borb", "Snoog", "Yom", "Thwop", "Flim",
    "Doot", "Glirp", "Chiff", "Pwoo", "Snog", "Tugg", "Vroop", "Mep", "Twigg",
    "Hib", "Quink", "Slop", "Flomp", "Nork", "Wabble", "Skritch", "Glurb",
    "Boff", "Snerk", "Yeep", "Smol", "Snizz", "Wonk", "Flarp", "Bloop", "Murr",
    "Skrunkle", "Borp", "Nug", "Plib", "Frell", "Gleep", "Yoik", "Quirk",
    "Spork", "Knub", "Wog", "Smerg", "Fwip", "Zonk", "Brub", "Sneep", "Squiff",
    "Plox", "Mibb", "Crumb", "Mochi", "Boba", "Astro", "Cyber", "Plasma",
    "Photon", "Neon", "Vector", "Quantum", "Sussy", "Chonk", "Yeet", "Glomp",
    "Bonk", "Sploink", "Doogle", "Pancake", "Bagel",
)

_NAME_MIDDLES = (
    "a", "o", "i", "u", "y", "ee", "oo", "ar", "ix", "el", "il", "om", "an",
    "iz", "imo", "ito", "umo", "aw", "ow", "ip", "ade", "uri", "obo", "imi",
    "ick", "ub", "ish",
)

_NAME_TAILS = (
    "tron", "bot", "lord", "max", "kin", "dex", "ling", "or", "wick", "drift",
    "punk", "byte", "nix", "wing", "tail", "bub", "ette", "zilla", "klink",
    "mite", "core", "spark", "claw", "hoot", "puff", "wuzz", "nub", "doof",
    "snorp", "boop", "wig", "saur", "zoid", "pus", "munch", "chu", "mon",
    "blob", "noid", "pop", "oid", "bug", "fang", "pup", "beast", "fluff",
    "jelly", "blast", "kraken", "spike", "shroom", "dile", "rex", "basher",
    "smasher", "biter", "glow", "gnoma", "lizard", "frog", "owl", "fox", "wolf",
    "drake", "naut", "scape", "shock", "snap", "doodle", "fizzle", "nibbler",
    "glitter", "ranger", "gobbler", "scratcher", "smoocher", "schnauzer",
    "biscuit", "muffin", "dollop", "trodian", "gloop", "stomper", "cruncher",
    "gulper", "winger", "gobble", "boomer", "blammer", "lopper", "gusher",
    "kins", "flap", "puffin", "finger", "kit", "wraith", "pyre", "glug", "yote",
    "stomp", "smush", "sticker", "stinger", "kuckle", "doinker", "pump",
    "marauder", "burst", "hammer", "scoot", "pancake", "woof", "marvel",
    "wizard", "baron", "scientist", "mancer", "smith", "griff", "blat", "cake",
    "roll", "snurfle", "glomp", "snake", "drone", "smackle", "cogger", "wonker",
    "throb", "jangle", "twink", "borp", "snorp", "whomp", "jimbo", "munch",
)

_NAME_SUFFIXES = (
    "the Whimsical", "the Mighty", "the Glitchy", "the Soft", "Mk. II",
    "Mk. III", "Mk. V", "Mk. VII", "Mk. IX", "v2.0", "v3.14", "v9.9", "the III",
    "the IV", "the V", "the VIII", "Jr.", "Sr.", "Esq.", "of the West",
    "of the Stars", "of Crisp", "the Goob", "the Smol", "the Loud",
    "the Sleepy", "X-1", "X-99", "the Boopable", "Prime", "Beta", "Alpha",
    "Omega", "Maximum", "Plus", "the Untamed", "the Cursed", "the Beloved",
    "the Bonkable", "the Honkable", "of the Vault", "of the Void",
    "Supreme", "Deluxe", "the Spicy", "the Crispy", "the Dank",
)


def _blbot_name(rng: random.Random) -> str:
    parts = []
    if rng.random() < 0.18:
        title = rng.choice(_NAME_TITLES)
        # Hyphen-prefix titles ("Mecha-") attach directly; others have a space.
        parts.append(title if title.endswith("-") else title + " ")
    head = rng.choice(_NAME_HEADS)
    if rng.random() < 0.35:
        head = head + rng.choice(_NAME_MIDDLES)
    parts.append(head + rng.choice(_NAME_TAILS))
    if rng.random() < 0.20:
        parts.append(" " + rng.choice(_NAME_SUFFIXES))
    if rng.random() < 0.10:
        parts.append(f" #{rng.randint(1, 999):03d}")
    return "".join(parts)


def _draw_sigil(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int, fill_rgb):
    """Diamond gem with inner highlight, used in card header."""
    pts = [(cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy)]
    draw.polygon(pts, fill=fill_rgb, outline=(20, 20, 30))
    inner = max(2, size // 2)
    hl = (
        _clamp(fill_rgb[0] + 80),
        _clamp(fill_rgb[1] + 80),
        _clamp(fill_rgb[2] + 80),
    )
    draw.polygon(
        [(cx, cy - inner), (cx + inner // 2, cy - inner // 3), (cx, cy), (cx - inner // 2, cy - inner // 3)],
        fill=hl,
    )


def _blbot_palette(rng: random.Random, color):
    r0, g0, b0 = color
    sat = rng.uniform(0.85, 1.05)
    body = (_clamp(int(r0 * sat)), _clamp(int(g0 * sat)), _clamp(int(b0 * sat)))
    belly = (_clamp(r0 + 80), _clamp(g0 + 80), _clamp(b0 + 80))
    outline = (max(8, r0 // 3), max(8, g0 // 3), max(8, b0 // 3))
    accent = rng.choice([
        (255, 230, 120),
        (255, 130, 150),
        (140, 230, 255),
        (180, 255, 160),
        (_clamp(255 - r0), _clamp(255 - g0), _clamp(255 - b0)),
    ])
    return {"body": body, "belly": belly, "outline": outline, "accent": accent}


_CHAOTIC_SHAPES = ("wrench", "stickfig", "lobster", "piston", "horseshoe", "mushroom", "pickle")


def _chaotic_silhouette(md: ImageDraw.ImageDraw, rng: random.Random, sw: int, sh: int):
    """Common-tier 'sentient junk drawer' silhouettes — wrenches, lobsters, pistons, etc.
    Returns (head_cx, head_cy, head_r, body_w, body_h, cx, cy) like _blbot_silhouette."""
    cx = sw // 2
    cy = sh // 2
    shape = rng.choice(_CHAOTIC_SHAPES)

    if shape == "wrench":
        head_r = rng.randint(int(sw * 0.16), int(sw * 0.22))
        head_cy = int(sh * 0.30)
        handle_w = rng.randint(sw // 10, sw // 7)
        md.ellipse((cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r), fill=255)
        hole_r = head_r * 5 // 10
        md.ellipse((cx - hole_r, head_cy - hole_r, cx + hole_r, head_cy + hole_r), fill=0)
        handle_top = head_cy + head_r - 5
        handle_bot = int(sh * 0.85)
        md.rounded_rectangle(
            (cx - handle_w // 2, handle_top, cx + handle_w // 2, handle_bot),
            radius=handle_w // 2, fill=255,
        )
        jaw_r = head_r * 4 // 5
        jaw_cy = handle_bot - jaw_r // 3
        md.ellipse((cx - jaw_r, jaw_cy - jaw_r, cx + jaw_r, jaw_cy + jaw_r), fill=255)
        md.polygon(
            [(cx - jaw_r * 7 // 10, jaw_cy + jaw_r),
             (cx + jaw_r * 7 // 10, jaw_cy + jaw_r),
             (cx + jaw_r // 5, jaw_cy + 5),
             (cx - jaw_r // 5, jaw_cy + 5)],
            fill=0,
        )
        return cx, head_cy - head_r // 3, max(8, hole_r - 6), head_r * 2, int(sh * 0.65), cx, int(sh * 0.55)

    if shape == "stickfig":
        head_r = rng.randint(int(sw * 0.10), int(sw * 0.14))
        head_cy = int(sh * 0.22)
        line_w = rng.randint(10, 16)
        md.ellipse((cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r), fill=255)
        body_top = head_cy + head_r
        body_bot = int(sh * 0.72)
        md.line([(cx, body_top), (cx, body_bot)], fill=255, width=line_w)
        arm_y = body_top + (body_bot - body_top) // 3
        md.line([(cx - sw // 4, arm_y), (cx + sw // 4, arm_y)], fill=255, width=line_w)
        md.line([(cx, body_bot), (cx - sw // 5, int(sh * 0.92))], fill=255, width=line_w)
        md.line([(cx, body_bot), (cx + sw // 5, int(sh * 0.92))], fill=255, width=line_w)
        return cx, head_cy, head_r * 4 // 5, sw // 2, int(sh * 0.7), cx, int(sh * 0.55)

    if shape == "lobster":
        body_w = rng.randint(int(sw * 0.32), int(sw * 0.40))
        body_h = rng.randint(int(sh * 0.30), int(sh * 0.38))
        body_cy = int(sh * 0.48)
        md.ellipse(
            (cx - body_w // 2, body_cy - body_h // 2, cx + body_w // 2, body_cy + body_h // 2),
            fill=255,
        )
        for i in range(3):
            seg_y = body_cy + body_h // 2 + i * (body_h // 6)
            seg_w = body_w * (9 - i * 2) // 10
            md.ellipse(
                (cx - seg_w // 2, seg_y - body_h // 10, cx + seg_w // 2, seg_y + body_h // 6),
                fill=255,
            )
        claw_r = body_h * 4 // 10
        for side in (-1, 1):
            ccx = cx + side * (body_w // 2 + claw_r // 2)
            ccy = body_cy - body_h // 4
            md.ellipse(
                (ccx - claw_r * 4 // 5, ccy - claw_r * 3 // 5,
                 ccx + claw_r * 4 // 5, ccy + claw_r * 3 // 5),
                fill=255,
            )
            md.polygon(
                [(ccx + side * claw_r * 4 // 5, ccy - claw_r * 3 // 10),
                 (ccx - side * claw_r * 2 // 5, ccy),
                 (ccx + side * claw_r * 4 // 5, ccy + claw_r * 3 // 10)],
                fill=0,
            )
        for side in (-1, 1):
            md.line(
                [(cx + side * body_w // 4, body_cy - body_h // 2),
                 (cx + side * body_w // 2, body_cy - body_h * 3 // 2)],
                fill=255, width=6,
            )
        return cx, body_cy - body_h // 5, body_h // 4, body_w + claw_r * 2, int(body_h * 2.4), cx, body_cy

    if shape == "piston":
        cyl_w = rng.randint(int(sw * 0.18), int(sw * 0.24))
        cyl_h = rng.randint(int(sh * 0.30), int(sh * 0.38))
        cyl_cy = int(sh * 0.55)
        md.rounded_rectangle(
            (cx - cyl_w // 2, cyl_cy - cyl_h // 2, cx + cyl_w // 2, cyl_cy + cyl_h // 2),
            radius=cyl_w // 4, fill=255,
        )
        cap_w = cyl_w * 13 // 10
        cap_h = max(10, cyl_h // 8)
        cap_y = cyl_cy - cyl_h // 2
        md.rounded_rectangle(
            (cx - cap_w // 2, cap_y - cap_h, cx + cap_w // 2, cap_y),
            radius=cap_h // 3, fill=255,
        )
        rod_w = cyl_w // 4
        rod_h = cyl_h // 3
        md.rectangle(
            (cx - rod_w // 2, cap_y - cap_h - rod_h, cx + rod_w // 2, cap_y - cap_h),
            fill=255,
        )
        stub_w = cyl_w // 3
        md.rectangle(
            (cx - stub_w // 2, cap_y - cap_h - rod_h - stub_w // 3,
             cx + stub_w // 2, cap_y - cap_h - rod_h),
            fill=255,
        )
        return cx, cyl_cy, cyl_w * 2 // 5, cap_w, cyl_h + rod_h + cap_h, cx, cyl_cy

    if shape == "horseshoe":
        outer_r = rng.randint(int(sw * 0.26), int(sw * 0.32))
        inner_r = outer_r * 6 // 10
        center_cy = int(sh * 0.50)
        md.ellipse(
            (cx - outer_r, center_cy - outer_r, cx + outer_r, center_cy + outer_r),
            fill=255,
        )
        md.ellipse(
            (cx - inner_r, center_cy - inner_r, cx + inner_r, center_cy + inner_r),
            fill=0,
        )
        md.rectangle(
            (cx - outer_r - 4, center_cy + inner_r // 2,
             cx + outer_r + 4, center_cy + outer_r + 10),
            fill=0,
        )
        stud_r = max(6, (outer_r - inner_r) // 3)
        leg_y = center_cy + inner_r * 3 // 10
        for side in (-1, 1):
            scx = cx + side * (outer_r + inner_r) // 2
            md.ellipse((scx - stud_r, leg_y - stud_r, scx + stud_r, leg_y + stud_r), fill=255)
        return cx, center_cy - outer_r // 2, max(8, (outer_r - inner_r) // 2), outer_r * 2, outer_r * 2, cx, center_cy

    if shape == "mushroom":
        cap_r = rng.randint(int(sw * 0.22), int(sw * 0.30))
        cap_cy = int(sh * 0.40)
        stem_w = cap_r * 6 // 10
        stem_h = rng.randint(int(sh * 0.18), int(sh * 0.28))
        md.pieslice(
            (cx - cap_r, cap_cy - cap_r, cx + cap_r, cap_cy + cap_r),
            start=180, end=360, fill=255,
        )
        md.rectangle((cx - cap_r, cap_cy - 4, cx + cap_r, cap_cy + 8), fill=255)
        stem_top = cap_cy + 8
        md.rounded_rectangle(
            (cx - stem_w // 2, stem_top, cx + stem_w // 2, stem_top + stem_h),
            radius=stem_w // 4, fill=255,
        )
        return cx, stem_top + stem_h // 2, stem_w // 3, cap_r * 2, cap_r + stem_h, cx, cap_cy + stem_h // 2

    # pickle
    body_w = rng.randint(int(sw * 0.26), int(sw * 0.34))
    body_h = rng.randint(int(sh * 0.55), int(sh * 0.68))
    body_cy = int(sh * 0.55)
    md.ellipse(
        (cx - body_w // 2, body_cy - body_h // 2, cx + body_w // 2, body_cy + body_h // 2),
        fill=255,
    )
    for _ in range(rng.randint(5, 9)):
        ang = rng.uniform(0, 2 * math.pi)
        bx = cx + int(math.cos(ang) * body_w * 0.45)
        by = body_cy + int(math.sin(ang) * body_h * 0.45)
        br = rng.randint(8, 18)
        md.ellipse((bx - br, by - br, bx + br, by + br), fill=255)
    stem_w = body_w // 5
    md.rounded_rectangle(
        (cx - stem_w // 2, body_cy - body_h // 2 - body_h // 12,
         cx + stem_w // 2, body_cy - body_h // 2 + 5),
        radius=stem_w // 3, fill=255,
    )
    return cx, body_cy - body_h // 4, body_w // 4, body_w, body_h, cx, body_cy


def _blbot_silhouette(md: ImageDraw.ImageDraw, rng: random.Random, sw: int, sh: int):
    """Draw the creature silhouette onto mask `md` (fill=255). Return head (cx, cy, r)."""
    cx = sw // 2 + rng.randint(-sw // 30, sw // 30)
    cy = int(sh * 0.55)
    body_w = rng.randint(int(sw * 0.45), int(sw * 0.62))
    body_h = rng.randint(int(sh * 0.50), int(sh * 0.68))

    shape = rng.choice(["round", "egg", "pear", "stacked", "blob", "boxy"])

    if shape == "round":
        r = min(body_w, body_h) // 2
        md.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
        head = (cx, cy - r // 3, r * 4 // 5)
    elif shape == "egg":
        md.ellipse(
            (cx - body_w // 2, cy - body_h // 2, cx + body_w // 2, cy + body_h // 2),
            fill=255,
        )
        head = (cx, cy - body_h // 5, body_w // 2 - 12)
    elif shape == "pear":
        bot_h = body_h * 5 // 8
        bot_cy = cy + body_h // 6
        md.ellipse(
            (cx - body_w // 2, bot_cy - bot_h // 2, cx + body_w // 2, bot_cy + bot_h // 2),
            fill=255,
        )
        top_r = body_w * 7 // 20
        top_cy = cy - body_h // 5
        md.ellipse((cx - top_r, top_cy - top_r, cx + top_r, top_cy + top_r), fill=255)
        head = (cx, top_cy, top_r)
    elif shape == "stacked":
        body_rw = body_w * 5 // 12
        body_rh = body_h * 7 // 20
        body_cy = cy + body_h // 4
        md.ellipse(
            (cx - body_rw, body_cy - body_rh, cx + body_rw, body_cy + body_rh),
            fill=255,
        )
        head_r = body_w * 3 // 10
        head_cy = cy - body_h // 5
        md.ellipse(
            (cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r),
            fill=255,
        )
        ny0 = head_cy + head_r - 6
        ny1 = body_cy - body_rh + 6
        md.rectangle(
            (cx - head_r // 3, min(ny0, ny1), cx + head_r // 3, max(ny0, ny1) + 1),
            fill=255,
        )
        head = (cx, head_cy, head_r)
    elif shape == "boxy":
        rect = (cx - body_w // 2, cy - body_h // 2, cx + body_w // 2, cy + body_h // 2)
        radius = min(body_w, body_h) // 5
        md.rounded_rectangle(rect, radius=radius, fill=255)
        head = (cx, cy - body_h // 5, body_w * 2 // 5)
    else:  # blob
        for _ in range(rng.randint(5, 8)):
            ox = rng.randint(-body_w // 5, body_w // 5)
            oy = rng.randint(-body_h // 5, body_h // 5)
            er = rng.randint(body_w // 5, body_w // 3)
            md.ellipse((cx + ox - er, cy + oy - er, cx + ox + er, cy + oy + er), fill=255)
        head = (cx, cy - body_h // 8, body_w * 2 // 5)

    head_cx, head_cy, head_r = head

    # Top accessory
    top = rng.choice(["none", "antennae", "ears_round", "ears_pointed", "horn", "fin", "tuft"])
    if top == "antennae":
        for side in (-1, 1):
            bx = head_cx + side * head_r // 3
            by = head_cy - head_r
            tx = bx + side * rng.randint(-15, 25)
            ty = by - rng.randint(50, 80)
            md.line([(bx, by), (tx, ty)], fill=255, width=10)
            tr = rng.randint(12, 18)
            md.ellipse((tx - tr, ty - tr, tx + tr, ty + tr), fill=255)
    elif top == "ears_round":
        er = rng.randint(20, 32)
        for side in (-1, 1):
            ex = head_cx + side * head_r * 7 // 10
            ey = head_cy - head_r * 7 // 10
            md.ellipse((ex - er, ey - er, ex + er, ey + er), fill=255)
    elif top == "ears_pointed":
        for side in (-1, 1):
            bcx = head_cx + side * head_r * 7 // 10
            bcy = head_cy - head_r * 7 // 10
            md.polygon(
                [(bcx - 18, bcy + 5), (bcx + 18, bcy + 5), (bcx + side * 20, bcy - 50)],
                fill=255,
            )
    elif top == "horn":
        hx = head_cx + rng.randint(-10, 10)
        hy = head_cy - head_r
        md.polygon([(hx - 16, hy + 10), (hx + 16, hy + 10), (hx, hy - 50)], fill=255)
    elif top == "fin":
        fx = head_cx
        fy = head_cy - head_r
        for i in range(3):
            off = (i - 1) * 24
            h = 30 - abs(i - 1) * 8
            md.polygon(
                [(fx + off - 12, fy + 8), (fx + off + 12, fy + 8), (fx + off, fy - h)],
                fill=255,
            )
    elif top == "tuft":
        tx = head_cx + rng.randint(-10, 10)
        ty = head_cy - head_r
        md.polygon([(tx - 18, ty + 12), (tx + 22, ty + 8), (tx + 4, ty - 35)], fill=255)

    # Arms (stubby ovals on the sides)
    if rng.random() < 0.7:
        arm_y = cy + body_h // 8
        arm_off = body_w // 2 - 8
        arm_len = rng.randint(20, 38)
        arm_th = rng.randint(12, 20)
        for side in (-1, 1):
            ax = cx + side * arm_off
            md.ellipse((ax - arm_len, arm_y - arm_th, ax + arm_len, arm_y + arm_th), fill=255)

    # Feet
    if rng.random() < 0.85:
        feet_y = cy + body_h * 9 // 20
        foot_off = rng.randint(body_w // 6, body_w // 4)
        foot_w = rng.randint(20, 30)
        foot_h = rng.randint(10, 16)
        for side in (-1, 1):
            fx = cx + side * foot_off
            md.ellipse((fx - foot_w, feet_y - foot_h, fx + foot_w, feet_y + foot_h), fill=255)

    # Tail
    if rng.random() < 0.4:
        side = rng.choice([-1, 1])
        tbx = cx + side * body_w * 9 // 20
        tby = cy + body_h // 6
        segs = rng.randint(3, 6)
        for i in range(segs):
            t = i / max(1, segs - 1)
            tx = tbx + side * int(20 * t * 2 + i * 8)
            ty = tby - int(20 * t)
            tr = max(6, 14 - i * 2)
            md.ellipse((tx - tr, ty - tr, tx + tr, ty + tr), fill=255)

    return head_cx, head_cy, head_r, body_w, body_h, cx, cy


def _eye_layout(n: int, head_cx: int, eye_y: int, head_r: int, eye_size: int):
    """Return list of (x, y, size_scale) for each eye, arranged on the head."""
    if n == 1:
        return [(head_cx, eye_y, 1.4)]
    if n == 2:
        sp = head_r * 9 // 20
        return [(head_cx - sp, eye_y, 1.0), (head_cx + sp, eye_y, 1.0)]
    if n == 3:
        sp = head_r * 7 // 20
        return [
            (head_cx, eye_y - 12, 0.95),
            (head_cx - sp, eye_y + 10, 0.95),
            (head_cx + sp, eye_y + 10, 0.95),
        ]
    if n == 4:
        sp_x = head_r * 6 // 20
        sp_y = max(10, eye_size)
        return [
            (head_cx - sp_x, eye_y - sp_y, 0.85),
            (head_cx + sp_x, eye_y - sp_y, 0.85),
            (head_cx - sp_x, eye_y + sp_y, 0.85),
            (head_cx + sp_x, eye_y + sp_y, 0.85),
        ]
    # 5..7 eyes: arrange in an arc around head center, all on the upper face.
    pts = []
    span = math.radians(150)  # arc spread
    start = -math.pi / 2 - span / 2
    radius = head_r * 9 // 20
    for i in range(n):
        ang = start + span * (i / max(1, n - 1))
        ex = head_cx + int(math.cos(ang) * radius)
        ey = eye_y + int(math.sin(ang) * radius * 0.55) + 6
        pts.append((ex, ey, 0.78))
    return pts


def _draw_eye(dd: ImageDraw.ImageDraw, ex: int, ey: int, sz: int,
              outline_rgb, rng: random.Random):
    dd.ellipse(
        (ex - sz, ey - sz, ex + sz, ey + sz),
        fill=(250, 250, 255, 255), outline=outline_rgb + (255,), width=4,
    )
    psz = sz * 6 // 10
    pox = rng.randint(-sz // 4, sz // 4)
    poy = rng.randint(-sz // 5, sz // 5)
    dd.ellipse(
        (ex - psz + pox, ey - psz + poy, ex + psz + pox, ey + psz + poy),
        fill=(15, 15, 25, 255),
    )
    hl = max(2, sz // 4)
    hx = ex - sz // 3 + pox
    hy = ey - sz // 2 + poy
    dd.ellipse((hx, hy, hx + hl, hy + hl), fill=(255, 255, 255, 255))


def _render_blbot(rng: random.Random, color, art_size, *, chaotic: bool = False):
    """Render a procedural BLBot onto a transparent canvas matching art_size."""
    w, h = art_size
    ss = 2
    sw, sh = w * ss, h * ss

    palette = _blbot_palette(rng, color)

    mask = Image.new("L", (sw, sh), 0)
    md = ImageDraw.Draw(mask)
    silhouette_fn = _chaotic_silhouette if chaotic else _blbot_silhouette
    head_cx, head_cy, head_r, body_w, body_h, cx, cy = silhouette_fn(md, rng, sw, sh)

    # Outline ring = dilated mask − mask. MaxFilter kernel (2r+1) grows by r px.
    outline_r = 5
    dilated = mask.filter(ImageFilter.MaxFilter(outline_r * 2 + 1))

    canvas = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))

    # Soft drop shadow (behind the body) — grounds the creature and helps
    # high-tier creatures pop off same-color backgrounds.
    shadow_layer = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    shadow_y = cy + body_h * 9 // 20 + 14
    shadow_w = body_w * 3 // 4
    shadow_h = max(12, body_h // 12)
    ImageDraw.Draw(shadow_layer).ellipse(
        (cx - shadow_w // 2, shadow_y - shadow_h // 2,
         cx + shadow_w // 2, shadow_y + shadow_h // 2),
        fill=(0, 0, 0, 150),
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=10))
    canvas = Image.alpha_composite(canvas, shadow_layer)

    outline_layer = Image.new("RGBA", (sw, sh), palette["outline"] + (255,))
    canvas.paste(outline_layer, (0, 0), dilated)
    body_layer = Image.new("RGBA", (sw, sh), palette["body"] + (255,))
    canvas.paste(body_layer, (0, 0), mask)

    # Belly highlight, clipped to body silhouette (creatures only — objects
    # don't have bellies, and patterns would make them harder to read)
    if not chaotic and rng.random() < 0.7:
        belly_w = body_w * 2 // 5
        belly_h = body_h // 3
        bcy = cy + body_h // 5
        belly = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        ImageDraw.Draw(belly).ellipse(
            (cx - belly_w, bcy - belly_h, cx + belly_w, bcy + belly_h),
            fill=palette["belly"] + (255,),
        )
        belly.putalpha(ImageChops.multiply(belly.split()[3], mask))
        canvas = Image.alpha_composite(canvas, belly)

    # Spots or stripes pattern, clipped to body
    pattern = "none" if chaotic else rng.choice(["none", "none", "spots", "stripes"])
    if pattern == "spots":
        layer = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        for _ in range(rng.randint(3, 7)):
            spx = cx + rng.randint(-body_w // 3, body_w // 3)
            spy = cy + rng.randint(-body_h // 4, body_h // 3)
            spr = rng.randint(6, 14)
            ld.ellipse((spx - spr, spy - spr, spx + spr, spy + spr),
                       fill=palette["accent"] + (210,))
        layer.putalpha(ImageChops.multiply(layer.split()[3], mask))
        canvas = Image.alpha_composite(canvas, layer)
    elif pattern == "stripes":
        layer = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        sw_w = rng.randint(8, 14)
        for off in range(-sh, sw + sh, sw_w * 3):
            ld.line([(off, 0), (off + sh, sh)],
                    fill=palette["accent"] + (180,), width=sw_w)
        layer.putalpha(ImageChops.multiply(layer.split()[3], mask))
        canvas = Image.alpha_composite(canvas, layer)

    dd = ImageDraw.Draw(canvas)

    # Eyes — count 1..7, weighted toward 2 with rarer multi-eye variants.
    # Smaller eyes when there are more, so they all fit on the head.
    n_eyes = rng.choices(
        [1, 2, 3, 4, 5, 6, 7],
        weights=[6, 50, 18, 10, 6, 5, 5],
    )[0]
    base_eye = rng.randint(16, 26)
    eye_size = max(7, base_eye - max(0, (n_eyes - 2)) * 3)
    eye_y = head_cy - head_r // 8
    out_rgb = palette["outline"]
    eye_positions = _eye_layout(n_eyes, head_cx, eye_y, head_r, eye_size)
    for ex, ey, scale in eye_positions:
        _draw_eye(dd, ex, ey, max(6, int(eye_size * scale)), out_rgb, rng)

    # Mouth
    mouth_y = head_cy + head_r // 3
    mouth = rng.choice(["smile", "open", "neutral", "fang", "tongue"])
    out_rgba = palette["outline"] + (255,)
    if mouth == "smile":
        dd.arc((head_cx - 24, mouth_y - 14, head_cx + 24, mouth_y + 14),
               start=0, end=180, fill=out_rgba, width=5)
    elif mouth == "open":
        dd.ellipse((head_cx - 12, mouth_y - 5, head_cx + 12, mouth_y + 18),
                   fill=(60, 20, 30, 255), outline=out_rgba, width=4)
    elif mouth == "neutral":
        dd.line([(head_cx - 18, mouth_y), (head_cx + 18, mouth_y)],
                fill=out_rgba, width=5)
    elif mouth == "fang":
        dd.line([(head_cx - 16, mouth_y), (head_cx + 16, mouth_y)],
                fill=out_rgba, width=5)
        for fx in (-6, 6):
            dd.polygon(
                [(head_cx + fx - 4, mouth_y), (head_cx + fx + 4, mouth_y),
                 (head_cx + fx, mouth_y + 12)],
                fill=(255, 255, 255, 255), outline=out_rgba,
            )
    elif mouth == "tongue":
        dd.arc((head_cx - 22, mouth_y - 14, head_cx + 22, mouth_y + 14),
               start=0, end=180, fill=out_rgba, width=5)
        dd.ellipse((head_cx - 10, mouth_y + 4, head_cx + 10, mouth_y + 16),
                   fill=(255, 130, 160, 255), outline=out_rgba, width=2)

    # Cheek blush (skip on objects)
    if not chaotic and rng.random() < 0.5:
        blush_y = head_cy + head_r // 8
        blush_off = head_r * 3 // 5
        for side in (-1, 1):
            bx = head_cx + side * blush_off
            dd.ellipse((bx - 14, blush_y - 7, bx + 14, blush_y + 7),
                       fill=(255, 130, 150, 140))

    return canvas.resize((w, h), Image.LANCZOS)


# ---------- Top-level renderer ----------

def render_card(
    rarity_name: str,
    item_name: str,
    coins: int,
    color,
    flavor: str,
    *,
    is_mythic: bool = False,
    minted_by: str | None = None,
    minted_at: str | None = None,
) -> io.BytesIO:
    """Render a unique trading-card PNG and return as a BytesIO ready for upload."""
    rng = random.Random()  # OS-entropy seeded → unique per call
    rgb = _color_tuple(color)
    species_name = _blbot_name(rng)
    if minted_at is None:
        minted_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    style_name, style_fn = rng.choice(_ART_STYLES)
    art_low = style_fn(rng, rgb)

    # Smooth upscale, light blur — gives the art a painterly feel except for
    # 'static' (which we want to stay crunchy).
    art = art_low.resize((ART_W, ART_H), Image.BICUBIC)
    if style_name != "static":
        art = art.filter(ImageFilter.GaussianBlur(radius=0.8))

    # BLBot creature on top of the habitat background. Common-tier rolls a
    # "sentient junk drawer" — wrench, lobster, piston, etc. — instead of a
    # cute creature.
    blbot = _render_blbot(rng, rgb, (ART_W, ART_H), chaotic=(rarity_name == "Common"))
    art = Image.alpha_composite(art.convert("RGBA"), blbot).convert("RGB")

    # Sparkle overlay — denser for higher tiers
    sparkle_count = {
        "Common": 6, "Uncommon": 12, "Rare": 24,
        "Epic": 48, "Legendary": 80, "Mythic": 140,
    }.get(rarity_name, 12)
    sparkles = Image.new("RGBA", (ART_W, ART_H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sparkles)
    for _ in range(sparkle_count):
        x = rng.randint(0, ART_W - 1)
        y = rng.randint(0, ART_H - 1)
        s = rng.choice([1, 1, 2, 2, 3])
        a = rng.randint(120, 230)
        sd.ellipse((x - s, y - s, x + s, y + s), fill=(255, 255, 255, a))
    art = Image.alpha_composite(art.convert("RGBA"), sparkles).convert("RGB")

    # Mythic chromatic shimmer — rainbow diagonal stripes at low alpha
    if is_mythic:
        shimmer = Image.new("RGBA", (ART_W, ART_H), (0, 0, 0, 0))
        sh_draw = ImageDraw.Draw(shimmer)
        for i, hue_rgb in enumerate([
            (255, 80, 80), (255, 180, 60), (255, 240, 70),
            (90, 220, 90), (90, 180, 240), (180, 120, 240),
        ]):
            offset = rng.randint(-20, 20)
            for d in range(-ART_H, ART_W, 24):
                sh_draw.line(
                    (d + i * 4 + offset, 0, d + i * 4 + offset + ART_H, ART_H),
                    fill=hue_rgb + (40,),
                    width=4,
                )
        art = Image.alpha_composite(art.convert("RGBA"), shimmer).convert("RGB")

    # ---- TCG-style overlays on the art panel ----
    art_rgba = art.convert("RGBA")
    badges = Image.new("RGBA", (ART_W, ART_H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(badges)

    # Top-left: species name badge — shrink font if a long compound name would
    # otherwise overflow the art panel.
    sp_pad_x, sp_pad_y = 9, 4
    sp_font = _font(14)
    bbox = bd.textbbox((0, 0), species_name, font=sp_font)
    if bbox[2] - bbox[0] > ART_W - 26:
        sp_font = _font(11)
        bbox = bd.textbbox((0, 0), species_name, font=sp_font)
    sp_tw = bbox[2] - bbox[0]
    sp_th = bbox[3] - bbox[1]
    sp_box = (8, 8, 8 + sp_tw + sp_pad_x * 2, 8 + sp_th + sp_pad_y * 2 + 2)
    bd.rounded_rectangle(sp_box, radius=6, fill=(0, 0, 0, 190), outline=rgb + (255,), width=2)
    bd.text((sp_box[0] + sp_pad_x, sp_box[1] + sp_pad_y - 1),
            species_name, font=sp_font, fill=(255, 255, 255, 255))

    art = Image.alpha_composite(art_rgba, badges).convert("RGB")

    # ---- Compose the card ----
    card = Image.new("RGB", (CARD_W, CARD_H), (15, 15, 22))
    draw = ImageDraw.Draw(card)

    # Outer + inner frame
    draw.rectangle((4, 4, CARD_W - 5, CARD_H - 5), outline=rgb, width=3)
    draw.rectangle((10, 10, CARD_W - 11, CARD_H - 11), outline=(60, 60, 70), width=1)

    # Header strip — drawn rarity sigils flanking the label (PIL-rendered fonts
    # can't display color emoji glyphs, which is why the old emoji-based header
    # showed tofu boxes).
    header_font = _font(30)
    label = rarity_name.upper()
    header_y = 26
    bbox = draw.textbbox((0, 0), label, font=header_font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    text_x = (CARD_W - tw) // 2
    draw.text((text_x, header_y), label, font=header_font, fill=rgb)
    sigil_y = header_y + th // 2 + 2
    sigil_size = 10
    _draw_sigil(draw, text_x - 24, sigil_y, sigil_size, rgb)
    _draw_sigil(draw, text_x + tw + 24, sigil_y, sigil_size, rgb)

    # Art panel + frame
    card.paste(art, (ART_X, ART_Y))
    draw.rectangle(
        (ART_X - 2, ART_Y - 2, ART_X + ART_W + 1, ART_Y + ART_H + 1),
        outline=rgb,
        width=2,
    )

    # Item name (wrap up to 2 lines)
    name_font = _font(20)
    name_y = ART_Y + ART_H + 18
    for line in _wrap(item_name, name_font, draw, CARD_W - 48, max_lines=2):
        bbox = draw.textbbox((0, 0), line, font=name_font)
        tw = bbox[2] - bbox[0]
        draw.text(((CARD_W - tw) // 2, name_y), line, font=name_font, fill=(240, 240, 240))
        name_y += 26

    # Value bar
    val_y = max(name_y + 4, ART_Y + ART_H + 70)
    draw.rectangle((24, val_y, CARD_W - 24, val_y + 42), fill=(28, 28, 36), outline=rgb, width=2)
    val_font = _font(22)
    val_text = f"{coins:,} coins"
    bbox = draw.textbbox((0, 0), val_text, font=val_font)
    tw = bbox[2] - bbox[0]
    draw.text(((CARD_W - tw) // 2, val_y + 8), val_text, font=val_font, fill=(255, 215, 80))

    # Mint credits (replaces the old slot tag) + flavor
    flavor_font = _font(13)
    footer_y = val_y + 56
    mint_parts = []
    if minted_by:
        mint_parts.append(f"Minted by {minted_by}")
    if minted_at:
        mint_parts.append(minted_at)
    if mint_parts:
        mint_text = "  ·  ".join(mint_parts)
        bbox = draw.textbbox((0, 0), mint_text, font=flavor_font)
        draw.text(
            (CARD_W - 24 - (bbox[2] - bbox[0]), footer_y),
            mint_text,
            font=flavor_font,
            fill=rgb,
        )
    fy = footer_y + 18
    for line in _wrap(flavor, flavor_font, draw, CARD_W - 48, max_lines=3):
        draw.text((24, fy), line, font=flavor_font, fill=(170, 170, 180))
        fy += 16

    buf = io.BytesIO()
    card.save(buf, "PNG", optimize=True)
    buf.seek(0)
    return buf


def _wrap(text: str, font, draw: ImageDraw.ImageDraw, max_w: int, *, max_lines: int = 99):
    """Word-wrap text to fit max_w. Returns list of lines (capped at max_lines)."""
    words = text.split()
    lines = []
    cur = ""
    for w in words:
        cand = (cur + " " + w).strip()
        bbox = draw.textbbox((0, 0), cand, font=font)
        if bbox[2] - bbox[0] <= max_w:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = w
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return lines


if __name__ == "__main__":
    # Smoke test: render one card per tier to /tmp.
    samples = [
        ("Common",    (191, 191, 191),    50_000),
        ("Uncommon",  (87, 242, 135),    150_000),
        ("Rare",      (88, 101, 242),    500_000),
        ("Epic",      (155, 89, 182),  1_500_000),
        ("Legendary", (255, 215, 0),   4_000_000),
        ("Mythic",    (255, 50, 200),  9_000_000),
    ]
    out_dir = os.environ.get("TMPDIR", "/tmp")
    for rarity, rgb, coins in samples:
        buf = render_card(
            rarity_name=rarity,
            item_name=f"Quantum {rarity} Trinket of Dubious Origin",
            coins=coins,
            color=rgb,
            flavor="A pigeon delivered this strapped to its leg.",
            is_mythic=(rarity == "Mythic"),
            minted_by="@zachary",
            minted_at="2026-05-04",
        )
        path = os.path.join(out_dir, f"loot_sample_{rarity.lower()}.png")
        with open(path, "wb") as f:
            f.write(buf.read())
        print(f"  wrote {path}")

    # Extra Commons so the user can see the chaotic-shape variety
    for i in range(6):
        buf = render_card(
            rarity_name="Common",
            item_name=f"Quantum Common Trinket of Dubious Origin",
            coins=50_000,
            color=(191, 191, 191),
            flavor="A pigeon delivered this strapped to its leg.",
            minted_by="@blbot",
            minted_at="2026-05-04",
        )
        path = os.path.join(out_dir, f"loot_sample_common_{i + 2}.png")
        with open(path, "wb") as f:
            f.write(buf.read())
        print(f"  wrote {path}")
