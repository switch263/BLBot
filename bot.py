#!/usr/bin/env python
import os
import sys
import logging
import discord
from discord.ext import commands
from pathlib import Path
import asyncio

# Configure logging
log_level_str = os.environ.get('LOG_LEVEL', "DEBUG").upper()
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(stream=sys.stdout, level=log_level_str, format=log_format)
logger = logging.getLogger(__name__)

async def setup_bot():
    # Check for the Discord token
    token = os.environ.get('DISCORD_TOKEN')
    if not token:
        logger.critical("DISCORD_TOKEN environment variable not set")
        sys.exit(1)

    # Set intents and description
    intents = discord.Intents.all()
    description = """A very basic discord bot, originally written for my group of gaming idiots called the Bored Lunatics. Hence the name blbot! Find the source code at https://github.com/switch263/BLBot"""
    bot = commands.Bot(command_prefix='!', description=description, intents=intents)

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
    try:
        bot.load_extension("cogs.stats")
        stats_cog = bot.get_cog("Stats")
        if stats_cog and hasattr(stats_cog, 'setup_database'):
            await stats_cog.setup_database()
    except Exception as e:
        logger.critical(f"Error loading stats cog: {e}")

    for file in os.listdir(os.path.join(cwd, "cogs")):
        if file.endswith(".py") and not file.startswith("_") and file != "stats.py":
            bot.load_extension(f"cogs.{file[:-3]}")

    await bot.start(token)

if __name__ == '__main__':
    asyncio.run(setup_bot())

