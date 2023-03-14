import os
import random
import datetime
import discord
from discord.ext import commands
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

    @commands.command(name='ping')
    async def ping(self, ctx):
        timestamp = ctx.message.created_at.astimezone(datetime.timezone.utc)
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        latency = now_utc - timestamp
        latency_in_ms = round(latency.total_seconds() * 1000)
        await ctx.send(f'Pong! ({latency_in_ms} ms)')

    @commands.command(name="roll")
    async def roll(self, ctx, dice: str):
        """Rolls a dice in NdN format."""
        try:
            rolls, limit = map(int, dice.split('d'))
        except ValueError:
            await ctx.send('Format has to be in NdN!')
            return

        result = ', '.join(str(random.randint(1, limit)) for _ in range(rolls))
        await ctx.send(result)

    @commands.command(name="choose",
                      aliases=['pick'])
    async def choose(self, ctx, *choices: str):
        """Chooses between multiple choices."""
        await ctx.send(random.choice(choices))

    @commands.command(name="joined")
    async def joined(self, ctx, member: discord.Member):
        """Says when a member joined."""
        await ctx.send(f'{member.name} joined in {member.joined_at}')

    @commands.command(name="test")
    async def test(self, ctx, *, message):
        await ctx.send(message)

    @commands.command(name="lenny")
    async def lenny(self, ctx):
        await ctx.send(lenny())

    @commands.command(name="reload")
    @commands.is_owner()
    async def reload_cogs(self, ctx):
        try:
            for cog in list(self.bot.cogs):
                self.bot.unload_extension(f"cogs.{cog.lower()}")
                print(f"Unloaded {cog}")
            await ctx.send("All cogs unloaded")

            message = ""
            for file in os.listdir(cwd + "/cogs"):
                if file.endswith(".py") and not file.startswith("_"):
                    self.bot.load_extension(f"cogs.{file[:-3]}")
                    message += f"{file[:-3]} reloaded\n"

            await ctx.send(message)

        except Exception as e:
            await ctx.send(f"Unable to reload cogs. Check console for possible traceback. {e}")

    @reload_cogs.error
    async def reload_cogs_error(self, ctx, error):
        await ctx.send(f"Unable to reload cogs. {error}")


def setup(bot):
    bot.add_cog(BasicCommands(bot))
