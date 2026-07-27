"""House profit sharing — paying the shareholders.

The Tier 7 splurge "Buy Into the House" (splurges.py) sells shares of the
casino. Shareholders split economy.HOUSE_PROFIT_SHARE_PCT of house PROFIT
pro-rata, and are barred from gambling in exchange.

Nothing is skimmed on the bet path. Instead this cog polls and calls
economy.settle_house_dividends, which measures house funds against a
high-water mark and pays a cut of any NEW profit. A house below its mark pays
nothing until it earns back — so dividends can only ever come out of money the
casino actually made, and shareholders can't drive it into a loss.

Payouts are announced in #game-spam (same channel resolution as taxes) only
when they're worth mentioning, so a quiet casino doesn't spam the channel.

Commands: /dividends (or !dividends) — who owns what, and what the house owes.
State: cog_kv namespace "splurge" — `owned:house_share` per holder and the
guild-scoped `profit_highwater`, both written by economy.py.
"""
import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging

import economy
from config import ADMIN_CHANNEL_ID

logger = logging.getLogger(__name__)

# How often profit is swept and paid out. Frequent enough to feel like income,
# rare enough that the announcement stays an event.
SETTLE_MINUTES = 15

# Don't announce dividends smaller than this — a trickle isn't news. The coins
# are still paid; only the message is suppressed.
ANNOUNCE_FLOOR = 1_000_000


class Dividends(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        if not self._settle_loop.is_running():
            self._settle_loop.start()

    async def cog_unload(self):
        if self._settle_loop.is_running():
            self._settle_loop.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("House dividends loaded.")

    def _find_channel(self, guild: discord.Guild):
        """Same resolution as taxes/bankruptcy: #game-spam, admin, then system."""
        ch = discord.utils.get(guild.text_channels, name=economy.TAX_CHANNEL_NAME)
        if ch:
            return ch
        ch = guild.get_channel(ADMIN_CHANNEL_ID)
        if isinstance(ch, discord.TextChannel):
            return ch
        return guild.system_channel

    @tasks.loop(minutes=SETTLE_MINUTES)
    async def _settle_loop(self):
        for guild in list(self.bot.guilds):
            try:
                result = economy.settle_house_dividends(guild.id)
                if result["paid"] >= ANNOUNCE_FLOOR:
                    await self._announce(guild, result)
            except Exception:
                logger.exception(f"dividend loop failed for guild {guild.id}")

    @_settle_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    async def _announce(self, guild: discord.Guild, result: dict):
        lines = [
            f"The house cleared **{result['profit']:,}** in profit. "
            f"**{int(economy.HOUSE_PROFIT_SHARE_PCT * 100)}%** goes to the "
            f"shareholders.",
            "",
        ]
        for uid, cut in result["payouts"]:
            member = guild.get_member(uid)
            name = member.display_name if member else f"<@{uid}>"
            lines.append(f"💰 {name} — **{cut:,}**")
        embed = discord.Embed(
            title="🏛️ Dividend Day",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        embed.set_footer(
            text=f"{result['shares']} share(s) outstanding. "
                 f"Paid out of profit — the house is still up.")
        ch = self._find_channel(guild)
        if ch is None:
            return
        try:
            await ch.send(embed=embed)
        except discord.HTTPException as e:
            logger.error(f"dividends: couldn't announce in guild {guild.id}: {e}")

    # --- the report ---------------------------------------------------------

    async def _report(self, ctx_or_interaction):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild

        async def reply(**kwargs):
            if not is_slash:
                return await ctx_or_interaction.send(**kwargs)
            return await ctx_or_interaction.response.send_message(**kwargs)

        if guild is None:
            return
        holders = economy.get_shareholders(guild.id)
        if not holders:
            embed = discord.Embed(
                title="🏛️ The House Has No Shareholders",
                description=(
                    "Nobody has bought in. Every coin of profit stays with the "
                    "house.\n\nShares are Tier 7 in `/splurge catalog` — they pay "
                    f"**{int(economy.HOUSE_PROFIT_SHARE_PCT * 100)}%** of profit "
                    "and cost you the right to gamble."),
                color=discord.Color.dark_gold(),
            )
            await reply(embed=embed)
            return

        outstanding = sum(n for _, n in holders)
        state = economy.get_house_state(guild.id)
        lines = []
        for uid, shares in holders:
            member = guild.get_member(uid)
            name = member.display_name if member else f"<@{uid}>"
            stake = shares / outstanding * economy.HOUSE_PROFIT_SHARE_PCT * 100
            lines.append(f"**{shares}** share(s) — {name} • **{stake:.1f}%** of profit")
        embed = discord.Embed(
            title="🏛️ House Shareholders",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        embed.add_field(name="Shares outstanding", value=f"**{outstanding}**", inline=True)
        embed.add_field(name="House funds",
                        value=f"**{state['on_hand'] + state['reserve']:,}**", inline=True)
        embed.set_footer(
            text=f"Dividends settle every {SETTLE_MINUTES} minutes on new profit "
                 f"above the house's high-water mark. Shareholders cannot gamble.")
        await reply(embed=embed)

    @commands.command(name="dividends", aliases=["shareholders"])
    @commands.guild_only()
    async def dividends_prefix(self, ctx):
        await self._report(ctx)

    @app_commands.command(name="dividends",
                          description="Who owns a piece of the house")
    @app_commands.guild_only()
    async def dividends_slash(self, interaction: discord.Interaction):
        await self._report(interaction)


async def setup(bot):
    await bot.add_cog(Dividends(bot))
