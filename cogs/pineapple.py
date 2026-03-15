import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger(__name__)


class Pineapple(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pineapple_url = 'https://user-images.githubusercontent.com/16721240/131228780-d95f9e41-2de1-41af-a791-e4643e5bd936.png'

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Pineapple module has been loaded")

    @commands.command(aliases=['Pineapple'])
    async def pineapple(self, ctx):
        await ctx.send(self.pineapple_url)

    @app_commands.command(name="pineapple", description="Pineapple time")
    async def pineapple_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(self.pineapple_url)


async def setup(bot):
    await bot.add_cog(Pineapple(bot))
