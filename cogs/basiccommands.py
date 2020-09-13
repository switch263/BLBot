import discord
from discord.ext import commands
import requests
import random
import os
from pathlib import Path
from lenny import lenny

cwd = Path(__file__).parents[0]
cwd = str(os.getcwd())

class BasicCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("Basic commands module has been loaded\n-----")

    @commands.command(name='Ping', aliases=['ping'])
    async def ping(self, ctx):
        await ctx.send('Pong!')

    @commands.command()
    async def roll(self, ctx, dice: str):
        """Rolls a dice in NdN format."""
        try:
            rolls, limit = map(int, dice.split('d'))
        except Exception:
            await ctx.send('Format has to be in NdN!')
            return

        result = ', '.join(str(random.randint(1, limit)) for r in range(rolls))
        await ctx.send(result)

    @commands.command(description='For when you wanna settle the score some other way', name="Choose", aliases=['pick',
                                                                                                                'Pick'])
    async def choose(self, ctx, *choices: str):
        """Chooses between multiple choices."""
        await ctx.send(random.choice(choices))

    # Disabled because this is real dumb to allow people to do...
    #@commands.command()
    #async def repeat(self, ctx, times: int, content='repeating...'):
    #    """Repeats a message multiple times."""
    #    for i in range(times):
    #        await ctx.send(content)

    @commands.command()
    async def joined(self, ctx, member: discord.Member):
        """Says when a member joined."""
        await ctx.send('{0.name} joined in {0.joined_at}'.format(member))

    @commands.command()
    async def test(self, ctx, *, message):
        await ctx.send(message)

    @commands.command()
    async def lenny(self, ctx):
        await ctx.send(lenny())

    @commands.command(name="Reload", aliases=['reload'])
    @commands.is_owner()
    async def Reload(self, ctx):
        try:
            for cog in list(self.bot.cogs):
                print("Unloaded {}".format(cog))
                self.bot.unload_extension("cogs.{}".format(cog.lower()))
            await ctx.send("All cogs unloaded")
            message = ""
            for file in os.listdir(cwd + "/cogs"):
                if file.endswith(".py") and not file.startswith("_"):
                    self.bot.load_extension(f"cogs.{file[:-3]}")
                    message += "{} reloaded\n".format(file[:-3])
            await ctx.send(message)
        except ValueError as e:
            await ctx.send("Unable to reload cogs. Check console for possible traceback. {}".format(e))

    @Reload.error
    async def Reload_error(self, ctx, error):
        await ctx.send("Unable to reload cogs. {}".format(error))


def setup(bot):
    bot.add_cog(BasicCommands(bot))

