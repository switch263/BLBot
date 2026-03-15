import discord
from discord.ext import commands
from discord import app_commands
import random
import os
import logging

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data_files")


def _load_lines(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.error(f"Data file not found: {filepath}")
        return []


class Excuse(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.starters = _load_lines(os.path.join(DATA_DIR, "excuse_starters.txt"))
        self.subjects = _load_lines(os.path.join(DATA_DIR, "excuse_subjects.txt"))
        self.actions = _load_lines(os.path.join(DATA_DIR, "excuse_actions.txt"))
        self.extras = _load_lines(os.path.join(DATA_DIR, "excuse_extras.txt"))

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Excuse module has been loaded")

    def _generate(self) -> str:
        if not self.starters or not self.subjects or not self.actions:
            return "I had an excuse but I lost it. (Data file missing!)"
        starter = random.choice(self.starters)
        subject = random.choice(self.subjects)
        action = random.choice(self.actions)
        extra = random.choice(self.extras) if self.extras else ""
        excuse = f"{starter} {subject} {action}."
        if extra:
            excuse += f" {extra}"
        return excuse

    @commands.command(aliases=['excuseme'])
    async def excuse(self, ctx):
        """Generate an absurd excuse for being late or AFK."""
        await ctx.send(self._generate())

    @app_commands.command(name="excuse", description="Generate an absurd excuse for being late or AFK")
    async def excuse_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(self._generate())


async def setup(bot):
    await bot.add_cog(Excuse(bot))
