#!env/bin/python3.7
import discord
import random
import os
from pathlib import Path
import json
from discord.ext import commands
from config import *
import logging
import sys

token = os.environ.get('DISCORD_TOKEN')
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

description = """A very basic discord bot, originally written for my group of gaming idiots called the Bored Lunatics. Hence the name blbot! Find the source code at https://github.com/switch263/BLBot"""
bot = commands.Bot(command_prefix='!', description=description)

cwd = Path(__file__).parents[0]
cwd = str(cwd)


@bot.event
async def on_ready():
    print('Logged in as {}, {}'.format(bot.user.name, bot.user.id))
    print('------')


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Not a thing I know how to do, partner! :cowboy:")
    else:
        raise ValueError(error)


if __name__ == '__main__':
    # When running this file, if it is the 'main' file
    # I.E its not being imported from another python file run this
    for file in os.listdir(cwd + "/cogs"):
        if file.endswith(".py") and not file.startswith("_"):
            bot.load_extension(f"cogs.{file[:-3]}")
    bot.run(token)
