import discord
from discord.ext import commands
from discord.ext import tasks
import random
from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)

# Triggers every 2-7 days
MIN_INTERVAL_DAYS = 2
MAX_INTERVAL_DAYS = 7

FAKE_EVENTS = [
    "said they could eat {number} hot dogs in one sitting",
    "admitted they sleep with a nightlight",
    "said they've never seen {movie}",
    "claimed they could beat everyone here in a fight",
    "confessed they don't know how to ride a bike",
    "said {food} is the best food ever made",
    "announced they were moving to {place}",
    "tried to convince everyone that birds aren't real",
    "said they shower with socks on",
    "admitted they don't know the alphabet past the letter Q",
    "declared that {day} is the best day of the week",
    "said they eat cereal with water",
    "claimed they once fought a raccoon and lost",
    "told everyone they iron their jeans",
    "said they think {movie} is overrated",
    "admitted they still use Internet Explorer",
    "confessed they put ketchup on everything including cereal",
    "said they've never used a microwave",
    "claimed to have arm wrestled a bear",
    "announced they were quitting gaming forever (lasted 2 hours)",
    "said they think {place} doesn't actually exist",
    "admitted they cry during car commercials",
    "said they've been pronouncing '{word}' wrong their entire life",
    "claimed they have a pet rock named Gerald",
    "told everyone they eat pizza with a fork",
    "said they think the moon is just the back of the sun",
    "confessed they've never finished a glass of water",
    "claimed they can communicate with pigeons",
    "admitted they google how to spell 'Wednesday' every single time",
    "said they think {food} is disgusting and should be illegal",
]

MOVIES = [
    "Star Wars", "The Lion King", "Shrek", "Toy Story", "Finding Nemo",
    "The Matrix", "Titanic", "Jurassic Park", "Harry Potter", "Lord of the Rings",
    "The Avengers", "Frozen", "The Dark Knight", "Forrest Gump", "The Godfather",
]

FOODS = [
    "pizza", "tacos", "sushi", "mac and cheese", "chicken nuggets",
    "pineapple on pizza", "gas station sushi", "cold pizza", "plain rice",
    "untoasted bread", "room temperature soup", "wet cereal", "burnt toast",
]

PLACES = [
    "Ohio", "Florida", "Wyoming", "Canada", "Australia",
    "the moon", "Delaware", "Atlantis", "the shadow realm", "Gary, Indiana",
]

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

WORDS = [
    "quinoa", "worcestershire", "colonel", "epitome", "hyperbole",
    "GIF", "mischievous", "espresso", "nuclear", "library",
]

REACTIONS = [
    "That was wild.",
    "Still think about it sometimes.",
    "We never recovered from that.",
    "Classic.",
    "I have screenshots.",
    "Legendary moment honestly.",
    "Nobody talks about this enough.",
    "I still can't believe it.",
    "The server was never the same after that.",
    "We all just let it happen.",
]


class SelectiveMemory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._next_fire = None
        self._schedule_next()

    def _schedule_next(self):
        days = random.randint(MIN_INTERVAL_DAYS, MAX_INTERVAL_DAYS)
        extra_hours = random.randint(0, 23)
        self._next_fire = datetime.now(timezone.utc) + timedelta(days=days, hours=extra_hours)
        logger.info(f"Next selective memory scheduled in {days} days and {extra_hours} hours")

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Selective Memory module has been loaded")
        if not self.memory_check.is_running():
            self.memory_check.start()

    def cog_unload(self):
        self.memory_check.cancel()

    def _generate_memory(self, member_mention: str) -> str:
        event = random.choice(FAKE_EVENTS)
        event = event.replace("{number}", str(random.randint(15, 73)))
        event = event.replace("{movie}", random.choice(MOVIES))
        event = event.replace("{food}", random.choice(FOODS))
        event = event.replace("{place}", random.choice(PLACES))
        event = event.replace("{day}", random.choice(DAYS))
        event = event.replace("{word}", random.choice(WORDS))
        reaction = random.choice(REACTIONS)
        return f"Remember when {member_mention} {event}? {reaction}"

    @tasks.loop(hours=24)
    async def memory_check(self):
        if not self._next_fire or datetime.now(timezone.utc) < self._next_fire:
            return

        guilds = [g for g in self.bot.guilds if g.text_channels]
        if not guilds:
            self._schedule_next()
            return

        guild = random.choice(guilds)

        # Pick a random non-bot member
        members = [m for m in guild.members if not m.bot]
        if not members:
            self._schedule_next()
            return
        member = random.choice(members)

        # Pick a channel (prefer general/chat)
        channels = [
            ch for ch in guild.text_channels
            if ch.permissions_for(guild.me).send_messages
        ]
        if not channels:
            self._schedule_next()
            return

        preferred = [ch for ch in channels if any(name in ch.name.lower() for name in ["general", "chat", "main", "lounge"])]
        channel = random.choice(preferred) if preferred else random.choice(channels)

        memory = self._generate_memory(member.mention)
        try:
            await channel.send(memory)
            logger.info(f"Selective memory about {member.display_name} in #{channel.name}")
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.error(f"Selective memory failed: {e}")

        self._schedule_next()

    @memory_check.before_loop
    async def before_memory_check(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(SelectiveMemory(bot))
