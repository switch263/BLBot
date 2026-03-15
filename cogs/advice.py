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


class BadAdvice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bad_advice = _load_lines(os.path.join(DATA_DIR, "bad_advice.txt"))

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Bad Advice module has been loaded")

    @commands.command(aliases=['badadvice', 'lifeadvice', 'lifetip'])
    async def advice(self, ctx):
        """Get some terrible life advice."""
        if not self.bad_advice:
            await ctx.send("Fresh out of bad advice. (Data file missing!)")
            return
        await ctx.send(f"\U0001f4a1 **Life Advice:** {random.choice(self.bad_advice)}")

    @app_commands.command(name="advice", description="Get some terrible life advice")
    async def advice_slash(self, interaction: discord.Interaction):
        if not self.bad_advice:
            await interaction.response.send_message("Fresh out of bad advice. (Data file missing!)")
            return
        await interaction.response.send_message(f"\U0001f4a1 **Life Advice:** {random.choice(self.bad_advice)}")


async def setup(bot):
    await bot.add_cog(BadAdvice(bot))
