import discord
from discord.ext import commands
import random


class mock(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("Mock module has been loaded\n-----")

    @commands.command(aliases=['Mock'])
    async def mock(self, ctx, *, mockstring: str):
        """ Automatic spongebob-mocking-text """
        output_text = ""
        for char in mockstring:
            if char.isalpha():
                if random.random() > 0.5:
                    output_text += char.upper()
                else:
                    output_text += char.lower()
            else:
                output_text += char
        await ctx.send(output_text)


def setup(bot):
    bot.add_cog(mock(bot))
