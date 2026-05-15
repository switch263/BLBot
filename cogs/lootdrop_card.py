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

# Per-tier stat ranges. Bigger tiers roll bigger numbers; the values are
# illustrative and don't drive any gameplay yet — they exist so each card
# carries the same TCG-style HP / ATK badges every player expects.
_HP_RANGES = {
    "Common":    (10, 30),
    "Uncommon":  (30, 60),
    "Rare":      (60, 100),
    "Epic":      (100, 150),
    "Legendary": (150, 220),
    "Mythic":    (220, 350),
    "Divine":    (700, 999),
}
_ATK_RANGES = {
    "Common":    (5, 15),
    "Uncommon":  (15, 30),
    "Rare":      (30, 55),
    "Epic":      (55, 90),
    "Legendary": (90, 140),
    "Mythic":    (140, 220),
    "Divine":    (400, 666),
}


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


# ---------- BLBot object generator ----------
# Each loot card features a static everyday object — beach ball, umbrella, can
# of compressed air, water bottle, MacBook, box of tissues, etc. Per-object
# builders lay down silhouette masks; the renderer outlines and fills each
# part, then a per-object decorator paints details (panels, labels, screens).
# Everything draws at 2× and downsamples for clean edges.

# Names used for the procedural creature nickname in the card title.
_NAME_TITLES = (
    "Sir", "Lady", "Captain", "Doctor", "Professor", "Lord",
    "Mister", "Madam", "Astro-", "Mecha-", "Lil",
)
_NAME_HEADS = (
    "Zap", "Boop", "Glitch", "Pix", "Blip", "Zorp", "Mecha", "Quib", "Snib",
    "Glow", "Flux", "Twit", "Whirl", "Buzz", "Crank", "Skib", "Vex", "Doink",
    "Mox", "Plip", "Snorp", "Quark", "Wisp", "Yip", "Snoot", "Glim", "Bork",
    "Drib", "Fizz", "Zog", "Nyx", "Pog", "Lump", "Goo", "Tato", "Beep",
    "Wuv", "Snug", "Rumb", "Plonk", "Chomp", "Wibb", "Floof", "Klonk",
    "Sploot", "Bink", "Pluf", "Zib", "Twink", "Frob", "Hork", "Smibble",
    "Glomp", "Pancake", "Bagel",
)
_NAME_TAILS = (
    "tron", "bot", "nik", "kins", "punk", "byte", "let", "ster", "wig",
    "puff", "spark", "snorp", "boop", "doodle",
)
_NAME_SUFFIXES = (
    "the Whimsical", "the Mighty", "Mk. II", "Mk. III", "v2.0", "the III",
    "Jr.", "of the Vault", "Prime", "Deluxe", "the Spicy", "the Crispy",
)


def _blbot_name(rng: random.Random) -> str:
    parts = []
    if rng.random() < 0.18:
        title = rng.choice(_NAME_TITLES)
        parts.append(title if title.endswith("-") else title + " ")
    parts.append(rng.choice(_NAME_HEADS) + rng.choice(_NAME_TAILS))
    if rng.random() < 0.20:
        parts.append(" " + rng.choice(_NAME_SUFFIXES))
    return "".join(parts)


