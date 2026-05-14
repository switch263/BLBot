import discord
from discord.ext import commands
from discord import app_commands
import logging
import economy
import re

logger = logging.getLogger(__name__)

ADMIN_CHANNEL_ID = 401391297211924480


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Admin module has been loaded")

    @commands.command(name="coins", aliases=["grantcoins", "addcoins", "cheatchk"])
    async def grant_coins(self, ctx, user: discord.Member, amount: int):
        """Admin command to grant coins to a user. Only works in the admin channel."""
        # Check if command is in the admin channel
        if ctx.channel.id != ADMIN_CHANNEL_ID:
            return  # Silently ignore if not in admin channel

        # Validate amount
        if amount <= 0:
            await ctx.send("Amount must be positive!")
            return

        if amount > 1000000:
            await ctx.send("That's too many coins! Maximum is 1,000,000 per grant.")
            return

        # Grant the coins
        guild_id = ctx.guild.id
        economy.award_coins(guild_id, user.id, amount)

        # Confirm
        embed = discord.Embed(
            title="💰 Coins Granted",
            description=f"{ctx.author.mention} granted **{amount:,}** coins to {user.mention}",
            color=discord.Color.gold()
        )
        embed.add_field(name="New Balance", value=f"{economy.get_coins(guild_id, user.id):,} coins")
        embed.set_footer(text=f"Admin: {ctx.author.display_name}")
        await ctx.send(embed=embed)

        logger.info(f"Admin {ctx.author} granted {amount} coins to {user} in guild {guild_id}")

    @commands.command(name="unjail", aliases=["pardon"])
    async def unjail(self, ctx, user: discord.Member):
        """Release a user from casino jail. Allowed in the admin channel, OR anywhere
        for a member with the `Admin` role."""
        in_admin_channel = ctx.channel.id == ADMIN_CHANNEL_ID
        has_admin_role = isinstance(ctx.author, discord.Member) and any(
            r.name == "Admin" for r in ctx.author.roles
        )
        if not (in_admin_channel or has_admin_role):
            return  # Silently ignore — same gate behavior as the other admin commands.

        guild_id = ctx.guild.id
        was_jailed = economy.unjail_user(guild_id, user.id)

        if was_jailed:
            embed = discord.Embed(
                title="🔓 Released from Jail",
                description=f"{ctx.author.mention} pardoned {user.mention}. Back in the casino.",
                color=discord.Color.green(),
            )
            embed.set_footer(text=f"Admin: {ctx.author.display_name}")
            await ctx.send(embed=embed)
            logger.info(f"Admin {ctx.author} unjailed {user} in guild {guild_id}")
        else:
            await ctx.send(f"{user.display_name} wasn't in jail.")

    @commands.command(name="removecoins", aliases=["takecoins", "deductcoins", "subcoins"])
    async def remove_coins(self, ctx, user: discord.Member, amount: int):
        """Deduct coins from a user. Allowed in the admin channel, OR anywhere for
        a member with the `Admin` role. Clamps at 0 — never produces a negative balance."""
        in_admin_channel = ctx.channel.id == ADMIN_CHANNEL_ID
        has_admin_role = isinstance(ctx.author, discord.Member) and any(
            r.name == "Admin" for r in ctx.author.roles
        )
        if not (in_admin_channel or has_admin_role):
            return  # Silently ignore — same gate behavior as unjail.

        if amount <= 0:
            await ctx.send("Amount must be positive!")
            return

        guild_id = ctx.guild.id
        before = economy.get_coins(guild_id, user.id)
        economy.fine_user(guild_id, user.id, amount)
        after = economy.get_coins(guild_id, user.id)
        actually_removed = before - after

        embed = discord.Embed(
            title="💸 Coins Removed",
            description=f"{ctx.author.mention} removed **{actually_removed:,}** coins from {user.mention}.",
            color=discord.Color.dark_red(),
        )
        if actually_removed < amount:
            embed.add_field(
                name="Note",
                value=f"Requested {amount:,}, but balance was only {before:,} — clamped at 0.",
                inline=False,
            )
        embed.add_field(name="New Balance", value=f"{after:,} coins")
        embed.set_footer(text=f"Admin: {ctx.author.display_name}")
        await ctx.send(embed=embed)

        logger.info(f"Admin {ctx.author} removed {actually_removed} coins from {user} in guild {guild_id}")


async def setup(bot):
    await bot.add_cog(Admin(bot))
