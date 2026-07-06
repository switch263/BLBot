"""All-in-one unit converter: /convert 72f to c, 100 usd to eur, 5mi to km.

Categories: temperature, length, mass, volume, speed, data, currency.
Physical units convert via base-unit factors (temperature is affine and
special-cased). Currency uses the ECB daily rates from the free, keyless
Frankfurter API (https://frankfurter.dev), cached per base for an hour —
rates are "good enough for Discord", not for wiring money.

Replaces the old /ctf + /ftc temperature pair (cogs/temperature.py, retired).
"""
import re
import time
import logging
from typing import Optional

import aiohttp
import discord
from discord.ext import commands
from discord import app_commands

logger = logging.getLogger(__name__)

FX_API = "https://api.frankfurter.dev/v1/latest"
FX_CACHE_TTL = 3600  # ECB rates update once a day; an hour of cache is plenty

# --- unit tables --------------------------------------------------------------
# factor = how many BASE units one of this unit is. Base units: m, g, l, m/s, byte.
LENGTH = {
    "mm": 0.001, "cm": 0.01, "m": 1.0, "km": 1000.0,
    "in": 0.0254, "ft": 0.3048, "yd": 0.9144, "mi": 1609.344, "nmi": 1852.0,
}
MASS = {
    "mg": 0.001, "g": 1.0, "kg": 1000.0, "t": 1_000_000.0,
    "oz": 28.349523125, "lb": 453.59237, "st": 6350.29318,
}
VOLUME = {
    "ml": 0.001, "l": 1.0,
    "tsp": 0.00492892159375, "tbsp": 0.01478676478125, "floz": 0.0295735295625,
    "cup": 0.2365882365, "pt": 0.473176473, "qt": 0.946352946, "gal": 3.785411784,
}
SPEED = {
    "ms": 1.0, "kph": 1 / 3.6, "mph": 0.44704, "knot": 0.514444,
}
DATA = {
    "b": 1.0, "kb": 1024.0, "mb": 1024.0**2, "gb": 1024.0**3, "tb": 1024.0**4,
}
TEMPERATURE = {"c", "f", "k"}

CATEGORIES: list[tuple[str, dict]] = [
    ("length", LENGTH), ("mass", MASS), ("volume", VOLUME),
    ("speed", SPEED), ("data", DATA),
]

# Currencies Frankfurter (ECB) publishes. Kept local so unknown units fail fast
# with a clean message instead of an API round-trip.
CURRENCIES = {
    "aud", "bgn", "brl", "cad", "chf", "cny", "czk", "dkk", "eur", "gbp",
    "hkd", "huf", "idr", "ils", "inr", "isk", "jpy", "krw", "mxn", "myr",
    "nok", "nzd", "php", "pln", "ron", "sek", "sgd", "thb", "try", "usd", "zar",
}

# Friendly spellings -> canonical unit key.
ALIASES = {
    "celsius": "c", "centigrade": "c", "°c": "c",
    "fahrenheit": "f", "°f": "f",
    "kelvin": "k",
    "millimeter": "mm", "millimeters": "mm", "millimetre": "mm", "millimetres": "mm",
    "centimeter": "cm", "centimeters": "cm", "centimetre": "cm", "centimetres": "cm",
    "meter": "m", "meters": "m", "metre": "m", "metres": "m",
    "kilometer": "km", "kilometers": "km", "kilometre": "km", "kilometres": "km",
    "inch": "in", "inches": "in", '"': "in",
    "foot": "ft", "feet": "ft", "'": "ft",
    "yard": "yd", "yards": "yd",
    "mile": "mi", "miles": "mi",
    "nauticalmile": "nmi", "nauticalmiles": "nmi",
    "milligram": "mg", "milligrams": "mg",
    "gram": "g", "grams": "g",
    "kilogram": "kg", "kilograms": "kg", "kilo": "kg", "kilos": "kg",
    "tonne": "t", "tonnes": "t", "ton": "t", "tons": "t",
    "ounce": "oz", "ounces": "oz",
    "pound": "lb", "pounds": "lb", "lbs": "lb",
    "stone": "st",
    "milliliter": "ml", "milliliters": "ml", "millilitre": "ml", "millilitres": "ml",
    "liter": "l", "liters": "l", "litre": "l", "litres": "l",
    "teaspoon": "tsp", "teaspoons": "tsp",
    "tablespoon": "tbsp", "tablespoons": "tbsp",
    "cups": "cup",
    "pint": "pt", "pints": "pt",
    "quart": "qt", "quarts": "qt",
    "gallon": "gal", "gallons": "gal",
    "m/s": "ms", "mps": "ms",
    "km/h": "kph", "kmh": "kph",
    "mih": "mph", "mi/h": "mph",
    "knots": "knot", "kt": "knot", "kts": "knot",
    "byte": "b", "bytes": "b",
    "kilobyte": "kb", "kilobytes": "kb",
    "megabyte": "mb", "megabytes": "mb",
    "gigabyte": "gb", "gigabytes": "gb",
    "terabyte": "tb", "terabytes": "tb",
    "$": "usd", "dollar": "usd", "dollars": "usd", "bucks": "usd",
    "€": "eur", "euro": "eur", "euros": "eur",
    "£": "gbp", "quid": "gbp",
    "¥": "jpy", "yen": "jpy",
}

