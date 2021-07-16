import discord
from discord.ext import commands

kevid='<@361219124979826698>'

class ohio(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("Ohio module has been loaded\n-----")

    @commands.command(aliases=['Ohio'])
    async def lasaga(self, ctx):
        await ctx.send("1-800-FUCK-OHIO! " + kevid)


def setup(bot):
    bot.add_cog(ohio(bot))