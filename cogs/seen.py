import discord
from discord.ext import commands
import logging

class Seen(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.stats = bot.get_cog('Stats')
        self.logger = logging.getLogger(__name__)

    @commands.Cog.listener()
    async def on_ready(self):
        self.logger.info("Seen cog is ready.")

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        try:
            if before.nick != after.nick:
                summary = f"Nick changed for user {before.id}: {before.nick} -> {after.nick}"
                self.logger.info(summary)
            if self.stats:
                await self.stats.update_display_name(userid=str(before.id), new_name=str(after.nick))
    
        except Exception as e:
            self.logger.error(f"An error occurred while processing member update event: {e}")

def setup(bot):
    bot.add_cog(Seen(bot))

