import discord
from discord.ext import commands
from discord import app_commands
import logging

import economy

logger = logging.getLogger(__name__)

# The bank is the anti-heist play: deposited coins leave your wallet, so
# /heist can't touch them (heists only ever see wallet coins). The catch is
# twofold — you can't gamble banked coins (every game reads the wallet, so
# you have to /withdraw first), and the bank sits inside the casino: a
# rob-the-house attempt can land on the SAFE-DEPOSIT BOXES (odds in
# cogs/heist.py) and skim up to BANK_RAID_MAX_PCT of every account.
# All money movement lives in economy.py (bank_deposit / bank_withdraw /
# bank_raid); this cog is just the counter window.

BANK_NAME = "First Bank of the Casino"


def _parse_amount(raw: str, available: int) -> int | None:
    """Parse a deposit/withdraw amount: a plain integer, 'all', or 'half'.
    Returns None if unparseable. May return a non-positive number (e.g. 'all'
    on an empty balance) — callers surface that as their own error."""
    raw = raw.strip().lower().replace(",", "")
    if raw == "all":
        return available
    if raw == "half":
        return available // 2
    try:
        return int(raw)
    except ValueError:
        return None


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
        embed.add_field(
            name="The fine print",
            value=(
                "• Banked coins are **safe from `/heist`** — thieves can only see your wallet.\n"
                "• You **can't gamble** banked coins. `/withdraw` to get cash on hand.\n"
                f"• Rarely, a house robber cracks the **safe-deposit boxes** and skims up to "
                f"**{max_pct}%** of every account. FDIC does not operate here."
            ),
            inline=False,
        )
        return embed

    async def _do_deposit(self, guild_id: int, user: discord.Member, raw_amount: str) -> str:
        wallet = economy.get_coins(guild_id, user.id)
        amount = _parse_amount(raw_amount, wallet)
        if amount is None:
            return "Usage: `/deposit <amount|all|half>`"
        if amount <= 0:
            return "Deposit something. The teller is judging you."
        result = economy.bank_deposit(guild_id, user.id, amount)
        if not result.get("ok"):
            if result.get("error") == "broke":
                return (
                    f"💸 You only have **{result.get('have', 0):,}** coins on hand — "
                    f"can't deposit **{amount:,}**."
                )
            return "⚠️ The teller's drawer jammed (database error). Try again."
        return (
            f"🏦 Deposited **{amount:,}** coins into the {BANK_NAME}.\n"
            f"💵 On hand: **{result['wallet']:,}** • 🏦 Banked: **{result['bank']:,}**\n"
            f"Safe from thieves — unless someone robs the whole house."
        )

    async def _do_withdraw(self, guild_id: int, user: discord.Member, raw_amount: str) -> str:
        banked = economy.bank_balance(guild_id, user.id)
        amount = _parse_amount(raw_amount, banked)
        if amount is None:
            return "Usage: `/withdraw <amount|all|half>`"
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
            return "⚠️ The vault door stuck (database error). Try again."
        return (
            f"💵 Withdrew **{amount:,}** coins. Cash in hand — go lose it responsibly.\n"
            f"💵 On hand: **{result['wallet']:,}** • 🏦 Banked: **{result['bank']:,}**"
        )

    # ---- /bank -------------------------------------------------------------

    @commands.command(name="bank")
    @commands.guild_only()
    async def bank_prefix(self, ctx, member: discord.Member = None):
        """Check your (or someone else's) bank balance."""
        target = member or ctx.author
        await ctx.send(embed=self._balance_embed(ctx.guild.id, target))

    @app_commands.command(name="bank", description="Check a casino bank account — banked coins are safe from heists")
    @app_commands.describe(member="Account to check (defaults to you)")
    async def bank_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        if not interaction.guild:
            await interaction.response.send_message("Server only.")
            return
        target = member or interaction.user
        await interaction.response.send_message(embed=self._balance_embed(interaction.guild_id, target))

    # ---- /deposit ----------------------------------------------------------

    @commands.command(name="deposit")
    @commands.guild_only()
    async def deposit_prefix(self, ctx, amount: str = ""):
        """Deposit coins into the bank: !deposit <amount|all|half>"""
        await ctx.send(await self._do_deposit(ctx.guild.id, ctx.author, amount))

    @app_commands.command(name="deposit", description="Park coins in the bank, out of heist reach (you can't gamble them)")
    @app_commands.describe(amount="Coins to deposit — a number, 'all', or 'half'")
    async def deposit_slash(self, interaction: discord.Interaction, amount: str):
        if not interaction.guild:
            await interaction.response.send_message("Server only.")
            return
        await interaction.response.send_message(
            await self._do_deposit(interaction.guild_id, interaction.user, amount)
        )

    # ---- /withdraw ---------------------------------------------------------

    @commands.command(name="withdraw")
    @commands.guild_only()
    async def withdraw_prefix(self, ctx, amount: str = ""):
        """Withdraw coins from the bank: !withdraw <amount|all|half>"""
        await ctx.send(await self._do_withdraw(ctx.guild.id, ctx.author, amount))

    @app_commands.command(name="withdraw", description="Withdraw banked coins so you have cash on hand to gamble")
    @app_commands.describe(amount="Coins to withdraw — a number, 'all', or 'half'")
    async def withdraw_slash(self, interaction: discord.Interaction, amount: str):
        if not interaction.guild:
            await interaction.response.send_message("Server only.")
            return
        await interaction.response.send_message(
            await self._do_withdraw(interaction.guild_id, interaction.user, amount)
        )


async def setup(bot):
    await bot.add_cog(Bank(bot))
