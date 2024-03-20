import discord
from discord.ext import commands
import random
import os
import datetime
import logging

logger = logging.getLogger(__name__)

class CooldownHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Cooldown cog loaded --\n")

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            retry_after = datetime.timedelta(seconds=error.retry_after)
            hours, remainder = divmod(retry_after.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            retry_str = f"{hours} hours, {minutes} minutes, {seconds} seconds"
            await ctx.send(f"Sorry {ctx.author.mention}, this command is on cooldown. Please try again in {retry_str}.")

def setup(bot):
    bot.add_cog(CooldownHandler(bot))

