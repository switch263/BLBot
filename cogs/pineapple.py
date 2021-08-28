import discord
from discord.ext import commands


class pineapple(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("Pineapple module has been loaded\n-----")

    @commands.command(aliases=['Pineapple'])
    async def pineapple(self, ctx):
        pineappleimg = 'https://user-images.githubusercontent.com/16721240/131228780-d95f9e41-2de1-41af-a791-e4643e5bd936.png'
        await ctx.send(pineappleimg)


def setup(bot):
    bot.add_cog(pineapple(bot))