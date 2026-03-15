import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import logging

logger = logging.getLogger(__name__)


class TarkovTime(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.timeout = aiohttp.ClientTimeout(total=10)

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Tarkov time module has been loaded")

    async def _fetch_tarkov_time(self) -> str:
        """Fetch and format Tarkov time. Returns message string or raises."""
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.get("https://tarkov-time.adam.id.au/api") as response:
                response.raise_for_status()
                timejson = await response.json()
        message = ""
        for side in timejson:
            message = message + side + ": " + timejson[side] + "\n"
        return message

    @commands.command(aliases=['ttime', 'tarkovtime'])
    async def tarkov_time(self, ctx):
        """Fetches current in-game times for Escape from Tarkov"""
        try:
            message = await self._fetch_tarkov_time()
            await ctx.send(message)
        except aiohttp.ClientError:
            await ctx.send("Failed to fetch Tarkov time. Please try again.")
            logger.error("Network error fetching Tarkov time")
        except Exception as e:
            await ctx.send("An error occurred fetching Tarkov time.")
            logger.error(f"Unexpected error in tarkov_time: {e}")

    @app_commands.command(name="tarkov_time", description="Get current in-game times for Escape from Tarkov")
    async def tarkov_time_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            message = await self._fetch_tarkov_time()
            await interaction.followup.send(message)
        except aiohttp.ClientError:
            await interaction.followup.send("Failed to fetch Tarkov time. Please try again.")
            logger.error("Network error fetching Tarkov time")
        except Exception as e:
            await interaction.followup.send("An error occurred fetching Tarkov time.")
            logger.error(f"Unexpected error in tarkov_time: {e}")


async def setup(bot):
    await bot.add_cog(TarkovTime(bot))
