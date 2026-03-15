import discord
from discord.ext import commands
from discord import app_commands
from discord.ext import tasks
import os
import random
from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data_files")

# Users to never target (matched by username or display name, case-insensitive)
EXCLUDED_USERNAMES = {
    "kev2tall8546",
    "kev2tall",
}

# How often to trigger (days)
MIN_INTERVAL_DAYS = 3
MAX_INTERVAL_DAYS = 60


def _load_lines(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.error(f"Data file not found: {filepath}")
        return []


class Unhinged(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.replies = _load_lines(os.path.join(DATA_DIR, "unhinged_replies.txt"))
        self._next_fire = None
        self._schedule_next()

    def _schedule_next(self):
        """Schedule the next unhinged reply at a random future time."""
        days = random.randint(MIN_INTERVAL_DAYS, MAX_INTERVAL_DAYS)
        # Add random hours so it's not always at the same time of day
        extra_hours = random.randint(0, 23)
        self._next_fire = datetime.now(timezone.utc) + timedelta(days=days, hours=extra_hours)
        logger.info(f"Next unhinged reply scheduled in {days} days and {extra_hours} hours")

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Unhinged module has been loaded")
        if not self.unhinged_check.is_running():
            self.unhinged_check.start()

    def cog_unload(self):
        self.unhinged_check.cancel()

    @tasks.loop(hours=24)
    async def unhinged_check(self):
        """Periodically check if it's time to go unhinged."""
        if not self._next_fire or datetime.now(timezone.utc) < self._next_fire:
            return
        if not self.replies:
            return

        # Pick a random guild the bot is in
        guilds = [g for g in self.bot.guilds if g.text_channels]
        if not guilds:
            return
        guild = random.choice(guilds)

        # Pick a random text channel the bot can read and send in
        channels = [
            ch for ch in guild.text_channels
            if ch.permissions_for(guild.me).read_message_history
            and ch.permissions_for(guild.me).send_messages
        ]
        if not channels:
            self._schedule_next()
            return

        channel = random.choice(channels)

        # Search for a random old message to reply to
        target_msg = await self._find_target_message(channel)
        if target_msg:
            reply_text = random.choice(self.replies)
            try:
                await target_msg.reply(reply_text, mention_author=False)
                logger.info(f"Unhinged reply sent in #{channel.name} to {target_msg.author.display_name}")
            except (discord.Forbidden, discord.HTTPException) as e:
                logger.error(f"Failed to send unhinged reply: {e}")

        self._schedule_next()

    async def _find_target_message(self, channel: discord.TextChannel) -> discord.Message | None:
        """Find a random historical message to reply to, excluding bots and excluded users."""
        now = datetime.now(timezone.utc)

        for _ in range(5):
            # Pick a random time in the last 90 days
            random_offset = random.randint(1, 90)
            random_date = now - timedelta(days=random_offset)

            try:
                candidates = []
                async for msg in channel.history(limit=100, after=random_date, oldest_first=True):
                    author_names = {msg.author.name.lower(), msg.author.display_name.lower()}
                    if (msg.author.bot
                            or author_names & EXCLUDED_USERNAMES
                            or not msg.content
                            or msg.content.startswith(("!", "/"))):
                        continue
                    # Skip very short messages
                    if len(msg.content) < 5:
                        continue
                    candidates.append(msg)
                    if len(candidates) >= 15:
                        break

                if candidates:
                    return random.choice(candidates)
            except (discord.Forbidden, discord.HTTPException):
                continue

        return None

    @unhinged_check.before_loop
    async def before_unhinged_check(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Unhinged(bot))
