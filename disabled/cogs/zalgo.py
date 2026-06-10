import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

logger = logging.getLogger(__name__)

# Unicode combining diacritical marks (0x0300-0x036F)
COMBINING_MARKS_ABOVE = [chr(c) for c in range(0x0300, 0x0340)]
COMBINING_MARKS_BELOW = [chr(c) for c in range(0x0316, 0x0340)]
COMBINING_MARKS_MIDDLE = [chr(c) for c in range(0x0340, 0x0370)]


def _zalgoify(text: str, intensity: int = 2) -> str:
    """Convert text to Zalgo text with the given intensity (1-3)."""
    intensity = max(1, min(3, intensity))
    marks_per_char = {1: (1, 3), 2: (3, 6), 3: (6, 12)}
    lo, hi = marks_per_char[intensity]
    result = []
    for char in text:
        if char.isspace():
            result.append(char)
            continue
        result.append(char)
        num_above = random.randint(lo, hi)
        num_below = random.randint(lo, hi)
        num_middle = random.randint(0, lo)
        for _ in range(num_above):
            result.append(random.choice(COMBINING_MARKS_ABOVE))
        for _ in range(num_below):
            result.append(random.choice(COMBINING_MARKS_BELOW))
        for _ in range(num_middle):
            result.append(random.choice(COMBINING_MARKS_MIDDLE))
    output = "".join(result)
    if len(output) > 2000:
        output = output[:2000]
    return output


class Zalgo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Zalgo module has been loaded")

    @commands.command()
    async def zalgo(self, ctx, intensity: int = 2, *, text: str):
        """Convert text to Zalgo text. Usage: !zalgo [1-3] <text>"""
        await ctx.send(_zalgoify(text, intensity))

    @app_commands.command(name="zalgo", description="Convert text to cursed Zalgo text")
    @app_commands.describe(
        text="The text to zalgoify",
        intensity="How cursed (1=mild, 2=medium, 3=extreme). Default 2."
    )
    async def zalgo_slash(self, interaction: discord.Interaction, text: str, intensity: int = 2):
        await interaction.response.send_message(_zalgoify(text, intensity))


async def setup(bot):
    await bot.add_cog(Zalgo(bot))
