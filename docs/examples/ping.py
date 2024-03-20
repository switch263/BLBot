"""

This is very basic example cog, showing you how to enable stats and !ping <member>


"""


import discord
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)

class Ping(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.stats = bot.get_cog('Stats')

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Ping module has been loaded\n-----")
        try:
            if self.stats:
                self.stats.register_cog(self.stats.db_path, "ping", ["pinged"])
                logger.info("Registering ping with stats")
            else:
                logger.warning("Stats cog not found.")
        except Exception as e:
            logger.error(f"Error registering ping with stats: {e}")

    @commands.command()
    async def ping(self, ctx, member: discord.Member):
        """
        Pings a user !ping <username>
        """
        # Send a message mentioning the member
        await ctx.send(f"**PING*** {member.mention}!")

        # Get the instance of the Stats cog
        stats_cog = self.bot.get_cog("Stats")
        if stats_cog:
            # Update the stats for the member
            await stats_cog.update_stats("ping", userid=str(member.id), pinged=1)

def setup(bot):
    bot.add_cog(Ping(bot))

