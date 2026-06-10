import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

logger = logging.getLogger(__name__)


class AlphabetSoup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_messages = {}  # channel_id -> message content

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Alphabet Soup module has been loaded")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if message.content and not message.content.startswith("!") and not message.content.startswith("/"):
            self.last_messages[message.channel.id] = message.content

    def _scramble(self, text: str) -> str:
        words = text.split()
        scrambled = []
        for word in words:
            chars = list(word)
            random.shuffle(chars)
            scrambled.append("".join(chars))
        random.shuffle(scrambled)
        return " ".join(scrambled)

    @commands.command()
    async def soup(self, ctx):
        """Scramble the last message into alphabet soup."""
        text = self.last_messages.get(ctx.channel.id)
        if not text:
            await ctx.send("No messages to make soup from! Say something first.")
            return
        await ctx.send(f"🍜 {self._scramble(text)}")

    @app_commands.command(name="soup", description="Scramble the last message into alphabet soup")
    async def soup_slash(self, interaction: discord.Interaction):
        text = self.last_messages.get(interaction.channel_id)
        if not text:
            await interaction.response.send_message("No messages to make soup from! Say something first.")
            return
        await interaction.response.send_message(f"🍜 {self._scramble(text)}")


async def setup(bot):
    await bot.add_cog(AlphabetSoup(bot))
