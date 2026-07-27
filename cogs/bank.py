import discord
from discord.ext import commands
from discord import app_commands
import logging

import economy
from amount import parse_amount
from taunts import ceiling_taunt

logger = logging.getLogger(__name__)

# The bank is the anti-heist play: deposited coins leave your wallet, so
# /heist can't touch them (heists only ever see wallet coins). The catch is
# twofold — you can't gamble banked coins (every game reads the wallet, so
# you have to /withdraw first), and the bank sits inside the casino: a
# rob-the-house attempt can land on the SAFE-DEPOSIT BOXES (odds in
# cogs/heist.py) and skim up to BANK_RAID_MAX_PCT of every account.
# All money movement lives in economy.py (bank_deposit / bank_withdraw /
# bank_raid); this cog is just the counter window.
#
# Privacy: accounts are private. /bank balance only shows your own account and
# every slash response is ephemeral; !bank DMs the statement. Public
# confirmations (prefix deposit/withdraw) never print balances.

BANK_NAME = "First Bank of the Casino"

# Amount parsing lives in amount.py (parse_amount with available=) — the
# shared parser handles numbers, k/m/b suffixes, all/half/max, and percents.
AMOUNT_HELP = "a number (`2500`, `10k`, `1.5m`), a percent (`50%`), `all`, `half`, or `max`"


