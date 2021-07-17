import discord
from discord.ext import commands

class ohio(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("Ohio module has been loaded\n-----")

    @commands.command(aliases=['Ohio'])
    async def lasaga(self, ctx, member: discord.Member = None):
        if member:
            target = member.mention
            await ctx.send("1-800-FUCK-OHIO! " + target)
        else:
            await ctx.send("1-800-FUCK-OHIO!")


def setup(bot):
    bot.add_cog(ohio(bot))