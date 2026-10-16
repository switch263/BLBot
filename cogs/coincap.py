"""Someone got too rich for the engine — and gets told about it.

economy.MAX_COINS is the hard ceiling on any stored balance (SQLite silently
turns an overflowed INTEGER into a float, which is what used to corrupt
wallets). When a payout is bigger than the room left in a winner's wallet, the
overflow goes to the house pot — or, economy.CEILING_DISPERSE_CHANCE of the
time, is split among the other active players — and economy.py logs a
"ceiling strike". No game cog knows or cares: every path through
casino_payout / refund_from_house / mint_house_bailout participates for free.

This cog drains that queue on a 30s poll and announces the loss in #game-spam,
blaming the player entirely — because it IS their fault. They chose to sit on
1e300 coins. Taunt lines are hand-written in
data_files/coincap_taunts.txt (see taunts.py).

State: cog_kv namespace "coincap", guild key `pending` — written by economy.py,
drained here.
"""
import discord
from discord.ext import commands, tasks
import logging

import economy
from taunts import ceiling_taunt
from config import ADMIN_CHANNEL_ID
from game_common import format_coins

logger = logging.getLogger(__name__)

# What the player was doing when the ceiling ate their money.
_SOURCE_TEXT = {
    "payout": "a win",
    "refund": "a refund",
    "bailout": "a bankruptcy bailout",
}

# Recipients named individually before the list collapses (embed size limit).
_MAX_LISTED = 15


class CoinCap(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        if not self._watch_loop.is_running():
            self._watch_loop.start()

    async def cog_unload(self):
        if self._watch_loop.is_running():
            self._watch_loop.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Coin ceiling watch loaded.")

    def _find_channel(self, guild: discord.Guild):
        """Same resolution as taxes/bankruptcy: #game-spam, admin, then system."""
        ch = discord.utils.get(guild.text_channels, name=economy.TAX_CHANNEL_NAME)
        if ch:
            return ch
        ch = guild.get_channel(ADMIN_CHANNEL_ID)
        if isinstance(ch, discord.TextChannel):
            return ch
        return guild.system_channel

    @tasks.loop(seconds=30)
    async def _watch_loop(self):
        for guild in list(self.bot.guilds):
            try:
                for ev in economy.pop_ceiling_events(guild.id):
                    await self._announce(guild, ev)
            except Exception:
                logger.exception(f"coincap loop failed for guild {guild.id}")

    @_watch_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    async def _announce(self, guild: discord.Guild, ev: dict):
        user_id = int(ev.get("user_id", 0))
        lost = int(ev.get("lost", 0))
        paid = int(ev.get("paid", 0))
        owed = int(ev.get("owed", 0))
        if lost <= 0:
            return
        what = _SOURCE_TEXT.get(ev.get("source"), "a payout")
        dispersed = [(int(uid), int(amt)) for uid, amt in ev.get("dispersed") or []]
        lines = [
            ceiling_taunt(),
            "",
            f"The house owed **{format_coins(owed)}** on {what}. Their wallet had room for "
            f"**{format_coins(paid)}**.",
        ]
        if dispersed:
            given = sum(amt for _, amt in dispersed)
            lines.append(
                f"**{format_coins(lost)}** coins bounced off the ceiling — and "
                f"**{format_coins(given)}** of it rained down on everyone else at the tables:"
            )
            lines += [f"• <@{uid}> +**{format_coins(amt)}**" for uid, amt in dispersed[:_MAX_LISTED]]
            if len(dispersed) > _MAX_LISTED:
                lines.append(f"• …and {len(dispersed) - _MAX_LISTED} more")
            if given < lost:
                lines.append(f"The other **{format_coins(lost - given)}** went to the pot.")
        else:
            lines.append(
                f"**{format_coins(lost)}** coins bounced off the ceiling and landed in the pot."
            )
        lines += ["", f"Wallets cap at **{economy.MAX_COINS_LABEL}** coins. Spend something."]
        embed = discord.Embed(
            title="🧱 TOO RICH FOR THE ENGINE",
            description="\n".join(lines),
            color=discord.Color.dark_gold(),
        )
        ch = self._find_channel(guild)
        if ch is None:
            logger.warning(f"coincap: no channel in guild {guild.id}; unannounced.")
            return
        try:
            await ch.send(content=f"🧱 <@{user_id}> hit the coin ceiling.", embed=embed)
        except discord.HTTPException as e:
            logger.error(f"coincap: couldn't announce in guild {guild.id}: {e}")


async def setup(bot):
    await bot.add_cog(CoinCap(bot))
