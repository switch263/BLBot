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
        lowerString = mockstring.lower()
        output_text = ""
        counter = 0
        for char in lowerString:
            if char != ' ':
                counter += 1
            if counter % 2 == 0:
                output_text += char.lower()
            else:
                output_text += char.upper()
        await ctx.send(output_text)


def setup(bot):
    bot.add_cog(mock(bot))
