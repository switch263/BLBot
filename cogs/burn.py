import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

import economy
from amount import parse_amount, amount_error

logger = logging.getLogger(__name__)


VANISH_FLAVOR = [
    "🔥 **Up in smoke.**",
    "🔥 **The coins glow red and crumble to ash.**",
    "🔥 **Inflation? Not on your watch.**",
    "🔥 **You feed the brazier. The brazier is pleased.**",
]

DONATE_FLAVOR = [
    "🏦 **The house tips its hat.**",
    "🏦 **Your coins clink into the house pot.**",
    "🏦 **The bot pockets the donation, no questions asked.**",
    "🏦 **The house thanks you for your contribution.**",
]


class Burn(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Burn module has been loaded")

    async def _do_burn(self, guild_id: int, user: discord.abc.User, amount: int, vanish: bool) -> discord.Embed:
        if amount <= 0:
            return discord.Embed(description="Burn at least **1** coin.", color=discord.Color.red())

        if vanish:
            if not economy.try_deduct(guild_id, user.id, amount):
                balance = economy.get_coins(guild_id, user.id)
                return discord.Embed(
                    description=f"You only have **{balance:,}** coins.",
                    color=discord.Color.red(),
                )
            flavor = random.choice(VANISH_FLAVOR)
            target = "the void"
            color = discord.Color.dark_red()
        else:
            result = economy.transfer_to_house(guild_id, user.id, amount, is_bet=False)
            if not result.get("ok"):
                if result.get("error") == "broke":
                    return discord.Embed(
                        description=f"You only have **{result.get('have', 0):,}** coins.",
                        color=discord.Color.red(),
                    )
                return discord.Embed(description="Donation failed. Try again.", color=discord.Color.red())
            flavor = random.choice(DONATE_FLAVOR)
            target = "the house"
            color = discord.Color.orange()

        new_bal = economy.get_coins(guild_id, user.id)
        embed = discord.Embed(
            title="Coins Burned",
            description=f"{flavor}\n{user.mention} burned **{amount:,}** coins to {target}.",
            color=color,
        )
        embed.add_field(name="New Balance", value=f"{new_bal:,} coins", inline=False)
        return embed

    @commands.command(name="burn")
    @commands.guild_only()
    async def burn_prefix(self, ctx, amount: str = None, mode: str = "house"):
        """Burn coins. Usage: !burn <amount> [house|vanish]"""
        if amount is None:
            await ctx.send("Usage: `!burn <amount> [house|vanish]` — defaults to **house**.")
            return
        amt = parse_amount(amount)
        if amt is None:
            await ctx.send(amount_error(amount))
            return
        amount = amt
        vanish = mode.lower() in ("vanish", "void", "destroy", "burn")
        embed = await self._do_burn(ctx.guild.id, ctx.author, amount, vanish)
        await ctx.send(embed=embed)

    @app_commands.command(name="burn", description="Burn coins. Defaults to the house pot; set vanish=True to destroy them.")
    @app_commands.describe(
        amount="Coins to burn",
        vanish="Destroy coins entirely instead of donating to the house (default False).",
    )
    async def burn_slash(self, interaction: discord.Interaction, amount: str, vanish: bool = False):
        if not interaction.guild_id:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        amt = parse_amount(amount)
        if amt is None:
            await interaction.response.send_message(amount_error(amount), ephemeral=True)
            return
        amount = amt
        embed = await self._do_burn(interaction.guild_id, interaction.user, amount, vanish)
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Burn(bot))
