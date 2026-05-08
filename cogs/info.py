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

    @app_commands.command(name="guildinfo", description="Show server info + bot's overall reach (only you can see this)")
    async def guildinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Server Info — {guild.name}",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        humans = sum(1 for m in guild.members if not m.bot)
        bots = guild.member_count - humans if guild.member_count else sum(1 for m in guild.members if m.bot)
        online = sum(1 for m in guild.members if m.status != discord.Status.offline)

        text_count = len(guild.text_channels)
        voice_count = len(guild.voice_channels)
        category_count = len(guild.categories)
        in_voice = sum(len(vc.members) for vc in guild.voice_channels)

        embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(name="Server ID", value=f"`{guild.id}`", inline=True)
        embed.add_field(name="Created", value=guild.created_at.strftime("%b %d, %Y"), inline=True)

        embed.add_field(name="Members", value=f"{guild.member_count or len(guild.members):,}", inline=True)
        embed.add_field(name="Humans / Bots", value=f"{humans:,} / {bots:,}", inline=True)
        embed.add_field(name="Online", value=f"{online:,}", inline=True)

        embed.add_field(name="Text / Voice / Categories", value=f"{text_count} / {voice_count} / {category_count}", inline=True)
        embed.add_field(name="In Voice", value=f"{in_voice:,}", inline=True)
        embed.add_field(name="Roles", value=f"{len(guild.roles)}", inline=True)

        embed.add_field(name="Boost Tier", value=f"Level {guild.premium_tier}", inline=True)
        embed.add_field(name="Boosts", value=f"{guild.premium_subscription_count or 0}", inline=True)
        embed.add_field(name="Verification", value=str(guild.verification_level).replace("_", " ").title(), inline=True)

        # Bot reach across all guilds it's in.
        all_guilds = self.bot.guilds
        total_users = sum(g.member_count or 0 for g in all_guilds)
        top = sorted(all_guilds, key=lambda g: g.member_count or 0, reverse=True)[:5]
        top_lines = [f"• {g.name} — {(g.member_count or 0):,}" for g in top]
        embed.add_field(
            name=f"Bot reach — {len(all_guilds)} server(s), {total_users:,} users",
            value="\n".join(top_lines) if top_lines else "—",
            inline=False,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Info(bot))
