import discord
from discord.ext import commands
from discord import app_commands
import logging
import economy

logger = logging.getLogger(__name__)


class Richest(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Richest module has been loaded")

    def _build_embed(self, guild: discord.Guild) -> discord.Embed:
        rows = economy.get_leaderboard(guild.id)
        stats = economy.get_server_stats(guild.id)

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
