import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

logger = logging.getLogger(__name__)

THEY = [
    "The government", "Big Pharma", "The Illuminati", "NASA", "The lizard people",
    "IKEA", "The Amish", "Walmart greeters", "The deep state", "Your HOA",
    "The squirrels", "Discord moderators", "The postal service", "Dentists",
    "Mattress Firm", "The birds", "Ronald McDonald", "The moon",
    "Time travelers", "Dolphins", "Your WiFi router", "The Bermuda Triangle",
    "Chuck E. Cheese", "The Keebler Elves", "Canada", "Pigeons",
    "The ghost of Blockbuster Video", "Maruchan Ramen", "Big Spoon",
]

VERBS = [
    "is hiding", "has been secretly deploying", "is mass-producing",
    "has been weaponizing", "is covering up the existence of",
    "is secretly funding", "is putting", "has been cloning",
    "is reverse-engineering", "is using", "has been hoarding",
    "is smuggling", "has been breeding", "is distributing",
    "is brainwashing people with", "replaced all the world's supply of",
    "is teleporting", "has been microdosing the water supply with",
]

OBJECTS = [
    "WiFi-powered bees", "sentient furniture", "5G-enhanced pigeons",
    "mind-control fluoride", "interdimensional hot dogs", "synthetic clouds",
    "AI-generated weather", "microscopic drones disguised as dust",
    "chemtrail-infused energy drinks", "cloned celebrities",
    "time-traveling roomba prototypes", "emotion-detecting toasters",
    "self-aware CAPTCHA tests", "anti-gravity mayonnaise",
    "memory-erasing hand sanitizer", "GPS-tracked geese",
    "holographic trees", "quantum-entangled socks (that's why they disappear)",
    "surveillance crickets", "mind-reading pizza toppings",
    "invisible toll booths", "cryptocurrency-mining hamster wheels",
    "mood-altering font choices", "dream-recording pillows",
    "telekinetic housecats", "thought-suppressing elevator music",
]

REASONS = [
    "to control the population",
    "to keep us from discovering the truth about mattress stores",
    "because they lost a bet in 1987",
    "to distract us from the real flat earth evidence",
    "to fund their underground mole people empire",
    "because the prophecy demanded it",
    "to prevent anyone from reaching level 100",
    "as part of a 400-year-old revenge plot",
    "to power a secret base under every Applebee's",
    "because the simulation is running out of RAM",
    "to prepare for the Great Reckoning of 2029",
    "and honestly? It's working",
    "and nobody is talking about it",
    "but I saw the documents. I SAW THEM.",
    "to keep gas station sushi prices artificially low",
    "and Big Spoon doesn't want you to know",
    "to ensure no one ever finds the missing socks",
    "to maintain the pickle jar difficulty level",
]

CLOSERS = [
    "Wake up, sheeple.",
    "Do your own research.",
    "They can't silence all of us.",
    "I'm not crazy. YOU'RE crazy.",
    "Connect the dots, people.",
    "Follow the money.",
    "This is all documented on a blog I can't find anymore.",
    "My cousin's friend's barber confirmed this.",
    "The evidence is literally everywhere if you open your third eye.",
    "I've said too much already.",
    "If I go missing, you know why.",
    "Think about it.",
    "",
]


class Conspiracy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Conspiracy module has been loaded")

    def _generate(self) -> discord.Embed:
        theory = f"{random.choice(THEY)} {random.choice(VERBS)} {random.choice(OBJECTS)} {random.choice(REASONS)}."
        closer = random.choice(CLOSERS)

        embed = discord.Embed(
            title="THEY DON'T WANT YOU TO KNOW THIS",
            description=f"{theory}\n\n*{closer}*" if closer else theory,
            color=discord.Color.dark_red()
        )
        embed.set_footer(text="Source: a dream I had")
        return embed

    @commands.command(aliases=['tinfoil'])
    async def conspiracy(self, ctx):
        """Generate an unhinged conspiracy theory."""
        await ctx.send(embed=self._generate())

    @app_commands.command(name="conspiracy", description="Generate an unhinged conspiracy theory")
    async def conspiracy_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self._generate())


async def setup(bot):
    await bot.add_cog(Conspiracy(bot))
