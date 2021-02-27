import discord
from discord.ext import commands


class lasaga(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("Lasaga module has been loaded\n-----")

    @commands.command(aliases=['Lasaga'])
    async def lasaga(self, ctx):
    lasagaimg = 'https://user-images.githubusercontent.com/1498712/101569286-32851600-39a2-11eb-9a0a-e2b1c7b69fc8.png'
    await ctx.send(lasagaimg)


def setup(bot):
    bot.add_cog(lasaga(bot))