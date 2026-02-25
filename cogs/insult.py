import discord
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
        try:
            # Security: Use context manager to ensure file is closed
            with open("list-of-insults", "r") as f:
                insult_list = f.readlines()
        except FileNotFoundError:
            await ctx.send("Error: Insult list not found.")
            return
        except Exception as e:
            await ctx.send("Error loading insults.")
            return

        if not insult_list:
            await ctx.send("No insults available.")
            return

        random.seed()
        insult = insult_list[random.randrange(len(insult_list))].strip()
        if member:
            insultmsg = "Hey, {}! {} said you're a {}!"
            insultmsg = insultmsg.format(member.mention, ctx.message.author.mention, insult)
            await ctx.send(insultmsg)
        else:
            insultmsg = "Hey, {}! You're a {}!"
            insultmsg = insultmsg.format(ctx.message.author.mention, insult)
            await ctx.send(insultmsg)


async def setup(bot):
    await bot.add_cog(insult(bot))

