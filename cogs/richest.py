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
        # Ranked by total wealth (wallet + bank) so parking coins in the bank
        # doesn't hide you from the leaderboard. Each entry shows one combined
        # number — bank accounts are private, so no per-player split.
        rows = economy.get_wealth_leaderboard(guild.id)
        stats = economy.get_server_stats(guild.id)

        if not rows:
            return discord.Embed(title="Leaderboard", description="No one has any coins yet!", color=discord.Color.gold())

        medals = ["🥇", "🥈", "🥉"] + [f"**{i}.**" for i in range(4, 11)]
        desc = ""
        for i, (uid, wealth, coins, banked, won, lost) in enumerate(rows):
            member = guild.get_member(uid)
            name = member.display_name if member else f"User {uid}"
            net = won - lost
            net_str = f"+{net}" if net >= 0 else str(net)
            desc += f"{medals[i]} **{name}** — {wealth:,} coins (net: {net_str})\n"

        embed = discord.Embed(
            title="Richest Players",
            description=desc,
            color=discord.Color.gold()
        )

        total_wealth = stats['total_coins'] + stats['total_banked']
        embed.add_field(name="Server Economy", value=(
            f"Players: **{stats['players']}**\n"
            f"Total Coins: **{total_wealth:,}** "
            f"(💵 **{stats['total_coins']:,}** on hand, 🏦 **{stats['total_banked']:,}** banked)\n"
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
