from discord.ext import commands
import requests
import os
import xkcd
import re

class xkcdComic(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @commands.Cog.listener()
    async def on_ready(self):
        print("xkcd module has been loaded\n-----")

    @commands.command(name='#xkcd')
    async def getLatestComicNum(self, ctx):
        """ Returns the latest xkcd comic """
        await ctx.send(xkcd.getLatestComicNum())

    @commands.command(name='xkcd')
    async def getImageLink(self, ctx, arg="323"):
        """ Returns image of comic. Try !xkcd [number] """
        checker = re.search(r"[0-9]+", arg)
        print(checker.group(0))
        if checker:
            try:
                lookUp = xkcd.Comic(checker.group(0))
                await ctx.send(f"{lookUp.getTitle()} {lookUp.getImageLink()}")
            except:
                pass

def setup(bot):
    bot.add_cog(xkcdComic(bot))

