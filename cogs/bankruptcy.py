"""The house went bankrupt — how the debt gets settled.

There is no bet cap, so a big enough win can drain both house buckets and
still leave the winner short. When that happens economy.casino_payout logs a
bankruptcy event; this cog picks it up (30s poll), rolls the dice, and settles
the debt one of two ways:

  🖨️ Usually (1 - BANKRUPTCY_ROB_CHANCE): the money printer. BLBot mints the
     winner's shortfall out of thin air (economy.mint_house_bailout) and the
     casino reopens like nothing happened.
  💰 BANKRUPTCY_ROB_CHANCE (1%): everyone else pays. An equal percentage of
     EVERY player bank account is seized to cover the losses
     (economy.cover_house_shortfall — the winner's own and the memorial
     player's excepted): "<player> bankrupted the house, so we took X% of
     everyone's bank to cover losses." If the banks can't cover it all, the
     printer mints the remainder — the winner is made whole either way.

Both paths finish with replenish_house_if_low so the house reserve is
re-seeded and play continues. Announcements land in #game-spam (same channel
resolution as taxes). Knobs live in economy.py. State (cog_kv namespace
"bankruptcy", guild-scoped user_id=0): `pending` — JSON list of unhandled
bankruptcy events, written by economy.py.
"""
import discord
from discord.ext import commands, tasks
import logging
import random

import economy
from config import ADMIN_CHANNEL_ID

logger = logging.getLogger(__name__)


class Bankruptcy(commands.Cog):
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
        logger.info("Bankruptcy watch loaded.")

    def _find_channel(self, guild: discord.Guild):
        """Same resolution as taxes: #game-spam, then admin, then system."""
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
                for ev in economy.pop_bankruptcy_events(guild.id):
                    await self._handle_bankruptcy(guild, ev)
            except Exception:
                logger.exception(f"bankruptcy loop failed for guild {guild.id}")

    @_watch_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    async def _handle_bankruptcy(self, guild: discord.Guild, ev: dict):
        winner_id = int(ev.get("user_id", 0))
        owed = int(ev.get("owed", 0))
        paid = int(ev.get("paid", 0))
        shortfall = max(0, owed - paid)
        if shortfall <= 0:
            return
        if random.random() < economy.BANKRUPTCY_ROB_CHANCE:
            embed = self._rob(guild, winner_id, owed, shortfall)
        else:
            embed = self._mint(guild, winner_id, owed, shortfall)
        # Either way the house is empty — re-seed the reserve so play continues.
        economy.replenish_house_if_low(guild.id)
        ch = self._find_channel(guild)
        if ch is None:
            logger.warning(f"bankruptcy: no channel in guild {guild.id}; unannounced.")
            return
        try:
            await ch.send(content=f"💥 <@{winner_id}> broke the bank!", embed=embed)
        except discord.HTTPException as e:
            logger.error(f"bankruptcy: couldn't announce in guild {guild.id}: {e}")

    def _rob(self, guild: discord.Guild, winner_id: int, owed: int,
             shortfall: int) -> discord.Embed:
        """The 1% roll: everyone else's banks cover the loss; the printer only
        tops up whatever the banks couldn't."""
        cover = economy.cover_house_shortfall(guild.id, winner_id, shortfall)
        minted = 0
        if cover["still_short"] > 0:
            minted = economy.mint_house_bailout(guild.id, winner_id, cover["still_short"])
        pct = f"{cover['pct'] * 100:.1f}%"
        if cover["seized"] > 0:
            lines = [
                f"<@{winner_id}> bankrupted the house, so we took **{pct}** of "
                f"everyone's bank to cover losses.",
                "",
                f"House owed **{owed:,}** and couldn't pay. **{cover['seized']:,}** "
                f"seized from **{cover['accounts']}** account(s).",
            ]
            if minted > 0:
                lines.append(f"Even that wasn't enough — the printer minted the "
                             f"last **{minted:,}**.")
        else:
            lines = [
                f"<@{winner_id}> bankrupted the house and the safe-deposit boxes "
                f"were empty too, so the printer covered the whole "
                f"**{minted:,}**.",
            ]
        return discord.Embed(
            title="🏚️ THE HOUSE IS BANKRUPT — EVERYONE PAYS",
            description="\n".join(lines),
            color=discord.Color.dark_red(),
        )

    def _mint(self, guild: discord.Guild, winner_id: int, owed: int,
              shortfall: int) -> discord.Embed:
        minted = economy.mint_house_bailout(guild.id, winner_id, shortfall)
        return discord.Embed(
            title="🖨️ THE MONEY PRINTER GOES BRRR",
            description=(
                f"<@{winner_id}> bankrupted the house — it owed **{owed:,}** and "
                f"couldn't pay, so BLBot minted **{minted:,}** fresh coins to "
                f"settle the debt. Your banks are safe. The coin's purchasing "
                f"power? Don't ask."
            ),
            color=discord.Color.green(),
        )


async def setup(bot):
    await bot.add_cog(Bankruptcy(bot))
