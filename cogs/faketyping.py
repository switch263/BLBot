import discord
from discord.ext import commands
from discord.ext import tasks
import random
import asyncio
from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)

# How often to trigger (hours)
MIN_INTERVAL_HOURS = 4
MAX_INTERVAL_HOURS = 48

BAIL_MESSAGES = [
    "nvm",
    "actually forget it",
    "wait no",
    "you know what, never mind",
    "...",
    "I forgor",
    "hold on let me think about this",
    "actually I don't remember what I was going to say",
    "ok I had something but it's gone now",
    "",  # empty = just stop typing with no message (ghosting)
    "",
    "",
    "",
]


class FakeTyping(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._next_fire = None
        self._schedule_next()

    def _schedule_next(self):
        hours = random.randint(MIN_INTERVAL_HOURS, MAX_INTERVAL_HOURS)
        self._next_fire = datetime.now(timezone.utc) + timedelta(hours=hours)
        logger.debug(f"Next fake typing scheduled in {hours} hours")

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Fake Typing module has been loaded")
        if not self.typing_check.is_running():
            self.typing_check.start()

    def cog_unload(self):
        self.typing_check.cancel()

    @tasks.loop(hours=1)
    async def typing_check(self):
        if not self._next_fire or datetime.now(timezone.utc) < self._next_fire:
            return

        guilds = [g for g in self.bot.guilds if g.text_channels]
        if not guilds:
            self._schedule_next()
            return

        guild = random.choice(guilds)
        channels = [
            ch for ch in guild.text_channels
            if ch.permissions_for(guild.me).send_messages
        ]
        if not channels:
            self._schedule_next()
            return

        channel = random.choice(channels)
        typing_duration = random.randint(15, 35)

        try:
            async with channel.typing():
                await asyncio.sleep(typing_duration)

            bail = random.choice(BAIL_MESSAGES)
            if bail:  # empty string = just ghost them
                await channel.send(bail)
                logger.info(f"Fake typing in #{channel.name}: sent '{bail}'")
            else:
                logger.info(f"Fake typing in #{channel.name}: ghosted (no message)")
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.error(f"Fake typing failed: {e}")

        self._schedule_next()

    @typing_check.before_loop
    async def before_typing_check(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(FakeTyping(bot))
