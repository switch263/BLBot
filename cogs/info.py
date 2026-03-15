import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class Info(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Info module has been loaded")

    @app_commands.command(name="whoami", description="Show your user info (only you can see this)")
    async def whoami(self, interaction: discord.Interaction):
        user = interaction.user
        embed = discord.Embed(
            title="Your Info",
            color=user.accent_color or discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)

        embed.add_field(name="Display Name", value=user.display_name, inline=True)
        embed.add_field(name="Username", value=str(user), inline=True)
        embed.add_field(name="User ID", value=f"`{user.id}`", inline=True)

        if isinstance(user, discord.Member):
            joined = user.joined_at.strftime("%b %d, %Y %I:%M %p") if user.joined_at else "Unknown"
            embed.add_field(name="Joined Server", value=joined, inline=True)
            embed.add_field(name="Top Role", value=user.top_role.mention if user.top_role.name != "@everyone" else "None", inline=True)
            embed.add_field(name="Boosting", value="Yes" if user.premium_since else "No", inline=True)

        created = user.created_at.strftime("%b %d, %Y %I:%M %p")
        embed.add_field(name="Account Created", value=created, inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="channelinfo", description="Show current channel info (only you can see this)")
    async def channelinfo(self, interaction: discord.Interaction):
        channel = interaction.channel
        embed = discord.Embed(
            title="Channel Info",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(name="Name", value=f"#{channel.name}" if hasattr(channel, 'name') else "DM", inline=True)
        embed.add_field(name="Channel ID", value=f"`{channel.id}`", inline=True)

        if isinstance(channel, discord.TextChannel):
            embed.add_field(name="Type", value="Text", inline=True)
            embed.add_field(name="Category", value=channel.category.name if channel.category else "None", inline=True)
            embed.add_field(name="Topic", value=channel.topic or "No topic set", inline=False)
            embed.add_field(name="NSFW", value="Yes" if channel.is_nsfw() else "No", inline=True)
            embed.add_field(name="Slowmode", value=f"{channel.slowmode_delay}s" if channel.slowmode_delay else "Off", inline=True)
            created = channel.created_at.strftime("%b %d, %Y %I:%M %p")
            embed.add_field(name="Created", value=created, inline=True)
            embed.add_field(name="Position", value=str(channel.position), inline=True)
            embed.add_field(name="Members", value=str(len(channel.members)), inline=True)
        elif isinstance(channel, discord.VoiceChannel):
            embed.add_field(name="Type", value="Voice", inline=True)
            embed.add_field(name="Bitrate", value=f"{channel.bitrate // 1000}kbps", inline=True)
            embed.add_field(name="User Limit", value=str(channel.user_limit) if channel.user_limit else "Unlimited", inline=True)
            embed.add_field(name="Connected", value=str(len(channel.members)), inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Info(bot))
