import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger(__name__)


class Lasaga(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lasaga_url = 'https://user-images.githubusercontent.com/1498712/101569286-32851600-39a2-11eb-9a0a-e2b1c7b69fc8.png'

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Lasaga module has been loaded")

    @commands.command(aliases=['Lasaga'])
    async def lasaga(self, ctx):
        await ctx.send(self.lasaga_url)

    @app_commands.command(name="lasaga", description="Bake some lasaga")
    async def lasaga_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(self.lasaga_url)


async def setup(bot):
    await bot.add_cog(Lasaga(bot))
