import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

import economy

logger = logging.getLogger(__name__)

MIN_RECIPIENTS = 3
MAX_RECIPIENTS = 7

# Once-per-week cooldown — can't have people being too generous.
CHARITY_COOLDOWN_SECONDS = 7 * 24 * 60 * 60

CHARITY_TITLES = [
    "🎁 Charity Drive",
    "💸 Random Acts of Wealth",
    "🕊️ The Foundation Disburses",
    "🪙 Coin Rain",
    "🤲 Philanthropy Hour",
]

CHARITY_FLAVOR = [
    "{giver} opens their wallet and the wind takes care of the rest.",
    "{giver} stages a public coin shower in the channel.",
    "{giver} feels generous. The recipients did nothing to earn this.",
    "{giver} establishes a one-time charitable trust. Trustees: chaos.",
    "{giver} dumps a sack of coins into the crowd.",
]


def _split_random(amount: int, n: int) -> list[int]:
    """Split `amount` into `n` positive integer shares with random sizes.

    Uses uniform cut points so shares follow a Dirichlet(1,...) distribution —
    naturally produces a windfall + scraps feel.
    """
    if n <= 1:
        return [amount]
    if amount <= n:
        shares = [1] * n
        for _ in range(amount - n):
            shares[random.randrange(n)] += 1
        random.shuffle(shares)
        return shares
    cuts = sorted(random.sample(range(1, amount), n - 1))
    shares = []
    prev = 0
    for c in cuts:
        shares.append(c - prev)
        prev = c
    shares.append(amount - prev)
    return shares


def _eligible_recipients(channel: discord.abc.GuildChannel, giver_id: int) -> list[discord.Member]:
    return [m for m in getattr(channel, "members", []) if not m.bot and m.id != giver_id]


class Charity(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Charity module has been loaded")

    async def _do_charity(
        self,
        guild_id: int,
        channel: discord.abc.GuildChannel,
        giver: discord.Member,
        amount: int,
    ) -> discord.Embed:
        if amount <= 0:
            return discord.Embed(description="Donate at least **1** coin.", color=discord.Color.red())

        # Once-per-week cooldown — can't have people being too generous. State
        # lives in the generic cog_kv store (namespace "charity").
        import time as _t
        now = _t.time()
        last_ts = economy.kv_get(guild_id, giver.id, "charity", "last_ts", 0) or 0
        elapsed = now - last_ts
        if elapsed < CHARITY_COOLDOWN_SECONDS:
            remaining = int(CHARITY_COOLDOWN_SECONDS - elapsed)
            days, rem = divmod(remaining, 86400)
            hours, _rem = divmod(rem, 3600)
            wait = f"{days}d {hours}h" if days else f"{hours}h"
            return discord.Embed(
                title="⏳ Charity Cooldown",
                description=(
                    f"You've already done your charitable deed this week. "
                    f"Open hand again in **{wait}**."
                ),
                color=discord.Color.red(),
            )

        pool = _eligible_recipients(channel, giver.id)
        if not pool:
            return discord.Embed(
                description="No eligible recipients in this channel (everyone's a bot or it's just you).",
                color=discord.Color.red(),
            )

        # Can't give more shares than coins available — every recipient must get >= 1.
        n = min(random.randint(MIN_RECIPIENTS, MAX_RECIPIENTS), len(pool), amount)
        recipients = random.sample(pool, n)
        shares = _split_random(amount, n)
        # Pair largest shares with random recipients (order is random because sample is random,
        # but sort shares descending so the embed reads cleanly biggest-first).
        shares.sort(reverse=True)
        pairings = list(zip(recipients, shares))

        result = economy.disburse(
            guild_id, giver.id,
            [(r.id, s) for r, s in pairings],
        )
        if not result.get("ok"):
            if result.get("error") == "broke":
                return discord.Embed(
                    description=f"You only have **{result.get('have', 0):,}** coins.",
                    color=discord.Color.red(),
                )
            return discord.Embed(description="Charity drive failed. Try again.", color=discord.Color.red())
        # Stamp the cooldown only after a successful disburse.
        economy.kv_set(guild_id, giver.id, "charity", "last_ts", now)
        new_bal = result["sender_balance"]
        title = random.choice(CHARITY_TITLES)
        flavor = random.choice(CHARITY_FLAVOR).format(giver=giver.display_name)

        lines = [flavor, ""]
        lines.append(f"**Total disbursed:** {amount:,} coins to **{n}** recipient(s).")
        lines.append("")
        for recipient, share in pairings:
            lines.append(f"• {recipient.mention} — **{share:,}** coins")
        lines.append("")
        lines.append(f"Donor balance: **{new_bal:,}**")

        return discord.Embed(
            title=title,
            description="\n".join(lines),
            color=discord.Color.green(),
        )

    @commands.command(name="charity", aliases=["donate", "alms"])
    @commands.guild_only()
    async def charity_prefix(self, ctx, amount: int = None):
        """Disperse coins to random non-bot members of this channel."""
        if amount is None:
            await ctx.send("Usage: `!charity <amount>`")
            return
        embed = await self._do_charity(ctx.guild.id, ctx.channel, ctx.author, amount)
        await ctx.send(embed=embed)

    @app_commands.command(name="charity", description="Disperse coins to random non-bot members of this channel.")
    @app_commands.describe(amount="Total coins to give away")
    async def charity_slash(self, interaction: discord.Interaction, amount: int):
        if not interaction.guild_id or not isinstance(interaction.channel, discord.abc.GuildChannel):
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        embed = await self._do_charity(
            interaction.guild_id, interaction.channel, interaction.user, amount
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Charity(bot))
