import discord
from discord.ext import commands
from discord import app_commands
import random
import hashlib
import logging

logger = logging.getLogger(__name__)

MOTIONS = ['neighs', 'negotiates', 'ogles', 'neglects', 'quavers', 'scowls', 'telephones', 'salivates',
           'satisfys', 'sheathes', 'traipses', 'parades', 'offends', 'manipulates', 'compiles', 'mispronounces',
           'murders', 'runs', 'vaginas', 'locks', 'whoolies', 'bangs', 'drops', 'itches', 'hugs', 'bakes',
           'fastens', 'grabs', 'jumps', 'jogs', 'questions', 'rinses', 'opens', 'knits', 'addresses', 'bemoans',
           'beseeches', 'chastises', 'deciphers', 'dawdles', 'dangles', 'cheers', 'decrys', 'antagonises',
           'apologises', 'assaults', 'brandishes', 'brags', 'clucks', 'digests', 'emphasises', 'ensnares',
           'gravitates', 'hogs', 'head-butts', 'butts', 'honks', 'fingers', 'eviscerates', 'excavates', 'folds',
           'exclaims', 'hypnotises', 'interviews', 'raises', 'flaps', 'wobbles', 'shakes', 'gyrates',
           'helicopters', 'flops', 'agitates', 'waves his donger in the air like he just dont care',
           'blipps', 'reiterates', 'drives', 'leans', 'polishes', 'chokes', 'announces', 'applauds', 'compiles',
           'displays', 'drags', 'greases', 'intensifies', 'irritates', 'loves', 'manipulates', 'overflows',
           'preaches', 'queues', 'screams', 'thaws', 'thrusts', 'tickles', 'degloves', 'springs', 'stimulates',
           'washes', 'inserts', 'bequeaths']

# Measurement chance (30%)
MEASURE_CHANCE = 0.30

UNITS = [
    ("inches", 0.5, 14.0),
    ("cm", 1.0, 35.0),
    ("millimeters", 10.0, 350.0),
    ("football fields", 0.00001, 0.0005),
    ("bananas", 0.2, 5.0),
    ("hot dogs", 0.3, 6.0),
    ("pixels", 5.0, 500.0),
    ("light years", 0.0, 0.0000001),
]

SMALL_ROASTS = [
    "That's... that's it? My condolences.",
    "The doctor said it's technically still there.",
    "I've seen bigger on a Ken doll.",
    "Is that a donger or a belly button?",
    "You should sue whoever did that to you.",
    "911? I'd like to report a missing donger.",
    "Bro that's not a donger that's a donglet.",
    "In some cultures that's considered... no, it's small everywhere.",
    "I've seen more impressive sticks on the ground.",
    "Are you cold or is it always like that?",
    "That's what we in the business call a 'fun size'.",
    "The magnifying glass industry thanks you for your business.",
    "Built for aerodynamics, not for show.",
    "That's not a measurement, that's a rounding error.",
    "My grandma has a bigger one and she's been dead for 10 years.",
]

MEDIUM_COMMENTS = [
    "Perfectly average. Just like everything else about you.",
    "Mid. Just like your K/D ratio.",
    "The Honda Civic of dongers. Reliable, boring.",
    "It's... fine. It's fine. Stop asking.",
    "Congratulations, you're statistically unremarkable.",
    "Not bad, not good. The participation trophy of dongers.",
    "Your donger said 'meh' and so do I.",
    "It exists. That's the nicest thing I can say.",
    "Aggressively average. Like room temperature water.",
    "The dictionary called, they want to use this as the definition of 'mediocre'.",
]

BIG_COMMENTS = [
    "GOOD LORD. Put that thing away, there are children here.",
    "That's not a donger, that's a weapon of mass destruction.",
    "Bro is packing a THIRD LEG.",
    "Someone call Guinness, we have a new record.",
    "That thing has its own zip code.",
    "NASA wants to study your donger.",
    "How do you even walk?",
    "That's not a donger, that's a baseball bat.",
    "Bro's donger has a donger.",
    "The ground shakes when this thing moves.",
    "You need a permit for that.",
    "That donger has its own gravitational pull.",
    "This is a certified WEAPON.",
]


def _get_donger_size(user_id: int) -> float:
    """Deterministic 'size' for a user. Same user always gets the same number."""
    h = hashlib.sha256(str(user_id).encode()).hexdigest()
    # Use first 8 hex chars to get a value 0.0-1.0
    return int(h[:8], 16) / 0xFFFFFFFF


def _build_donger_art(size_pct: float) -> str:
    """Build an ASCII donger scaled to size."""
    shaft_len = max(1, int(size_pct * 12))
    return "8" + ("=" * shaft_len) + "D~ ~ ~"


def _measure(user_id: int) -> str:
    """Generate a deterministic measurement with commentary."""
    size_pct = _get_donger_size(user_id)
    unit_name, low, high = random.choice(UNITS)
    measurement = round(low + (size_pct * (high - low)), 2)

    art = _build_donger_art(size_pct)

    if size_pct < 0.3:
        comment = random.choice(SMALL_ROASTS)
    elif size_pct < 0.7:
        comment = random.choice(MEDIUM_COMMENTS)
    else:
        comment = random.choice(BIG_COMMENTS)

    return f"{art}\n📏 **{measurement} {unit_name}**\n*{comment}*"


class Donger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Donger module has been loaded")

    def _donger_response(self, author: discord.Member, member: discord.Member = None) -> str:
        if member == author:
            motion = random.choice(MOTIONS)
            msg = f"{author.mention} {motion} with their own donger 8====D~ ~ ~"
        elif member:
            motion = random.choice(MOTIONS)
            msg = f"{author.mention} {motion} their donger at {member.mention} 8====D~ ~ ~"
        else:
            msg = "8====D~ ~ ~"

        # Random chance to add a measurement
        target = member if member else author
        if random.random() < MEASURE_CHANCE:
            msg += f"\n\n*Wait... hold on... let me get the tape measure...*\n{_measure(target.id)}"

        return msg

    @commands.command(aliases=['donger'])
    async def Donger(self, ctx, member: discord.Member = None):
        await ctx.send(self._donger_response(ctx.author, member))

    @app_commands.command(name="donger", description="Raise your donger")
    @app_commands.describe(member="Target of your donger (optional)")
    async def donger_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        await interaction.response.send_message(self._donger_response(interaction.user, member))

    @commands.command(aliases=['dongsize', 'pp'])
    async def measure(self, ctx, member: discord.Member = None):
        """Measure someone's donger. Science."""
        target = member or ctx.author
        await ctx.send(f"{target.mention}'s official measurement:\n{_measure(target.id)}")

    @app_commands.command(name="measure", description="Officially measure someone's donger")
    @app_commands.describe(member="Whose donger to measure (defaults to you)")
    async def measure_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        await interaction.response.send_message(f"{target.mention}'s official measurement:\n{_measure(target.id)}")


async def setup(bot):
    await bot.add_cog(Donger(bot))
