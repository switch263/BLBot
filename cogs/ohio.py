import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger(__name__)


class Ohio(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Ohio module has been loaded")

    @commands.command(aliases=['Ohio'])
    async def ohio(self, ctx, member: discord.Member = None):
        if member:
            await ctx.send("1-800-FUCK-OHIO! " + member.mention)
        else:
            await ctx.send("1-800-FUCK-OHIO!")

    @app_commands.command(name="ohio", description="Express your feelings about Ohio")
    @app_commands.describe(member="Direct it at someone (optional)")
    async def ohio_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        if member:
            await interaction.response.send_message("1-800-FUCK-OHIO! " + member.mention)
        else:
            await interaction.response.send_message("1-800-FUCK-OHIO!")


async def setup(bot):
    await bot.add_cog(Ohio(bot))
