import discord
from discord.ext import commands


class hf(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("hf module has been loaded\n-----")

    @commands.command(aliases=['hotfuckin','HotFuckin'])
    async def hf(self, ctx, *, mockstring: str):
        """ A Special Response for a Special Group Member """
        message = r'C:\HOTFUCKIN\'
        await ctx.send(message)


def setup(bot):
    bot.add_cog(hf(bot))