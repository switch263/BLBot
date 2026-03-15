import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger(__name__)


class Vaporwave(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Vaporwave module has been loaded")

    def _vaporize(self, text: str) -> str:
        result = ""
        for char in text:
            code = ord(char)
            # Convert ASCII printable to fullwidth equivalents
            if 0x21 <= code <= 0x7E:
                result += chr(code + 0xFEE0)
            elif char == " ":
                result += "\u3000"  # fullwidth space
            else:
                result += char
        return result

    @commands.command(aliases=['vapor', 'aesthetic'])
    async def vaporwave(self, ctx, *, text: str):
        """Ｃｏｎｖｅｒｔ ｔｅｘｔ ｔｏ ｖａｐｏｒｗａｖｅ"""
        result = self._vaporize(text)
        if len(result) > 2000:
            await ctx.send("Ｔｏｏ ｌｏｎｇ")
            return
        await ctx.send(result)

    @app_commands.command(name="vaporwave", description="Ｃｏｎｖｅｒｔ ｔｅｘｔ ｔｏ ｖａｐｏｒｗａｖｅ ａｅｓｔｈｅｔｉｃ")
    @app_commands.describe(text="Text to vaporize")
    async def vaporwave_slash(self, interaction: discord.Interaction, text: str):
        result = self._vaporize(text)
        if len(result) > 2000:
            await interaction.response.send_message("Ｔｏｏ ｌｏｎｇ")
            return
        await interaction.response.send_message(result)


async def setup(bot):
    await bot.add_cog(Vaporwave(bot))
