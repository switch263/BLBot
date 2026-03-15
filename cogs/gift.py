import discord
from discord.ext import commands
from discord import app_commands
from config import DATA_DIR
import os
import sqlite3
import logging

logger = logging.getLogger(__name__)


class Gift(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_file = os.path.join(DATA_DIR, "slots.db")

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Gift module has been loaded")

    def _get_coins(self, guild_id: int, user_id: int) -> int:
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, 100)",
                    (guild_id, user_id)
                )
                conn.commit()
                cursor = conn.execute(
                    "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                    (guild_id, user_id)
                )
                return cursor.fetchone()[0]
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return 0

    def _transfer(self, guild_id: int, from_id: int, to_id: int, amount: int) -> tuple[int, int]:
        """Transfer coins. Returns (sender_balance, receiver_balance)."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, 100)",
                    (guild_id, to_id)
                )
                conn.execute(
                    "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
                    (amount, guild_id, from_id)
                )
                conn.execute(
                    "UPDATE wallets SET coins = coins + ? WHERE guild_id = ? AND user_id = ?",
                    (amount, guild_id, to_id)
                )
                conn.commit()
                c1 = conn.execute("SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?", (guild_id, from_id)).fetchone()[0]
                c2 = conn.execute("SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?", (guild_id, to_id)).fetchone()[0]
                return c1, c2
        except sqlite3.Error as e:
            logger.error(f"Database error transferring: {e}")
            return 0, 0

    async def _do_gift(self, guild_id: int, sender: discord.Member, recipient: discord.Member, amount: int) -> discord.Embed:
        if sender.id == recipient.id:
            return discord.Embed(description="You can't gift coins to yourself!", color=discord.Color.red())
        if recipient.bot:
            return discord.Embed(description="You can't gift coins to a bot!", color=discord.Color.red())
        if amount < 1:
            return discord.Embed(description="You must gift at least **1** coin!", color=discord.Color.red())
        if amount > 1000000:
            return discord.Embed(description="That's too generous! Max gift is **1,000,000** coins.", color=discord.Color.red())

        balance = self._get_coins(guild_id, sender.id)
        if balance < amount:
            return discord.Embed(description=f"You only have **{balance}** coins!", color=discord.Color.red())

        sender_bal, recv_bal = self._transfer(guild_id, sender.id, recipient.id, amount)

        embed = discord.Embed(
            title="Gift Sent!",
            description=f"{sender.mention} gifted **{amount}** coins to {recipient.mention}!",
            color=discord.Color.green()
        )
        embed.add_field(name=f"{sender.display_name}'s Balance", value=f"{sender_bal} coins", inline=True)
        embed.add_field(name=f"{recipient.display_name}'s Balance", value=f"{recv_bal} coins", inline=True)
        return embed

    @commands.command(aliases=['give', 'send'])
    async def gift(self, ctx, recipient: discord.Member = None, amount: int = None):
        """Gift coins to another user. Usage: !gift @user amount"""
        if recipient is None or amount is None:
            await ctx.send("Usage: `!gift @user amount`")
            return
        embed = await self._do_gift(ctx.guild.id, ctx.author, recipient, amount)
        await ctx.send(embed=embed)

    @app_commands.command(name="gift", description="Gift coins to another user")
    @app_commands.describe(recipient="Who to send coins to", amount="How many coins to give")
    async def gift_slash(self, interaction: discord.Interaction, recipient: discord.Member, amount: int):
        embed = await self._do_gift(interaction.guild_id, interaction.user, recipient, amount)
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Gift(bot))
