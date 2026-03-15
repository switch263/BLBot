import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger(__name__)


class Mock(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Mock module has been loaded")

    def _mockify(self, text: str) -> str:
        """Convert text to spongebob mocking case."""
        lower = text.lower()
        output = ""
        counter = 0
        for char in lower:
            if char != ' ':
                counter += 1
            if counter % 2 == 0:
                output += char.lower()
            else:
                output += char.upper()
        return output

    @commands.command(aliases=['Mock'])
    async def mock(self, ctx, *, mockstring: str):
        """ Automatic spongebob-mocking-text """
        if len(mockstring) > 2000:
            await ctx.send("Message too long! Maximum 2000 characters.")
            return
        await ctx.send(self._mockify(mockstring))

    @app_commands.command(name="mock", description="Convert text to SpongeBob mocking case")
    @app_commands.describe(text="The text to mock")
    async def mock_slash(self, interaction: discord.Interaction, text: str):
        if len(text) > 2000:
            await interaction.response.send_message("Message too long! Maximum 2000 characters.")
            return
        await interaction.response.send_message(self._mockify(text))


async def setup(bot):
    await bot.add_cog(Mock(bot))
