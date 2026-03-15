import discord
from discord.ext import commands
from discord import app_commands
import os
import random
from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data_files")


def _load_lines(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.error(f"Data file not found: {filepath}")
        return []


class RandomQuote(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.fake_quotes = _load_lines(os.path.join(DATA_DIR, "fake_quotes.txt"))
        self.starters = _load_lines(os.path.join(DATA_DIR, "fakequote_starters.txt"))
        self.actions = _load_lines(os.path.join(DATA_DIR, "fakequote_actions.txt"))
        self.endings = _load_lines(os.path.join(DATA_DIR, "fakequote_endings.txt"))

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Random Quote module has been loaded")

    def _generate_fake_quote(self) -> str:
        """Generate a fake quote. Uses templates if available, falls back to static list."""
        # 70% templated, 30% static (if both available)
        use_template = self.starters and self.actions and self.endings
        use_static = bool(self.fake_quotes)

        if use_template and use_static:
            if random.random() < 0.7:
                return f"{random.choice(self.starters)} {random.choice(self.actions)} {random.choice(self.endings)}"
            else:
                return random.choice(self.fake_quotes)
        elif use_template:
            return f"{random.choice(self.starters)} {random.choice(self.actions)} {random.choice(self.endings)}"
        elif use_static:
            return random.choice(self.fake_quotes)
        else:
            return "I forgot what I was going to say."

    async def _find_random_message(self, channel: discord.TextChannel, member: discord.Member) -> discord.Message | None:
        """Search for a random message from a member. 5 attempts at random dates."""
        joined = member.joined_at
        if not joined:
            return None

        now = datetime.now(timezone.utc)
        total_days = (now - joined).days
        if total_days < 1:
            total_days = 1

        for _ in range(5):
            random_offset = random.randint(0, total_days)
            random_date = joined + timedelta(days=random_offset)

            try:
                messages = []
                async for msg in channel.history(limit=200, after=random_date, oldest_first=True):
                    if msg.author.id == member.id and msg.content and not msg.content.startswith(("!", "/")):
                        messages.append(msg)
                    if len(messages) >= 10:
                        break

                if messages:
                    return random.choice(messages)
            except (discord.Forbidden, discord.HTTPException) as e:
                logger.error(f"Error searching message history: {e}")
                continue

        return None

    def _build_real_embed(self, member: discord.Member, message: discord.Message) -> discord.Embed:
        """Build an embed for a real found message."""
        embed = discord.Embed(
            description=f'"{message.content}"',
            color=discord.Color.blurple(),
            timestamp=message.created_at
        )
        embed.set_author(name=f"{member.display_name} said:", icon_url=member.display_avatar.url)
        embed.set_footer(text=f"#{message.channel.name} • Sent")
        return embed

    def _build_fake_embed(self, member: discord.Member) -> discord.Embed:
        """Build an embed with a fabricated quote."""
        fake = self._generate_fake_quote()

        joined = member.joined_at or datetime.now(timezone.utc) - timedelta(days=365)
        days_since = max(1, (datetime.now(timezone.utc) - joined).days)
        fake_date = joined + timedelta(days=random.randint(0, days_since))

        embed = discord.Embed(
            description=f'"{fake}"',
            color=discord.Color.blurple(),
            timestamp=fake_date
        )
        embed.set_author(name=f"{member.display_name} said:", icon_url=member.display_avatar.url)
        embed.set_footer(text="Definitely real quote • Sent")
        return embed

    @commands.command(name="random", aliases=['randomquote', 'rq'])
    async def random_quote(self, ctx, member: discord.Member = None):
        """Pull a random out-of-context message from someone's history."""
        if member is None:
            member = ctx.author

        async with ctx.typing():
            message = await self._find_random_message(ctx.channel, member)

        if message:
            await ctx.send(embed=self._build_real_embed(member, message))
        else:
            await ctx.send(embed=self._build_fake_embed(member))

    @app_commands.command(name="random", description="Pull a random out-of-context message from someone")
    @app_commands.describe(member="Whose message history to search (defaults to you)")
    async def random_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        if member is None:
            member = interaction.user

        await interaction.response.defer(thinking=True)
        message = await self._find_random_message(interaction.channel, member)

        if message:
            await interaction.followup.send(embed=self._build_real_embed(member, message))
        else:
            await interaction.followup.send(embed=self._build_fake_embed(member))


async def setup(bot):
    await bot.add_cog(RandomQuote(bot))
