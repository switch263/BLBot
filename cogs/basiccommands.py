import discord
from discord.ext import commands
import requests
import random


class BasicCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("Ping module has been loaded\n-----")

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

    @commands.command(description='For when you wanna settle the score some other way')
    async def choose(self, ctx, *choices: str):
        """Chooses between multiple choices."""
        await ctx.send(random.choice(choices))

    @commands.command()
    async def repeat(self, ctx, times: int, content='repeating...'):
        """Repeats a message multiple times."""
        for i in range(times):
            await ctx.send(content)

    @commands.command()
    async def joined(self, ctx, member: discord.Member):
        """Says when a member joined."""
        await ctx.send('{0.name} joined in {0.joined_at}'.format(member))

    @commands.command()
    async def test(self, ctx, *, message):
        await ctx.send(message)

    @commands.command()
    async def lenny(self, ctx):
        lenny = requests.get("https://api.lenny.today/v1/random?limit=1").json()
        await ctx.send(lenny[0]["face"])


def setup(bot):
    bot.add_cog(BasicCommands(bot))

