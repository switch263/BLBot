import discord
from discord.ext import commands, tasks
import json
import logging
import re
import time
from datetime import datetime, timedelta

from economy import kv_get, kv_set, kv_delete, kv_get_all, kv_incr, kv_all_in_namespace

logger = logging.getLogger(__name__)

NAMESPACE = "remindme"
SCAN_INTERVAL_SECONDS = 15
MIN_DELAY_SECONDS = 5
MAX_DELAY_SECONDS = 365 * 86400
MAX_ACTIVE_PER_USER = 25
MAX_TEXT_LEN = 300

_UNITS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
    "w": 604800, "week": 604800, "weeks": 604800,
    "mo": 2592000, "month": 2592000, "months": 2592000,
}

_NUM_RE = re.compile(r"^\d+(?:\.\d+)?$")
_FUSED_PART_RE = re.compile(r"(\d+(?:\.\d+)?)([a-z]+)")
_HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_AMPM_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?(am|pm)$")

USAGE = (
    "Usage: `!remindme <when> <what>` — e.g. "
    "`!remindme 7 days check on the gator`, `!remindme 2h30m withdraw from the bank`, "
    "`!remindme 12pm lunch`, `!remindme at 18:30 pig derby`, `!remindme tomorrow 9am pay taxes`. "
    "Durations take s/m/h/d/w/mo; clock times (`12pm`, `18:30`, `noon`) are server time — "
    "today, or tomorrow if that time already passed."
)


def _fused_seconds(tok: str):
    """'2h30m' -> 9000, or None if the token isn't purely number+unit pairs."""
    parts = _FUSED_PART_RE.findall(tok)
    if not parts or "".join(n + u for n, u in parts) != tok:
        return None
    total = 0.0
    for num, unit in parts:
        mult = _UNITS.get(unit)
        if mult is None:
            return None
        total += float(num) * mult
    return total


def _parse_clock(tok: str):
    """'18:30' / '9am' / '9:15pm' / 'noon' / 'midnight' -> (hour, minute), or None."""
    if tok == "noon":
        return (12, 0)
    if tok == "midnight":
        return (0, 0)
    m = _HHMM_RE.match(tok)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        return (h, mi) if h < 24 and mi < 60 else None
    m = _AMPM_RE.match(tok)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2) or 0)
        if not (1 <= h <= 12 and mi < 60):
            return None
        if m.group(3) == "pm" and h != 12:
            h += 12
        elif m.group(3) == "am" and h == 12:
            h = 0
        return (h, mi)
    return None


def parse_when(raw: str):
    """Split a leading time spec off the front of `raw`.

    Returns (due_epoch, text) on success or (None, error_message) on failure.
    Accepts durations ('7 days', '2h30m', 'in 90 minutes'), 'at HH:MM',
    'at YYYY-MM-DD [HH:MM]', and 'tomorrow [HH:MM|9am]'. Absolute times are
    interpreted in the bot's local timezone.
    """
    tokens = raw.strip().split()
    i = 0
    if i < len(tokens) and tokens[i].lower() == "in":
        i += 1
    if i >= len(tokens):
        return None, USAGE
    now = datetime.now()
    head = tokens[i].lower()

    if head in ("at", "on"):
        i += 1
        if i >= len(tokens):
            return None, "At... when? Give me a time, like `at 18:30` or `at 2026-08-01 09:00`."
        tok = tokens[i]
        try:
            date_part = datetime.strptime(tok, "%Y-%m-%d")
        except ValueError:
            date_part = None
        if date_part is not None:
            i += 1
            clock = _parse_clock(tokens[i].lower()) if i < len(tokens) else None
            if clock:
                i += 1
            else:
                clock = (9, 0)  # date with no time fires at 9am
            due = date_part.replace(hour=clock[0], minute=clock[1])
        else:
            clock = _parse_clock(tok.lower())
            if clock is None:
                return None, f"Couldn't read `{tok}` as a time. Try `18:30`, `9pm`, or `2026-08-01 09:00`."
            i += 1
            due = now.replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
            if due <= now:
                due += timedelta(days=1)  # that time already passed today -> tomorrow
        return due.timestamp(), " ".join(tokens[i:])

    if head == "tomorrow":
        i += 1
        clock = _parse_clock(tokens[i].lower()) if i < len(tokens) else None
        if clock:
            i += 1
        else:
            clock = (9, 0)
        due = (now + timedelta(days=1)).replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
        return due.timestamp(), " ".join(tokens[i:])

    # A bare clock time ('12pm', '18:30', 'noon') is an implicit 'at' — today,
    # or tomorrow if that time already passed.
    clock = _parse_clock(head)
    if clock is not None:
        i += 1
        due = now.replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
        if due <= now:
            due += timedelta(days=1)
        return due.timestamp(), " ".join(tokens[i:])

    # Durations: consume tokens while they parse as '7d', '2h30m', or '7 days'.
    total = 0.0
    while i < len(tokens):
        tok = tokens[i].lower().rstrip(",")
        fused = _fused_seconds(tok)
        if fused is not None:
            total += fused
            i += 1
            continue
        if _NUM_RE.match(tok) and i + 1 < len(tokens):
            mult = _UNITS.get(tokens[i + 1].lower().rstrip(","))
            if mult is not None:
                total += float(tok) * mult
                i += 2
                continue
        break
    if total <= 0:
        return None, USAGE
    return time.time() + total, " ".join(tokens[i:])


