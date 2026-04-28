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
from typing import Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont


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


# ---------- Top-level renderer ----------

def render_card(
    rarity_name: str,
    item_name: str,
    coins: int,
    color,
    emoji: str,
    slot: str,
    flavor: str,
    *,
    is_mythic: bool = False,
) -> io.BytesIO:
    """Render a unique trading-card PNG and return as a BytesIO ready for upload."""
    rng = random.Random()  # OS-entropy seeded → unique per call
    rgb = _color_tuple(color)

    style_name, style_fn = rng.choice(_ART_STYLES)
    art_low = style_fn(rng, rgb)

    # Smooth upscale, light blur — gives the art a painterly feel except for
    # 'static' (which we want to stay crunchy).
    art = art_low.resize((ART_W, ART_H), Image.BICUBIC)
    if style_name != "static":
        art = art.filter(ImageFilter.GaussianBlur(radius=0.8))

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

    # ---- Compose the card ----
    card = Image.new("RGB", (CARD_W, CARD_H), (15, 15, 22))
    draw = ImageDraw.Draw(card)

    # Outer + inner frame
    draw.rectangle((4, 4, CARD_W - 5, CARD_H - 5), outline=rgb, width=3)
    draw.rectangle((10, 10, CARD_W - 11, CARD_H - 11), outline=(60, 60, 70), width=1)

    # Header strip
    header_font = _font(28)
    label = f"{emoji}  {rarity_name.upper()}  {emoji}"
    bbox = draw.textbbox((0, 0), label, font=header_font)
    tw = bbox[2] - bbox[0]
    draw.text(((CARD_W - tw) // 2, 28), label, font=header_font, fill=rgb)

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

    # Slot tag + flavor
    flavor_font = _font(13)
    footer_y = val_y + 56
    slot_tag = f"[{slot.upper()} DROP]"
    bbox = draw.textbbox((0, 0), slot_tag, font=flavor_font)
    draw.text(
        (CARD_W - 24 - (bbox[2] - bbox[0]), footer_y),
        slot_tag,
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
        ("Common",    (191, 191, 191), "⬜",       50_000),
        ("Uncommon",  (87, 242, 135),  "🟩",      150_000),
        ("Rare",      (88, 101, 242),  "🟦",      500_000),
        ("Epic",      (155, 89, 182),  "🟪",    1_500_000),
        ("Legendary", (255, 215, 0),   "🟨",    4_000_000),
        ("Mythic",    (255, 50, 200),  "🌈",    9_000_000),
    ]
    out_dir = os.environ.get("TMPDIR", "/tmp")
    for rarity, rgb, emj, coins in samples:
        buf = render_card(
            rarity_name=rarity,
            item_name=f"Quantum {rarity} Trinket of Dubious Origin",
            coins=coins,
            color=rgb,
            emoji=emj,
            slot="am",
            flavor="A pigeon delivered this strapped to its leg.",
            is_mythic=(rarity == "Mythic"),
        )
        path = os.path.join(out_dir, f"loot_sample_{rarity.lower()}.png")
        with open(path, "wb") as f:
            f.write(buf.read())
        print(f"  wrote {path}")
