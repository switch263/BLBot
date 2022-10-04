from discord.ext import commands
import requests


class tarkov_time(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("Tarkov time module has been loaded\n-----")

    @commands.command(aliases=['ttime','tarkovtime'])
    async def tarkov_time(self, ctx):
        """ fetches current in-game times for Escape from Tarkov"""
        message = ""
        timejson = requests.get("https://tarkov-time.adam.id.au/api").json()
        for side in timejson:
            message = message + side + ": " + timejson[side] + "\n"
        print(message)
        await ctx.send(message)


def setup(bot):
    bot.add_cog(tarkov_time(bot))

