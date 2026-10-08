import discord
from discord.ext import commands
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import logging
import os
import random

import user_settings

logger = logging.getLogger(__name__)

# The server lives in Central time. A TZ env var (the same one the rest of the
# bot reads, see config.py) overrides it; the container doesn't set one, so
# falling back to the host zone would mean UTC.
DEFAULT_TZ = os.environ.get("TZ") or "America/Chicago"

# Key for this cog's entry in the shared /pref registry.
TIMEZONE_SETTING = "timezone"

# Friendly names people will actually type; anything else is tried as an IANA
# zone name (e.g. "Europe/London").
ZONE_ALIASES = {
    "central": "America/Chicago", "ct": "America/Chicago",
    "cst": "America/Chicago", "cdt": "America/Chicago",
    "eastern": "America/New_York", "et": "America/New_York",
    "est": "America/New_York", "edt": "America/New_York",
    "mountain": "America/Denver", "mt": "America/Denver",
    "mst": "America/Denver", "mdt": "America/Denver",
    "pacific": "America/Los_Angeles", "pt": "America/Los_Angeles",
    "pst": "America/Los_Angeles", "pdt": "America/Los_Angeles",
    "utc": "UTC", "gmt": "UTC",
}

# How often !date comes with a free insult.
SASS_CHANCE = 0.35

# Hand-written, never generated. Crude about the asker, never about family.
SASS_LINES = [
    "Why you so dumb that you don't know the date, dude?",
    "Your phone has a clock on it. It's the thing you stare at all day, genius.",
    "Bro asked a casino bot what day it is. Rock bottom has a basement and you found it.",
    "You've lost track of time gambling again, haven't you, degenerate.",
    "Imagine needing a Discord bot to tell you the date. Couldn't be me.",
    "Write it on your hand this time, dumbass.",
    "You're asking me? You can't even keep track of your own wallet.",
    "Every device you own displays this. You chose violence instead.",
    "Congrats, you've been in jail so long you forgot what year it is.",
    "Wow. Brain completely empty. Not even a calendar in there.",
]


def ordinal(n: int) -> str:
    """1 -> '1st', 2 -> '2nd', 11 -> '11th', 22 -> '22nd'."""
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def format_date(dt: datetime) -> str:
    """'Wednesday, October 7th, 2026 — 3:42 PM CDT'."""
    hour = dt.hour % 12 or 12
    clock = f"{hour}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"
    return (f"{dt.strftime('%A')}, {dt.strftime('%B')} {ordinal(dt.day)}, "
            f"{dt.year} — {clock} {dt.tzname()}")


def resolve_zone(name: str | None) -> ZoneInfo | None:
    """Alias or IANA name -> ZoneInfo; None for blank input means the default.
    Returns None if the name isn't a known zone."""
    key = ZONE_ALIASES.get(name.strip().lower(), name.strip()) if name else DEFAULT_TZ
    try:
        return ZoneInfo(key)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def validate_timezone(raw: str) -> str:
    """/pref validator: accept an alias or IANA name, store the IANA name."""
    tz = resolve_zone(raw) if raw.strip() else None
    if tz is None:
        raise ValueError("That's not a timezone. Try `central`, `pacific`, "
                         "`est`, or a full name like `Europe/London`.")
    return tz.key


def pick_zone(invoker_id: int, zone: str | None,
              target=None) -> tuple[ZoneInfo | None, str | None]:
    """Which zone to report in. Returns (zone, error_message); exactly one is
    non-None. Mirrors weather: an @mentioned member's saved zone > a typed
    zone > the invoker's own saved zone > the server default."""
    if target is not None:
        saved = user_settings.get_value(target.id, TIMEZONE_SETTING)
        if not saved:
            who = "You haven't" if target.id == invoker_id else f"**{target.display_name}** hasn't"
            return None, (f"{who} saved a timezone. "
                          "Set one with `/pref set timezone <zone>`.")
        return resolve_zone(saved) or resolve_zone(None), None

    if zone and zone.strip():
        tz = resolve_zone(zone)
        if tz is None:
            return None, (f"Never heard of a timezone called `{zone}`. Try `central`, "
                          "`eastern`, `pacific`, or something like `Europe/London`.")
        return tz, None

    saved = user_settings.get_value(invoker_id, TIMEZONE_SETTING)
    return resolve_zone(saved) or resolve_zone(None), None


class Date(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        # Players can `/pref set timezone pacific` and then just `!date`.
        user_settings.register(
            key=TIMEZONE_SETTING,
            label="Timezone",
            description="Your timezone for !date (e.g. central, pacific, Europe/London)",
            validate=validate_timezone,
        )

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Date module has been loaded")

    @commands.command(name="date", aliases=["today"])
    async def date(self, ctx, *, zone: str = None):
        """Today's date, written out. Central time unless you name a zone
        (!date pacific, !date Europe/London), saved one with
        `/pref set timezone <zone>`, or ask about a member (!date @someone)."""
        target = ctx.message.mentions[0] if ctx.message.mentions else None
        tz, error = pick_zone(ctx.author.id, zone, target)
        if error:
            await ctx.send(error, allowed_mentions=discord.AllowedMentions.none())
            return
        where = f" for **{target.display_name}**" if target else ""
        msg = f"📅 Today{where} is **{format_date(datetime.now(tz))}**."
        if random.random() < SASS_CHANCE:
            msg = f"{random.choice(SASS_LINES)}\n{msg}"
        await ctx.send(msg, allowed_mentions=discord.AllowedMentions.none())

    # Prefix only — slash commands are at Discord's 100-global-command cap.


async def setup(bot):
    await bot.add_cog(Date(bot))
