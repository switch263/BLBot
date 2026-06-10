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

    # Slash command removed to stay under Discord's 100-global-command cap.
    # Still available as the !ohio / !Ohio prefix command.


async def setup(bot):
    await bot.add_cog(Ohio(bot))