def _draw_sigil(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int, fill_rgb):
    """Diamond gem with inner highlight, used in the card header."""
    pts = [(cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy)]
    draw.polygon(pts, fill=fill_rgb, outline=(20, 20, 30))
    inner = max(2, size // 2)
    hl = (_clamp(fill_rgb[0] + 80), _clamp(fill_rgb[1] + 80), _clamp(fill_rgb[2] + 80))
    draw.polygon(
        [(cx, cy - inner), (cx + inner // 2, cy - inner // 3),
         (cx, cy), (cx - inner // 2, cy - inner // 3)],
        fill=hl,
    )


# ---------- Object registry ----------
# Object art is hand-curated and pre-processed into assets/objects/. Each
# entry maps the species slug used on disk (and as the random-pool key) to a
# proper display name shown in the card title.

_OBJECTS = {
    # Short display names — they're prepended with a nickname and a rarity in
    # the card title, so anything verbose blows the 3-line wrap budget.
    "beach_ball":                    "Beach Ball",
    "hot_dog":                       "Hot Dog",
    "the_don":                       "Don",
    "trojan_horse":                  "Trojan Horse",
    "llama_gorilla":                 "Llamilla",
    "mr_cat_nut":                    "Catnut",
    "baked_potato_butter":           "Buttered Spud",
    "baked_potato_cheese_broccoli":  "Broc-Spud",
    "baked_potato_cheese_butter":    "Cheese Spud",
    "baked_potato_chili":            "Chili Spud",
    "t_bone_steak":                  "T-Bone",
    "the_goat":                      "Goat",
    "zebra_monkey":                  "Zonkey",
    "lobster_freak":                 "Lobsterfreak",
    "eggplant_of_suspicion":         "Sus Eggplant",
    "penguin_donkey":                "Pendonk",
    "frogfather":                    "Frogfather",
    "slothronaut":                   "Slothronaut",
    "tax_pug":                       "Tax Pug",
    "possum_pope":                   "Possum Pope",
    "possum_tongue":                 "Possum Tongue",
    "lobster_man":                   "Lobsterman",
    "gorgochelid":                   "Gorgochelid",
    "alien_baker":                   "Alien Baker",
    "zanchez":                       "Zanchez",
    "maple_harvest_beer":            "Maple Harvest Beer",
    "maple_bacon_banana":            "Maple Bacon Banana",
    "mystery_hotdog":                "Mystery Hot Dog",
    "qr_rickroll":                   "Codex",  # Divine-tier QR card
}

# Species that the random pool should NEVER roll on its own. They only show
# up when the caller forces species= explicitly (used for tier-locked cards
# like the QR-code Divine drop).
_LOCKED_SPECIES = frozenset({"qr_rickroll"})

# Public API kept under the historical names so the lootdrop cog and any
# other importer keep working without changes.
ANIMAL_SPECIES = tuple(s for s in _OBJECTS if s not in _LOCKED_SPECIES)
_OBJECT_DISPLAY_NAMES = dict(_OBJECTS)

_ASSET_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "assets", "objects")
)

# Lazy {species_slug: [path, ...]} index. Rescan whenever a render is requested
# for a species we haven't seen yet, so newly-added asset variants are picked
# up without needing a process restart.
_ASSET_INDEX_CACHE: dict | None = None


def _asset_index() -> dict:
    global _ASSET_INDEX_CACHE
    if _ASSET_INDEX_CACHE is not None:
        return _ASSET_INDEX_CACHE
    index: dict = {}
    if os.path.isdir(_ASSET_DIR):
        for fname in sorted(os.listdir(_ASSET_DIR)):
            if not fname.endswith(".png"):
                continue
            stem = fname[:-4]
            # Filename format: <slug>_<index>.png so multiple variants of one
            # species can share a slug (e.g. trojan_horse_00.png, _01.png).
            if "_" not in stem:
                continue
            slug, idx = stem.rsplit("_", 1)
            if not idx.isdigit():
                continue
            index.setdefault(slug, []).append(os.path.join(_ASSET_DIR, fname))
    _ASSET_INDEX_CACHE = index
    return index


def pick_species(rng: random.Random | None = None) -> str:
    """Pick a random object slug. Name kept for backwards-compat with callers."""
    rng = rng or random.Random()
    return rng.choice(ANIMAL_SPECIES)


def _render_blbot(rng: random.Random, color, art_size, *, species: str | None = None):
    """Load the card's object illustration from `assets/objects/` and return
    (canvas, slug). Falls back to a transparent placeholder if the asset is
    missing — that should only happen mid-development before assets are
    re-processed; production always ships with a complete asset set."""
    w, h = art_size
    if species is None or species not in _OBJECTS:
        species = pick_species(rng)
    variants = _asset_index().get(species)
    if not variants:
        # Asset missing — return an empty layer so the rest of the card still
        # renders rather than crashing the loot drop.
        return Image.new("RGBA", art_size, (0, 0, 0, 0)), species
    img = Image.open(rng.choice(variants)).convert("RGBA")
    if img.size != art_size:
        img = img.resize(art_size, Image.LANCZOS)
    return img, species


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
    species: str | None = None,
) -> io.BytesIO:
    """Render a unique trading-card PNG and return as a BytesIO ready for upload.

    If `item_name` contains the literal placeholder "{species}", it is replaced
    with the (capitalized) animal species rendered on the card; otherwise the
    name is used verbatim. Pass `species` explicitly to force a particular
    animal — useful when the caller wants the item name and the card art to
    agree on what creature was rolled."""
    rng = random.Random()  # OS-entropy seeded → unique per call
    rgb = _color_tuple(color)
    creature_nickname = _blbot_name(rng)
    if minted_at is None:
        minted_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    style_name, style_fn = rng.choice(_ART_STYLES)
    art_low = style_fn(rng, rgb)

    # Smooth upscale, light blur — gives the art a painterly feel except for
    # 'static' (which we want to stay crunchy).
    art = art_low.resize((ART_W, ART_H), Image.BICUBIC)
    if style_name != "static":
        art = art.filter(ImageFilter.GaussianBlur(radius=0.8))

    blbot, rendered_species = _render_blbot(rng, rgb, (ART_W, ART_H),
                                             species=species)

    # Tier glow — composite a halo behind the creature using its alpha channel,
    # tinted with the rarity color so the figure pops off the busy background.
    # Two passes (inner intense + outer soft) give shape; intensity scales up
    # with tier so Mythic feels more dramatic than Common.
    glow_intensity = {
        "Common": 0.55, "Uncommon": 0.75, "Rare": 0.90,
        "Epic": 1.05, "Legendary": 1.20, "Mythic": 1.35,
    }.get(rarity_name, 0.85)
    # Brighten the tier color toward white so darker tiers (e.g., Rare blue)
    # still cast a luminous halo rather than a muddy shadow.
    glow_rgb = tuple(min(255, int(c * 0.55 + 255 * 0.45)) for c in rgb)
    creature_alpha = blbot.split()[3]
    glow_mask = creature_alpha.filter(ImageFilter.MaxFilter(15))
    glow_canvas = Image.new("RGBA", (ART_W, ART_H), (0, 0, 0, 0))
    inner = Image.new("RGBA", (ART_W, ART_H),
                      glow_rgb + (min(255, int(220 * glow_intensity)),))
    inner.putalpha(ImageChops.multiply(inner.split()[3], glow_mask))
    inner = inner.filter(ImageFilter.GaussianBlur(radius=12))
    glow_canvas = Image.alpha_composite(glow_canvas, inner)
    outer = Image.new("RGBA", (ART_W, ART_H),
                      glow_rgb + (min(255, int(170 * glow_intensity)),))
    outer.putalpha(ImageChops.multiply(outer.split()[3], glow_mask))
    outer = outer.filter(ImageFilter.GaussianBlur(radius=28))
    glow_canvas = Image.alpha_composite(glow_canvas, outer)
    art = Image.alpha_composite(art.convert("RGBA"), glow_canvas).convert("RGB")

    art = Image.alpha_composite(art.convert("RGBA"), blbot).convert("RGB")
    # Substitute the object name into the item title placeholder. Underscores
    # become spaces so multi-word object keys read as a normal English noun
    # (e.g. "box of tissues" → "Box Of Tissues"). Title casing keeps the look
    # consistent with the rest of the title.
    if "{species}" in item_name:
        pretty = _OBJECT_DISPLAY_NAMES.get(rendered_species,
                                            rendered_species.replace("_", " ").title())
        # The interpolated template wraps the species in "<nickname> the X of
        # Dubious Origin", so a species name that already starts with "The"
        # would double-article ("Snootboop the The Goat ..."). Strip the
        # leading article when substituting.
        if pretty.lower().startswith("the "):
            pretty = pretty[4:]
        item_name = item_name.replace("{species}", pretty)
    # Prepend the procedural nickname so the title reads like a proper TCG
    # card: "Bilpoboclaw the Quantum Common Beach Ball of Dubious Origin".
    item_name = f"{creature_nickname} the {item_name}"

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

    # The nickname now goes into the item title at the bottom of the card
    # ("Bilpoboclaw the Quantum Common Cat of Dubious Origin"), so the corner
    # badge that used to display it has been removed.
    art = art.convert("RGB")

    # ---- Compose the card ----
    # Subtle vertical gradient background pulls a touch of the tier color
    # into the corners so the card doesn't read as a flat dark slab.
    card = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 255))
    bg_top = (
        _clamp(15 + rgb[0] // 12),
        _clamp(15 + rgb[1] // 12),
        _clamp(22 + rgb[2] // 12),
    )
    bg_bot = (
        _clamp(8  + rgb[0] // 28),
        _clamp(8  + rgb[1] // 28),
        _clamp(14 + rgb[2] // 28),
    )
    bg_draw = ImageDraw.Draw(card)
    for y in range(CARD_H):
        t = y / max(1, CARD_H - 1)
        bg_draw.line(
            [(0, y), (CARD_W, y)],
            fill=(
                int(bg_top[0] + (bg_bot[0] - bg_top[0]) * t),
                int(bg_top[1] + (bg_bot[1] - bg_top[1]) * t),
                int(bg_top[2] + (bg_bot[2] - bg_top[2]) * t),
                255,
            ),
        )
    draw = ImageDraw.Draw(card)

    # Rounded outer frame in the tier color + thin inner pinstripe so the
    # border reads like a proper TCG card edge.
    draw.rounded_rectangle(
        (3, 3, CARD_W - 4, CARD_H - 4),
        radius=18, outline=rgb, width=4,
    )
    draw.rounded_rectangle(
        (10, 10, CARD_W - 11, CARD_H - 11),
        radius=14, outline=(245, 245, 230, 60), width=1,
    )

    # Soft inner glow on the frame in the tier color — paint, blur, composite.
    glow = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle(
        (6, 6, CARD_W - 7, CARD_H - 7),
        radius=16, outline=rgb + (180,), width=8,
    )
    glow = glow.filter(ImageFilter.GaussianBlur(radius=4))
    card = Image.alpha_composite(card, glow)
    draw = ImageDraw.Draw(card)

    # Tier-colored diamond ornaments in each corner — small TCG-style accents.
    for cx_o, cy_o in (
        (24, 24), (CARD_W - 24, 24),
        (24, CARD_H - 24), (CARD_W - 24, CARD_H - 24),
    ):
        _draw_sigil(draw, cx_o, cy_o, 5, rgb)

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

    # ---- TCG-style stat badges (HP top-right, ATK top-left of art panel) ----
    hp_lo, hp_hi = _HP_RANGES.get(rarity_name, (10, 30))
    atk_lo, atk_hi = _ATK_RANGES.get(rarity_name, (5, 15))
    hp_value = rng.randint(hp_lo, hp_hi)
    atk_value = rng.randint(atk_lo, atk_hi)
    badge_font = _font(15)

    def _draw_badge(label: str, value: int, anchor: str, fill_rgb, text_rgb):
        text = f"{label} {value}"
        b = draw.textbbox((0, 0), text, font=badge_font)
        tw_ = b[2] - b[0]
        th_ = b[3] - b[1]
        pad_x, pad_y = 8, 4
        box_w = tw_ + pad_x * 2
        box_h = th_ + pad_y * 2 + 2
        if anchor == "tr":
            x0 = ART_X + ART_W - box_w - 6
        else:  # "tl"
            x0 = ART_X + 6
        y0 = ART_Y + 6
        draw.rounded_rectangle(
            (x0, y0, x0 + box_w, y0 + box_h),
            radius=6, fill=fill_rgb, outline=(245, 245, 245), width=2,
        )
        draw.text((x0 + pad_x, y0 + pad_y - 1), text,
                  font=badge_font, fill=text_rgb)

    _draw_badge("HP",  hp_value,  "tr", (180, 35, 50),  (255, 255, 255))
    _draw_badge("ATK", atk_value, "tl", (220, 130, 30), (30, 22, 18))

    # Item name (wrap up to 3 lines so longer species like "Baked Potato with
    # Cheese and Broccoli" don't get truncated mid-word).
    name_font = _font(20)
    name_y = ART_Y + ART_H + 18
    for line in _wrap(item_name, name_font, draw, CARD_W - 48, max_lines=3):
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

    # Round the card corners by clipping the alpha to a rounded rectangle.
    corner_mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(corner_mask).rounded_rectangle(
        (0, 0, CARD_W - 1, CARD_H - 1), radius=20, fill=255,
    )
    card.putalpha(corner_mask)

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
        ("Common",    (191, 191, 191),       50_000),
        ("Uncommon",  (87, 242, 135),       150_000),
        ("Rare",      (88, 101, 242),       500_000),
        ("Epic",      (155, 89, 182),     1_500_000),
        ("Legendary", (255, 215, 0),      4_000_000),
        ("Mythic",    (255, 50, 200),     9_000_000),
        ("Divine",    (255, 240, 200),  120_000_000),
    ]
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")
    os.makedirs(out_dir, exist_ok=True)
    for rarity, rgb, coins in samples:
        if rarity == "Divine":
            item_name = "Codex"
            forced_species = "qr_rickroll"
        else:
            item_name = f"Quantum {rarity} {{species}}"
            forced_species = None
        buf = render_card(
            rarity_name=rarity,
            item_name=item_name,
            coins=coins,
            color=rgb,
            flavor="A pigeon delivered this strapped to its leg.",
            species=forced_species,
            is_mythic=(rarity == "Mythic"),
            minted_by="@blbot",
            minted_at="2026-05-04",
        )
        path = os.path.join(out_dir, f"loot_sample_{rarity.lower()}.png")
        with open(path, "wb") as f:
            f.write(buf.read())
        print(f"  wrote {path}")

    # Extra Commons so the user can see alien render variety
    for i in range(6):
        buf = render_card(
            rarity_name="Common",
            item_name=f"Quantum Common {{species}} of Dubious Origin",
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