class Bank(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Bank module has been loaded")

    # ---- Shared logic ------------------------------------------------------

    def _balance_embed(self, guild_id: int, user: discord.Member) -> discord.Embed:
        wallet = economy.get_coins(guild_id, user.id)
        banked = economy.bank_balance(guild_id, user.id)
        max_pct = int(economy.BANK_RAID_MAX_PCT * 100)
        embed = discord.Embed(
            title=f"🏦 {BANK_NAME}",
            description=f"Account holder: **{user.display_name}**",
            color=discord.Color.blue(),
        )
        embed.add_field(name="💵 On hand", value=f"**{wallet:,}** coins", inline=True)
        embed.add_field(name="🏦 In the bank", value=f"**{banked:,}** coins", inline=True)
        apr_pct = economy.BANK_INTEREST_APR * 100
        embed.add_field(
            name="The fine print",
            value=(
                f"• Deposits earn **{apr_pct:.0f}% APR**, compounded continuously.\n"
                "• Banked coins are **safe from `/heist`** — thieves can only see your wallet.\n"
                "• You **can't gamble** banked coins. `/bank withdraw` to get cash on hand.\n"
                f"• Rarely, a house robber cracks the **safe-deposit boxes** and skims up to "
                f"**{max_pct}%** of every account. FDIC does not operate here."
            ),
            inline=False,
        )
        return embed

    async def _do_deposit(self, guild_id: int, user: discord.Member,
                          raw_amount: str, show_balances: bool = True) -> str:
        wallet = economy.get_coins(guild_id, user.id)
        amount = parse_amount(raw_amount, available=wallet)
        if amount is None:
            return f"Usage: `/bank deposit <amount>` — {AMOUNT_HELP}."
        if amount <= 0:
            return "Deposit something. The teller is judging you."
        result = economy.bank_deposit(guild_id, user.id, amount)
        if not result.get("ok"):
            if result.get("error") == "broke":
                return (
                    f"💸 You only have **{result.get('have', 0):,}** coins on hand — "
                    f"can't deposit **{amount:,}**."
                )
            if result.get("error") == "capped":
                return (
                    f"🧱 Your account is full — it already holds the maximum "
                    f"**{economy.MAX_COINS:,}** coins.\n{ceiling_taunt()}"
                )
            return "⚠️ The teller's drawer jammed (database error). Try again."
        # A deposit trims itself to the account's remaining room under the coin
        # ceiling, so report what actually moved.
        amount = result.get("amount", amount)
        msg = f"🏦 Deposited **{amount:,}** coins into the {BANK_NAME}."
        if show_balances:
            msg += f"\n💵 On hand: **{result['wallet']:,}** • 🏦 Banked: **{result['bank']:,}**"
        msg += "\nSafe from thieves — unless someone robs the whole house."
        return msg

    async def _do_withdraw(self, guild_id: int, user: discord.Member,
                           raw_amount: str, show_balances: bool = True) -> str:
        banked = economy.bank_balance(guild_id, user.id)
        amount = parse_amount(raw_amount, available=banked)
        if amount is None:
            return f"Usage: `/bank withdraw <amount>` — {AMOUNT_HELP}."
        if amount <= 0:
            return "Your account can't cover a withdrawal of nothing." if banked > 0 else \
                "🏦 Your bank account is empty. Nothing to withdraw."
        result = economy.bank_withdraw(guild_id, user.id, amount)
        if not result.get("ok"):
            if result.get("error") == "broke":
                return (
                    f"💸 Your account holds **{result.get('have', 0):,}** coins — "
                    f"can't withdraw **{amount:,}**."
                )
            if result.get("error") == "capped":
                return (
                    f"🧱 Your wallet is full — it already holds the maximum "
                    f"**{economy.MAX_COINS:,}** coins. Spend some first.\n"
                    f"{ceiling_taunt()}"
                )
            return "⚠️ The vault door stuck (database error). Try again."
        amount = result.get("amount", amount)
        msg = f"💵 Withdrew **{amount:,}** coins. Cash in hand — go lose it responsibly."
        if show_balances:
            msg += f"\n💵 On hand: **{result['wallet']:,}** • 🏦 Banked: **{result['bank']:,}**"
        return msg

    # ---- prefix commands ---------------------------------------------------

    @commands.command(name="bank")
    @commands.guild_only()
    async def bank_prefix(self, ctx):
        """Check your bank balance (sent by DM — accounts are private)."""
        embed = self._balance_embed(ctx.guild.id, ctx.author)
        try:
            await ctx.author.send(embed=embed)
            await ctx.send("🏦 Statement sent to your DMs. Accounts are private.")
        except discord.Forbidden:
            await ctx.send(
                "🏦 Your DMs are closed, and the bank doesn't discuss accounts "
                "in the lobby. Open your DMs or use `/bank balance` for a private view."
            )

    @commands.command(name="deposit")
    @commands.guild_only()
    async def deposit_prefix(self, ctx, amount: str = ""):
        """Deposit coins into the bank: !deposit <amount|all|half|50%|10k>"""
        await ctx.send(await self._do_deposit(ctx.guild.id, ctx.author, amount, show_balances=False))

    @commands.command(name="withdraw")
    @commands.guild_only()
    async def withdraw_prefix(self, ctx, amount: str = ""):
        """Withdraw coins from the bank: !withdraw <amount|all|half|50%|10k>"""
        await ctx.send(await self._do_withdraw(ctx.guild.id, ctx.author, amount, show_balances=False))

    # ---- slash commands ------------------------------------------------------
    # One /bank group instead of three top-level commands — each group costs a
    # single slot against Discord's 100-command cap; subcommands are free.
    bank_group = app_commands.Group(name="bank", description=f"The {BANK_NAME} — private, heist-proof, un-gamblable",
                                    guild_only=True)

    @bank_group.command(name="balance", description="Check your bank account privately — banked coins are safe from heists")
    async def balance_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=self._balance_embed(interaction.guild_id, interaction.user),
            ephemeral=True,
        )

    @bank_group.command(name="deposit", description="Park coins in the bank, out of heist reach (you can't gamble them)")
    @app_commands.describe(amount="Coins to deposit — a number (10k, 1.5m), a percent (50%), 'all', 'half', or 'max'")
    async def deposit_slash(self, interaction: discord.Interaction, amount: str):
        await interaction.response.send_message(
            await self._do_deposit(interaction.guild_id, interaction.user, amount),
            ephemeral=True,
        )

    @bank_group.command(name="withdraw", description="Withdraw banked coins so you have cash on hand to gamble")
    @app_commands.describe(amount="Coins to withdraw — a number (10k, 1.5m), a percent (50%), 'all', 'half', or 'max'")
    async def withdraw_slash(self, interaction: discord.Interaction, amount: str):
        await interaction.response.send_message(
            await self._do_withdraw(interaction.guild_id, interaction.user, amount),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Bank(bot))
