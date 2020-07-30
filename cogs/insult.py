from discord.ext import commands
import random

class insult(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("Insult module has been loaded\n-----")

    @commands.command(aliases=['Insult'])
    async def insult(self, ctx, member: discord.Member = None):
        """ Insult the target if one is given, otherwise insult the user that asked. """
        with open(list-of-insults) as f:
            insult_list = f.readlines()

        random.seed()
        insult = insult_list[random.randrange(len(insult_list))]
        if member:
            insultmsg = "Hey, {}! {} said you're a {}!"
            insultmsg = insultmsg.format(member.mention, ctx.message.author.mention, insult)
            await ctx.send(insultmsg)
        else:
            insultmsg = "Hey, {}! You're a {}!"
            insultmsg = insultmsg.format(ctx.message.author.mention, insult)
            await ctx.send(insultmsg)


def setup(bot):
    bot.add_cog(insult(bot))