USAGE = (
    "Usage: `/convert 72f to c` — also `100 usd to eur`, `5 mi to km`, "
    "`10kg lb`, `2 cups in ml`, `500gb tb`, `60mph kph`.\n"
    "Categories: temperature (c/f/k), length (mm–mi), mass (mg–st), volume "
    "(tsp–gal), speed (kph/mph/knots), data (b–tb), currency (usd/eur/gbp/…)."
)

_QUERY_RE = re.compile(
    r"^\s*(-?[\d][\d,]*\.?\d*)\s*([a-z°$€£¥/'\"]+)\s*(?:to|in|as|->|→)?\s*([a-z°$€£¥/'\"]+)\s*$",
    re.IGNORECASE,
)


def _canon(unit: str) -> str:
    u = unit.strip().lower()
    return ALIASES.get(u, u)


def _category(unit: str) -> Optional[str]:
    if unit in TEMPERATURE:
        return "temperature"
    for name, table in CATEGORIES:
        if unit in table:
            return name
    if unit in CURRENCIES:
        return "currency"
    return None


def _to_celsius(value: float, unit: str) -> float:
    if unit == "c":
        return value
    if unit == "f":
        return (value - 32) / 1.8
    return value - 273.15  # k


def _from_celsius(value: float, unit: str) -> float:
    if unit == "c":
        return value
    if unit == "f":
        return value * 1.8 + 32
    return value + 273.15  # k


def _fmt(x: float) -> str:
    """Human-friendly number: thousands separators, sensible precision,
    no trailing zero noise."""
    if x == 0:
        return "0"
    if abs(x) >= 1:
        s = f"{x:,.4f}".rstrip("0").rstrip(".")
    else:
        s = f"{x:.6g}"
    return s


def convert_physical(value: float, src: str, dst: str) -> Optional[float]:
    """Convert within one physical category; None if units don't share one.
    Currency is not handled here (needs the async rate fetch)."""
    if src in TEMPERATURE and dst in TEMPERATURE:
        return _from_celsius(_to_celsius(value, src), dst)
    for _name, table in CATEGORIES:
        if src in table and dst in table:
            return value * table[src] / table[dst]
    return None


class Convert(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None
        self._fx_cache: dict[str, tuple[float, dict]] = {}  # base -> (ts, rates)

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Convert module has been loaded")

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def _rates(self, base: str) -> Optional[dict]:
        """Frankfurter rates for `base`, cached FX_CACHE_TTL. None on failure."""
        cached = self._fx_cache.get(base)
        if cached and time.time() - cached[0] < FX_CACHE_TTL:
            return cached[1]
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10))
        try:
            async with self.session.get(FX_API, params={"base": base.upper()}) as resp:
                if resp.status != 200:
                    logger.warning(f"convert: FX API {resp.status} for base {base}")
                    return None
                data = await resp.json()
                rates = {k.lower(): v for k, v in data.get("rates", {}).items()}
                rates[base] = 1.0
                self._fx_cache[base] = (time.time(), rates)
                return rates
        except Exception as e:
            logger.warning(f"convert: FX fetch failed: {e}")
            return None

    async def _convert(self, query: str) -> str:
        m = _QUERY_RE.match(query)
        if not m:
            return USAGE
        try:
            value = float(m.group(1).replace(",", ""))
        except ValueError:
            return USAGE
        src, dst = _canon(m.group(2)), _canon(m.group(3))
        src_cat, dst_cat = _category(src), _category(dst)
        if src_cat is None or dst_cat is None:
            unknown = src if src_cat is None else dst
            return f"Unknown unit **{unknown}**.\n{USAGE}"
        if src_cat != dst_cat:
            return (f"Can't convert **{src}** ({src_cat}) to **{dst}** "
                    f"({dst_cat}). Pick two units from the same category.")

        if src_cat == "currency":
            if src == dst:
                return f"💱 {_fmt(value)} {src.upper()} is… {_fmt(value)} {dst.upper()}. Nailed it."
            rates = await self._rates(src)
            if not rates or dst not in rates:
                return "💱 Couldn't reach the exchange-rate service. Try again in a bit."
            result = value * rates[dst]
            return (f"💱 **{_fmt(value)} {src.upper()}** = **{_fmt(result)} "
                    f"{dst.upper()}** (ECB daily rate)")

        result = convert_physical(value, src, dst)
        if result is None:
            return USAGE
        emoji = {"temperature": "🌡️", "length": "📏", "mass": "⚖️",
                 "volume": "🧪", "speed": "🏎️", "data": "💾"}[src_cat]
        unit_out = {"c": "°C", "f": "°F", "k": "K"}.get
        return (f"{emoji} **{_fmt(value)} {unit_out(src, src)}** = "
                f"**{_fmt(result)} {unit_out(dst, dst)}**")

    @commands.command(name="convert")
    async def convert_prefix(self, ctx, *, query: str = ""):
        """Convert units: !convert 72f to c / 100 usd to eur / 5mi to km"""
        await ctx.send(await self._convert(query))

    @app_commands.command(name="convert", description="Convert units & currency: 72f to c, 100 usd to eur, 5mi to km")
    @app_commands.describe(query="What to convert, e.g. '72f to c', '100 usd to eur', '10kg lb'")
    async def convert_slash(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        await interaction.followup.send(await self._convert(query))


async def setup(bot):
    await bot.add_cog(Convert(bot))
