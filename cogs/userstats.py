# userstats
import logging
from discord.ext import commands

class UserStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.stats = bot.get_cog('Stats')
        self.logger = logging.getLogger(__name__)
        self.logger.debug("UserStats cog initialized.")

    @commands.Cog.listener()
    async def on_ready(self):
        self.logger.info("UserStats module has been loaded")
        try:
            if self.stats:
                self.stats.register_cog("user", ["messages", "characters"])
                self.logger.debug("UserStats: Successfully registered with Stats cog.")
            else:
                self.logger.warning("Stats cog not found.")
        except Exception as e:
            self.logger.error(f"Error registering submodule with stats: {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        try:
            if self.stats:
                self.logger.debug("UserStats: Stats cog found. Updating user stats.")
                await self.stats.update_stats("user", userid=str(message.author.id), messages=1, characters=len(message.content))
                await self.stats.update_member_seen(userid=str(message.author.id))
            else:
                self.logger.warning("UserStats: Stats cog not found.")
        except Exception as ex:
            self.logger.info(f"TODO: Fix This is a known issue.") 
            #self.logger.error(f"An unexpected error occurred while updating user stats: {ex}")

def setup(bot):
    bot.add_cog(UserStats(bot))

