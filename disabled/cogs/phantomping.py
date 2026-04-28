import discord
from discord.ext import commands
from discord.ext import tasks
import random
from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)

# Triggers every 1-4 days
MIN_INTERVAL_DAYS = 1
MAX_INTERVAL_DAYS = 4

INITIAL_MESSAGES = [
    "who pinged me?",
    "who just pinged me",
    "someone just pinged me. who was it.",
    "I swear someone just @ me",
    "did someone just ping me or am I losing it",
    "yo who pinged",
    "I literally just got a notification from this channel. who.",
    "ok which one of you pinged me",
    "I HEARD THAT PING. SHOW YOURSELF.",
    "my notifications went off. who did it.",
]

FOLLOWUP_MESSAGES = [
    "I know I saw it. Someone said my name.",
    "Don't gaslight me. I saw the notification.",
    "I have proof. Well, I did. It's gone now.",
    "You know what, forget it.",
    "I'm watching you all.",
    "Fine. Pretend nothing happened. I'll remember this.",
    "This is exactly what a pinger would say.",
    "The notification is GONE but I FELT it.",
    "Ok I might be going insane. Carry on.",
    "I'll let it slide this time. But I'm keeping score.",
    "Mark my words, I will find out who it was.",
    "You can delete the message but you can't delete the TRUTH.",
    "My trust in this server has decreased by 12%.",
    "I'm not crazy. YOU'RE crazy. All of you.",
    "Whatever. I didn't even want to be pinged anyway.",
]


class PhantomPing(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._next_fire = None
        self._schedule_next()

    def _schedule_next(self):
        days = random.randint(MIN_INTERVAL_DAYS, MAX_INTERVAL_DAYS)
        extra_hours = random.randint(0, 23)
        self._next_fire = datetime.now(timezone.utc) + timedelta(days=days, hours=extra_hours)
        logger.info(f"Next phantom ping scheduled in {days} days and {extra_hours} hours")

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Phantom Ping module has been loaded")
        if not self.phantom_check.is_running():
            self.phantom_check.start()

    def cog_unload(self):
        self.phantom_check.cancel()

    @tasks.loop(hours=24)
    async def phantom_check(self):
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

        # Pick a channel that's had recent activity
        active_channels = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
        for ch in channels:
            try:
                async for msg in ch.history(limit=1, after=cutoff):
                    active_channels.append(ch)
                    break
            except (discord.Forbidden, discord.HTTPException):
                continue

        channel = random.choice(active_channels) if active_channels else random.choice(channels)

        try:
            await channel.send(random.choice(INITIAL_MESSAGES))

            # 50% chance of a paranoid followup after a delay
            if random.random() < 0.5:
                import asyncio
                await asyncio.sleep(random.randint(15, 60))
                await channel.send(random.choice(FOLLOWUP_MESSAGES))

            logger.info(f"Phantom ping in #{channel.name}")
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.error(f"Phantom ping failed: {e}")

        self._schedule_next()

    @phantom_check.before_loop
    async def before_phantom_check(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(PhantomPing(bot))