class RemindMe(commands.Cog):
    """RemindMe-style reminders. Stored in cog_kv so they survive restarts;
    a background loop delivers any that came due (late ones fire on the next
    scan after the bot comes back up)."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        if not self._reminder_loop.is_running():
            self._reminder_loop.start()

    async def cog_unload(self):
        if self._reminder_loop.is_running():
            self._reminder_loop.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("RemindMe loaded.")

    # ---- Create -----------------------------------------------------------

    async def _create(self, guild, user, channel_id, raw, reply):
        due, text = parse_when(raw)
        if due is None:
            await reply(text)
            return
        now = time.time()
        delay = due - now
        if delay < MIN_DELAY_SECONDS:
            await reply("That's basically now. Give me at least a few seconds.")
            return
        if delay > MAX_DELAY_SECONDS:
            await reply("I'm not remembering anything for more than a year. Neither should you.")
            return
        if len(text) > MAX_TEXT_LEN:
            await reply(f"Keep it under {MAX_TEXT_LEN} characters — this is a reminder, not a memoir.")
            return
        active = [k for k in kv_get_all(guild.id, user.id, NAMESPACE) if k.startswith("r")]
        if len(active) >= MAX_ACTIVE_PER_USER:
            await reply(f"You already have {MAX_ACTIVE_PER_USER} reminders pending. Cancel one with `!cancelreminder <id>`.")
            return
        rid = kv_incr(guild.id, 0, NAMESPACE, "next_id")
        kv_set(guild.id, user.id, NAMESPACE, f"r{rid}", json.dumps({
            "due": int(due),
            "channel_id": channel_id,
            "text": text,
            "created": int(now),
        }))
        what = f": {text}" if text else ""
        await reply(f"⏰ Got it — reminder **#{rid}** set for <t:{int(due)}:f> (<t:{int(due)}:R>){what}")

    @commands.command(name="remindme")
    @commands.guild_only()
    async def remindme_prefix(self, ctx, *, when_and_text: str):
        await self._create(ctx.guild, ctx.author, ctx.channel.id, when_and_text, ctx.send)

    @remindme_prefix.error
    async def remindme_prefix_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(USAGE)
        else:
            raise error

    # ---- List -------------------------------------------------------------

    async def _list(self, guild, user, reply):
        entries = []
        for key, value in kv_get_all(guild.id, user.id, NAMESPACE).items():
            if not key.startswith("r"):
                continue
            try:
                data = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                continue
            entries.append((data["due"], key[1:], data.get("text", "")))
        if not entries:
            await reply("No pending reminders. Your future is a blank page.")
            return
        entries.sort()
        lines = [
            f"**#{rid}** — <t:{due}:R> (<t:{due}:f>)" + (f" — {text}" if text else "")
            for due, rid, text in entries
        ]
        await reply("⏰ **Your reminders:**\n" + "\n".join(lines))

    @commands.command(name="reminders")
    @commands.guild_only()
    async def reminders_prefix(self, ctx):
        await self._list(ctx.guild, ctx.author, ctx.send)

    # ---- Cancel -----------------------------------------------------------

    async def _cancel(self, guild, user, rid, reply):
        key = f"r{rid}"
        if kv_get(guild.id, user.id, NAMESPACE, key) is None:
            await reply(f"You don't have a reminder **#{rid}**. Check `!reminders`.")
            return
        kv_delete(guild.id, user.id, NAMESPACE, key)
        await reply(f"🗑️ Reminder **#{rid}** cancelled. Forgotten, like it never mattered.")

    @commands.command(name="cancelreminder")
    @commands.guild_only()
    async def cancel_prefix(self, ctx, reminder_id: int):
        await self._cancel(ctx.guild, ctx.author, reminder_id, ctx.send)

    @cancel_prefix.error
    async def cancel_prefix_error(self, ctx, error):
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send("Usage: `!cancelreminder <id>` — ids are in `!reminders`.")
        else:
            raise error

    # ---- Delivery loop ----------------------------------------------------

    @tasks.loop(seconds=SCAN_INTERVAL_SECONDS)
    async def _reminder_loop(self):
        now = int(time.time())
        for guild in list(self.bot.guilds):
            try:
                all_rows = kv_all_in_namespace(guild.id, NAMESPACE)
            except Exception:
                logger.exception(f"reminder loop: kv scan failed for guild {guild.id}")
                continue
            for user_id, rows in all_rows.items():
                if user_id == 0:
                    continue  # guild-scoped counter row, not a person
                for key, value in rows.items():
                    if not key.startswith("r"):
                        continue
                    try:
                        data = json.loads(value)
                        due = int(data["due"])
                    except (json.JSONDecodeError, TypeError, KeyError, ValueError):
                        logger.warning(f"reminder loop: dropping malformed row {key} for user {user_id}")
                        kv_delete(guild.id, user_id, NAMESPACE, key)
                        continue
                    if due > now:
                        continue
                    # Delete first so a send failure can't make it fire every scan.
                    kv_delete(guild.id, user_id, NAMESPACE, key)
                    await self._deliver(guild, user_id, data)

    async def _deliver(self, guild, user_id, data):
        text = data.get("text", "")
        created = data.get("created")
        set_note = f" (set <t:{int(created)}:R>)" if created else ""
        what = f": **{text}**" if text else ". You never said what about. Hope you remember."
        msg = f"⏰ <@{user_id}> Reminder{set_note}{what}"
        channel = self.bot.get_channel(data.get("channel_id") or 0)
        if channel is not None:
            try:
                await channel.send(msg)
                return
            except (discord.Forbidden, discord.HTTPException):
                pass
        # Channel gone or unpostable — fall back to a DM.
        try:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            await user.send(f"{msg}\n-# (Couldn't post in the original channel in {guild.name}.)")
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            logger.warning(f"reminder loop: couldn't deliver reminder to user {user_id} in guild {guild.id}")

    @_reminder_loop.before_loop
    async def before_reminder_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(RemindMe(bot))
