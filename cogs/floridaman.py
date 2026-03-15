import discord
from discord.ext import commands
from discord import app_commands
import random
from datetime import date
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


class FloridaMan(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.actions = _load_lines(os.path.join(DATA_DIR, "floridaman_actions.txt"))
        self.footers = _load_lines(os.path.join(DATA_DIR, "floridaman_footers.txt"))

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Florida Man module has been loaded")

    def _generate(self) -> discord.Embed:
        today = date.today().strftime("%B %d")

        if not self.actions:
            embed = discord.Embed(
                title=f"FLORIDA MAN \u2014 {today}",
                description="**Florida Man could not be reached for comment. (Data file missing!)**",
                color=discord.Color.orange()
            )
            return embed

        action = random.choice(self.actions)
        headline = f"Florida Man {action}"

        embed = discord.Embed(
            title=f"FLORIDA MAN \u2014 {today}",
            description=f"**{headline}**",
            color=discord.Color.orange()
        )
        if self.footers:
            embed.set_footer(text=random.choice(self.footers))
        return embed

    @commands.command(aliases=['florida'])
    async def floridaman(self, ctx):
        """Generate a random Florida Man headline."""
        await ctx.send(embed=self._generate())

    @app_commands.command(name="floridaman", description="Generate a random Florida Man headline")
    async def floridaman_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self._generate())


async def setup(bot):
    await bot.add_cog(FloridaMan(bot))
