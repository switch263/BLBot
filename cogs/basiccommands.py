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

        # Security: Prevent DoS by limiting rolls and dice size
        if rolls < 1 or rolls > 100:
            await ctx.send('Number of rolls must be between 1 and 100!')
            return
        if limit < 1 or limit > 1000:
            await ctx.send('Dice sides must be between 1 and 1000!')
            return

        result = ', '.join(str(random.randint(1, limit)) for r in range(rolls))
        await ctx.send(result)

    @commands.command(description='For when you wanna settle the score some other way', name="Choose",
                      aliases=['pick', 'Pick', 'choose'])
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

    # Removed: test command (security risk - echoes unvalidated user input)

    @commands.command()
    async def lenny(self, ctx):
        await ctx.send(lenny())

    @commands.command(name="Reload", aliases=['reload'])
    @commands.is_owner()
    async def Reload(self, ctx):
        try:
            for cog in list(self.bot.cogs):
                print("Unloaded {}".format(cog))
                await self.bot.unload_extension("cogs.{}".format(cog.lower()))
            await ctx.send("All cogs unloaded")
            message = ""
            # Security: Use os.path.join to prevent path traversal
            cogs_dir = os.path.join(cwd, "cogs")
            for file in os.listdir(cogs_dir):
                if file.endswith(".py") and not file.startswith("_"):
                    await self.bot.load_extension(f"cogs.{file[:-3]}")
                    message += "{} reloaded\n".format(file[:-3])
            await ctx.send(message)
        except ValueError as e:
            # Security: Don't expose internal error details
            await ctx.send("Unable to reload cogs. Check console for details.")

    @Reload.error
    async def Reload_error(self, ctx, error):
        await ctx.send("Unable to reload cogs. {}".format(error))


async def setup(bot):
    await bot.add_cog(BasicCommands(bot))

