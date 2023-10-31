#!/usr/bin/env python
import discord
from discord.ext import commands
from pathlib import Path
import json
import logging
import os
import random
import sys
# Load configuration from a separate file
from config import *

# Configure logging
log_level_str = os.environ.get('LOG_LEVEL', "DEBUG")
log_levels = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG
}
log_level = log_levels.get(log_level_str, logging.DEBUG)
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(stream=sys.stdout, level=log_level, format=log_format)
logger = logging.getLogger(__name__)

# Check for the Discord token
token = os.environ.get('DISCORD_TOKEN')
if not token:
    logger.critical("DISCORD_TOKEN environment variable not set")
    sys.exit(1)

description = """A very basic discord bot, originally written for my group of gaming idiots called the Bored Lunatics. Hence the name blbot! Find the source code at https://github.com/switch263/BLBot"""
bot = commands.Bot(command_prefix='!', description=description)

cwd = str(Path(__file__).parents[0])

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user.name} with user id of {bot.user.id}.")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Not a thing I know how to do, partner! :cowboy:")
    else:
        logger.error(f"Unexpected error occurred: {error}")

# Load cogs from the cogs directory
if __name__ == '__main__':
    for file in os.listdir(os.path.join(cwd, "cogs")):
        if file.endswith(".py") and not file.startswith("_"):
            bot.load_extension(f"cogs.{file[:-3]}")
    bot.run(token)

