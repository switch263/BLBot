import logging

from discord.ext import commands, tasks

import economy
from economy import (
    replenish_house_if_low,
    HOUSE_STARTING_COINS,
    HOUSE_LOW_WATER_PCT,
)

logger = logging.getLogger(__name__)


class HouseUpkeep(commands.Cog):
    """Background maintenance for the house bank. Once a week it checks each
    guild's house and, if total funds (on-hand + reserve) have fallen below
    HOUSE_LOW_WATER_PCT of the seed, tops the reserve back up to the seed so a
    bad run of player luck can never permanently drain the casino. Replenishment
    targets the safe-harbor reserve, so the topped-up coins aren't immediately
    heistable."""

    def __init__(self, bot):
        self.bot = bot
        self.replenish_loop.start()

    def cog_unload(self):
        self.replenish_loop.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("House Upkeep loaded.")

    @tasks.loop(hours=24 * 7)
    async def replenish_loop(self):
        low_water = int(HOUSE_STARTING_COINS * HOUSE_LOW_WATER_PCT)
        for guild in self.bot.guilds:
            try:
                result = replenish_house_if_low(guild.id)
            except Exception as e:
                logger.error(f"House replenish failed for guild {guild.id}: {e}")
                continue
            if result.get("replenished"):
                logger.info(
                    f"House replenished in guild {guild.id}: added "
                    f"{result['added']:,} (total was below {low_water:,}); "
                    f"reserve now {result['reserve']:,}."
                )

    @replenish_loop.before_loop
    async def before_replenish_loop(self):
        # Wait until the bot is connected and the house id is registered before
        # the first run, so guild list and house wallet are available.
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(HouseUpkeep(bot))
