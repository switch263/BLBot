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


class ThoughtOfTheDay(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.thoughts = _load_lines(os.path.join(DATA_DIR, "thoughts.txt"))

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Thought of the Day module has been loaded")

    @commands.command(aliases=['showerthought', 'deepthought'])
    async def thought(self, ctx):
        """Get a deep(?) thought of the day."""
        if not self.thoughts:
            await ctx.send("My brain is empty right now. (Data file missing!)")
            return
        embed = discord.Embed(
            description=f"\U0001f9e0 *{random.choice(self.thoughts)}*",
            color=discord.Color.from_rgb(147, 112, 219)
        )
        await ctx.send(embed=embed)

    @app_commands.command(name="thought", description="Get a deep(?) thought of the day")
    async def thought_slash(self, interaction: discord.Interaction):
        if not self.thoughts:
            await interaction.response.send_message("My brain is empty right now. (Data file missing!)")
            return
        embed = discord.Embed(
            description=f"\U0001f9e0 *{random.choice(self.thoughts)}*",
            color=discord.Color.from_rgb(147, 112, 219)
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(ThoughtOfTheDay(bot))
