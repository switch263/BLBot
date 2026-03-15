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


class Therapy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.responses = _load_lines(os.path.join(DATA_DIR, "therapy_responses.txt"))

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Therapy module has been loaded")

    @commands.command(aliases=['therapist', 'shrink'])
    async def therapy(self, ctx):
        """Get some professional(?) advice."""
        if not self.responses:
            await ctx.send("The therapist is out. (Data file missing!)")
            return
        await ctx.send(f"\U0001f6cb\ufe0f {random.choice(self.responses)}")

    @app_commands.command(name="therapy", description="Get some professional(?) advice from the bot therapist")
    async def therapy_slash(self, interaction: discord.Interaction):
        if not self.responses:
            await interaction.response.send_message("The therapist is out. (Data file missing!)")
            return
        await interaction.response.send_message(f"\U0001f6cb\ufe0f {random.choice(self.responses)}")


async def setup(bot):
    await bot.add_cog(Therapy(bot))
