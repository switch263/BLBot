import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger(__name__)


class Clap(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Clap module has been loaded")

    def _clapify(self, text: str) -> str:
        words = text.split()
        return " 👏 ".join(words) + " 👏"

    @commands.command()
    async def clap(self, ctx, *, text: str):
        """Put 👏 between 👏 every 👏 word"""
        result = self._clapify(text)
        if len(result) > 2000:
            await ctx.send("Too 👏 many 👏 words 👏")
            return
        await ctx.send(result)

    @app_commands.command(name="clap", description="Put 👏 between 👏 every 👏 word")
    @app_commands.describe(text="The text to clapify")
    async def clap_slash(self, interaction: discord.Interaction, text: str):
        result = self._clapify(text)
        if len(result) > 2000:
            await interaction.response.send_message("Too 👏 many 👏 words 👏")
            return
        await interaction.response.send_message(result)


async def setup(bot):
    await bot.add_cog(Clap(bot))
