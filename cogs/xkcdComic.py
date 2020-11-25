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
    async def getImageLink(self, ctx, arg="323"):
        """ Returns image of comic. Try !#xkcd [number] """
        checker = re.search(r"[0-9]+", arg)
        print(checker.group(0))
        if checker:
            try:
                lookUp = xkcd.Comic(checker.group(0))
                await ctx.send(f"{lookUp.getTitle()} {lookUp.getImageLink()}")
            except:
                pass

    @commands.command(name='xkcd')
    async def getImageLink(self, ctx, arg):
        """ Returns image of comic. Try !xkcd [search string] """
        headers = {
            'Connection': 'keep-alive',
            'Accept': '*/*',
            'DNT': '1',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Safari/537.36',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://relevant-xkcd.github.io',
            'Sec-Fetch-Site': 'cross-site',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Dest': 'empty',
            'Referer': 'https://relevant-xkcd.github.io/',
            'Accept-Language': 'en-US,en;q=0.9',
            'sec-gpc': '1',
        }

        data = {
          'search': arg
        }

        response = requests.post('https://relevant-xkcd-backend.herokuapp.com/search', headers=headers, data=data)

        js = response.json()
        xkcd_image = js["results"][0]["image"]
        xkcd_title = js["results"][0]["title"]

        await ctx.send(f"{xkcd_title} {xkcd_image}")
def setup(bot):
    bot.add_cog(xkcdComic(bot))

