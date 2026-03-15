import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class ServerStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Server Stats module has been loaded")

    def _build_embed(self, guild: discord.Guild) -> discord.Embed:
        """Build a server stats embed."""
        # Member counts
        total = guild.member_count
        online = sum(1 for m in guild.members if m.status != discord.Status.offline)
        bots = sum(1 for m in guild.members if m.bot)
        humans = total - bots

        # Channel counts
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)

        # Server age
        created = guild.created_at
        age = datetime.now(timezone.utc) - created
        if age.days >= 365:
            age_str = f"{age.days // 365} years, {(age.days % 365) // 30} months"
        elif age.days >= 30:
            age_str = f"{age.days // 30} months, {age.days % 30} days"
        else:
            age_str = f"{age.days} days"

        # Boost info
        boost_level = guild.premium_tier
        boost_count = guild.premium_subscription_count or 0

        # Roles
        role_count = len(guild.roles) - 1  # exclude @everyone

        # Emoji
        emoji_count = len(guild.emojis)

        embed = discord.Embed(
            title=f"Server Stats: {guild.name}",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(
            name="Members",
            value=f"Total: **{total}**\nOnline: **{online}**\nHumans: **{humans}**\nBots: **{bots}**",
            inline=True
        )

        embed.add_field(
            name="Channels",
            value=f"Text: **{text_channels}**\nVoice: **{voice_channels}**\nCategories: **{categories}**",
            inline=True
        )

        embed.add_field(
            name="Boost Status",
            value=f"Level: **{boost_level}**\nBoosts: **{boost_count}**",
            inline=True
        )

        embed.add_field(
            name="Server Age",
            value=f"Created: {created.strftime('%b %d, %Y')}\nAge: **{age_str}**",
            inline=True
        )

        embed.add_field(
            name="Other",
            value=f"Roles: **{role_count}**\nEmojis: **{emoji_count}**\nOwner: {guild.owner.mention if guild.owner else 'Unknown'}",
            inline=True
        )

        # Top roles by member count (excluding @everyone)
        top_roles = sorted(
            [r for r in guild.roles if r.name != "@everyone" and len(r.members) > 0],
            key=lambda r: len(r.members),
            reverse=True
        )[:5]
        if top_roles:
            roles_text = "\n".join(f"{r.mention} - {len(r.members)} members" for r in top_roles)
            embed.add_field(name="Top Roles", value=roles_text, inline=False)

        embed.set_footer(text=f"Server ID: {guild.id}")

        return embed

    @commands.command(aliases=['serverstats', 'serverinfo', 'server_info'])
    async def server_stats(self, ctx):
        """Display server statistics."""
        await ctx.send(embed=self._build_embed(ctx.guild))

    @app_commands.command(name="serverstats", description="Display server statistics")
    async def serverstats_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self._build_embed(interaction.guild))


async def setup(bot):
    await bot.add_cog(ServerStats(bot))
