import discord
from discord.ext import commands
from discord import app_commands
import random
import os
import logging
from pathlib import Path
from lenny import lenny

logger = logging.getLogger(__name__)
cwd = str(os.getcwd())

class BasicCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Basic commands module has been loaded")

    # --- Ping ---
    @commands.command(name='Ping', aliases=['ping'])
    async def ping(self, ctx):
        await ctx.send('Pong!')

    @app_commands.command(name="ping", description="Check if the bot is alive")
    async def ping_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message('Pong!')

    # --- Roll ---
    def _roll_dice(self, dice: str) -> str:
        """Parse NdN format and return results or error message."""
        try:
            rolls, limit = map(int, dice.split('d'))
        except Exception:
            return 'Format has to be in NdN!'

        if rolls < 1 or rolls > 100:
            return 'Number of rolls must be between 1 and 100!'
        if limit < 1 or limit > 1000:
            return 'Dice sides must be between 1 and 1000!'

        return ', '.join(str(random.randint(1, limit)) for r in range(rolls))

    @commands.command()
    async def roll(self, ctx, dice: str):
        """Rolls a dice in NdN format."""
        await ctx.send(self._roll_dice(dice))

    @app_commands.command(name="roll", description="Roll dice in NdN format (e.g. 2d6)")
    @app_commands.describe(dice="Dice format like 2d6, 1d20, 4d8")
    async def roll_slash(self, interaction: discord.Interaction, dice: str):
        await interaction.response.send_message(self._roll_dice(dice))

    # --- Choose ---
    @commands.command(description='For when you wanna settle the score some other way', name="Choose",
                      aliases=['pick', 'Pick', 'choose'])
    async def choose(self, ctx, *choices: str):
        """Chooses between multiple choices."""
        await ctx.send(random.choice(choices))

    @app_commands.command(name="choose", description="Choose between multiple options")
    @app_commands.describe(choices="Options separated by commas (e.g. pizza, tacos, burgers)")
    async def choose_slash(self, interaction: discord.Interaction, choices: str):
        options = [c.strip() for c in choices.split(',') if c.strip()]
        if not options:
            await interaction.response.send_message("Give me some choices separated by commas!")
            return
        await interaction.response.send_message(random.choice(options))

    # --- Joined ---
    @commands.command()
    async def joined(self, ctx, member: discord.Member):
        """Says when a member joined."""
        await ctx.send('{0.name} joined in {0.joined_at}'.format(member))

    @app_commands.command(name="joined", description="See when a member joined the server")
    @app_commands.describe(member="The member to check")
    async def joined_slash(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.send_message('{0.name} joined in {0.joined_at}'.format(member))

    # --- Lenny ---
    @commands.command()
    async def lenny(self, ctx):
        await ctx.send(lenny())

    @app_commands.command(name="lenny", description="Get a random lenny face")
    async def lenny_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(lenny())

    # --- Reload (prefix-only, owner-only) ---
    @commands.command(name="Reload", aliases=['reload'])
    @commands.is_owner()
    async def Reload(self, ctx):
        try:
            # Unload all currently loaded extensions
            for ext in list(self.bot.extensions):
                logger.info("Unloaded %s", ext)
                await self.bot.unload_extension(ext)
            await ctx.send("All cogs unloaded")
            message = ""
            # Security: Use os.path.join to prevent path traversal
            cogs_dir = os.path.join(cwd, "cogs")
            for file in os.listdir(cogs_dir):
                if file.endswith(".py") and not file.startswith("_"):
                    await self.bot.load_extension(f"cogs.{file[:-3]}")
                    message += "{} reloaded\n".format(file[:-3])
            await ctx.send(message)
        except Exception as e:
            logger.error("Reload failed: %s", e)
            await ctx.send("Unable to reload cogs. Check console for details.")

    @Reload.error
    async def Reload_error(self, ctx, error):
        logger.error("Reload error: {}".format(error))
        await ctx.send("Unable to reload cogs. Check console for details.")


async def setup(bot):
    await bot.add_cog(BasicCommands(bot))
