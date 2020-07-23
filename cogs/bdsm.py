import discord
from discord.ext import commands
import codecs
import json
import textgen

"""
I'm bored and this is funny :D
"""

class bdsm(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("BDSM module has been loaded\n-----")

    @commands.command(aliases=['bdsm'])
    async def BDSM(self, ctx, member: discord.Member = None):
        if member:
            print("lol bdsm!")
            user = ctx.message.author
            victim = member
            with codecs.open("bdsm.json", encoding="utf-8") as f:
                bdsm_data = json.load(f)
            generator = textgen.TextGenerator(bdsm_data["templates"], bdsm_data["parts"], variables={"user": str(victim)})
            bdsmmsg = "%s %s" % (user.mention, generator.generate_string())
            await ctx.send(bdsmmsg)
        else:
            bdsmmsg = "{} is pro-pain and pro pro-pain-accessories!"
            bdsmmsg = bdsmmsg.format(ctx.message.author.mention)
            await ctx.send(bdsmmsg)

def setup(bot):
    bot.add_cog(bdsm(bot))