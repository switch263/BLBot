import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger(__name__)


class HF(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("HF module has been loaded")

    @commands.command(aliases=['hotfuckin','HotFuckin'])
    async def hf(self, ctx):
        """ A Special Response for a Special Group Member """
        await ctx.send("C:\\HOTFUCKIN\\")

    @app_commands.command(name="hf", description="A Special Response for a Special Group Member")
    async def hf_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message("C:\\HOTFUCKIN\\")


async def setup(bot):
    await bot.add_cog(HF(bot))
