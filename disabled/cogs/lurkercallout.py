import discord
from discord.ext import commands
from discord.ext import tasks
import random
from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)

# How often to trigger (days)
MIN_INTERVAL_DAYS = 5
MAX_INTERVAL_DAYS = 14

CALLOUT_MESSAGES = [
    "Hey {user}, we know you're here. We can see you.",
    "{user} has been real quiet lately... too quiet... 👀",
    "Just checking in on {user} who hasn't said a word. We see you lurking.",
    "Friendly reminder that {user} exists. They haven't spoken since the incident.",
    "{user} is online right now reading everything and saying nothing. Suspicious.",
    "I'm legally required to inform you that {user} is lurking in this channel.",
    "Sources confirm {user} has been watching this chat in silence. Thoughts?",
    "Spotted: {user} lurking in the shadows. Say something coward.",
    "{user} really out here reading every message and contributing nothing. Iconic.",
    "The ghost of {user} haunts this server. They see all. They say nothing.",
    "POV: you're {user} reading this and panicking right now.",
    "Breaking: {user} has been declared legally lurking. The court has spoken.",
    "If {user} doesn't speak in the next 24 hours we're sending a search party.",
    "I've seen {user} online 47 times this week and they haven't said a single word.",
    "{user} is giving strong 'I'm just here so I don't get fined' energy.",
    "We need to talk about {user}'s lurking. It's reaching unprecedented levels.",
    "I have it on good authority that {user} is reading this right now. Wave hi.",
    "{user} really said 'I'll just observe' and committed fully. Respect honestly.",
    "Day 47 of {user} not speaking. The plants are thriving but the vibes are off.",
    "Someone check on {user}. They're either lurking or in witness protection.",
]


class LurkerCallout(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._next_fire = None
        self._schedule_next()

    def _schedule_next(self):
        days = random.randint(MIN_INTERVAL_DAYS, MAX_INTERVAL_DAYS)
        extra_hours = random.randint(0, 23)
        self._next_fire = datetime.now(timezone.utc) + timedelta(days=days, hours=extra_hours)
        logger.info(f"Next lurker callout scheduled in {days} days and {extra_hours} hours")

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Lurker Callout module has been loaded")
        if not self.lurker_check.is_running():
            self.lurker_check.start()

    def cog_unload(self):
        self.lurker_check.cancel()

    async def _find_lurker(self, guild: discord.Guild) -> discord.Member | None:
        """Find a member who hasn't spoken recently."""
        # Get members who are online or idle but not bots
        potential = [
            m for m in guild.members
            if not m.bot and m.status != discord.Status.offline
        ]
        if not potential:
            # Fall back to all non-bot members
            potential = [m for m in guild.members if not m.bot]
        if not potential:
            return None

        # Pick a random channel to check history
        channels = [
            ch for ch in guild.text_channels
            if ch.permissions_for(guild.me).read_message_history
        ]
        if not channels:
            return random.choice(potential)

        # Find who has NOT spoken in the last 7 days across a few channels
        recent_speakers = set()
        sample_channels = random.sample(channels, min(5, len(channels)))
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)

        for ch in sample_channels:
            try:
                async for msg in ch.history(limit=200, after=cutoff):
                    if not msg.author.bot:
                        recent_speakers.add(msg.author.id)
            except (discord.Forbidden, discord.HTTPException):
                continue

        # Filter to people who haven't spoken
        lurkers = [m for m in potential if m.id not in recent_speakers]

        if lurkers:
            return random.choice(lurkers)
        # If everyone has spoken recently, just pick someone random
        return random.choice(potential)

    @tasks.loop(hours=24)
    async def lurker_check(self):
        if not self._next_fire or datetime.now(timezone.utc) < self._next_fire:
            return

        guilds = [g for g in self.bot.guilds if g.text_channels]
        if not guilds:
            self._schedule_next()
            return

        guild = random.choice(guilds)

        # Find a lurker
        lurker = await self._find_lurker(guild)
        if not lurker:
            self._schedule_next()
            return

        # Pick a channel to call them out in
        channels = [
            ch for ch in guild.text_channels
            if ch.permissions_for(guild.me).send_messages
        ]
        if not channels:
            self._schedule_next()
            return

        # Prefer general/main channels
        preferred = [ch for ch in channels if any(name in ch.name.lower() for name in ["general", "chat", "main", "lounge"])]
        channel = random.choice(preferred) if preferred else random.choice(channels)

        callout = random.choice(CALLOUT_MESSAGES).format(user=lurker.mention)
        try:
            await channel.send(callout)
            logger.info(f"Lurker callout: {lurker.display_name} in #{channel.name}")
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.error(f"Lurker callout failed: {e}")

        self._schedule_next()

    @lurker_check.before_loop
    async def before_lurker_check(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(LurkerCallout(bot))
