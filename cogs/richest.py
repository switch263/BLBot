import discord
from discord.ext import commands
from discord import app_commands
from config import DATA_DIR
import os
import sqlite3
import logging

logger = logging.getLogger(__name__)


class Richest(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_file = os.path.join(DATA_DIR, "slots.db")

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Richest module has been loaded")

    def _get_leaderboard(self, guild_id: int) -> list:
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.execute(
                    "SELECT user_id, coins, total_won, total_lost, spins, jackpots FROM wallets WHERE guild_id = ? ORDER BY coins DESC LIMIT 10",
                    (guild_id,)
                )
                return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return []

    def _get_server_stats(self, guild_id: int) -> dict:
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.execute(
                    "SELECT COUNT(*), SUM(coins), SUM(total_won), SUM(total_lost), SUM(spins), SUM(jackpots) FROM wallets WHERE guild_id = ?",
                    (guild_id,)
                )
                row = cursor.fetchone()
                return {
                    "players": row[0] or 0,
                    "total_coins": row[1] or 0,
                    "total_won": row[2] or 0,
                    "total_lost": row[3] or 0,
                    "total_spins": row[4] or 0,
                    "total_jackpots": row[5] or 0,
                }
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return {"players": 0, "total_coins": 0, "total_won": 0, "total_lost": 0, "total_spins": 0, "total_jackpots": 0}

    def _build_embed(self, guild: discord.Guild) -> discord.Embed:
        rows = self._get_leaderboard(guild.id)
        stats = self._get_server_stats(guild.id)

        if not rows:
            return discord.Embed(title="Leaderboard", description="No one has any coins yet!", color=discord.Color.gold())

        medals = ["🥇", "🥈", "🥉"] + [f"**{i}.**" for i in range(4, 11)]
        desc = ""
        for i, (uid, coins, won, lost, spins, jackpots) in enumerate(rows):
            member = guild.get_member(uid)
            name = member.display_name if member else f"User {uid}"
            net = won - lost
            net_str = f"+{net}" if net >= 0 else str(net)
            desc += f"{medals[i]} **{name}** — {coins:,} coins (net: {net_str})\n"

        embed = discord.Embed(
            title="Richest Players",
            description=desc,
            color=discord.Color.gold()
        )

        embed.add_field(name="Server Economy", value=(
            f"Players: **{stats['players']}**\n"
            f"Total Coins: **{stats['total_coins']:,}**\n"
            f"Total Spins: **{stats['total_spins']:,}**\n"
            f"Total Jackpots: **{stats['total_jackpots']:,}**"
        ), inline=False)

        return embed

    @commands.command(aliases=['rich', 'leaderboard', 'lb', 'economy'])
    async def richest(self, ctx):
        """Show the richest players and server economy stats."""
        await ctx.send(embed=self._build_embed(ctx.guild))

    @app_commands.command(name="richest", description="See the richest players and server economy stats")
    async def richest_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self._build_embed(interaction.guild))


async def setup(bot):
    await bot.add_cog(Richest(bot))
