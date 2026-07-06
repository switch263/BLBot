import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger(__name__)


class Temperature(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Temperature conversion module has been loaded")

    @commands.command(aliases=['ctf'])
    async def CTF(self, ctx, temp: float):
        """ converts celcius to fahrenheit"""
        convert = round(temp * 1.8 + 32, 1)
        await ctx.send(":thermometer: " + str(temp) + "\u00b0C is " + str(convert) + "\u00b0F")

    @commands.command(aliases=['ftc'])
    async def FTC(self, ctx, temp: float):
        """ converts fahrenheit to celcius"""
        convert = round((temp - 32) / 1.8, 1)
        await ctx.send(":thermometer: " + str(temp) + "\u00b0F is " + str(convert) + "\u00b0C")

    @app_commands.command(name="ctf", description="Convert Celsius to Fahrenheit")
    @app_commands.describe(temp="Temperature in Celsius")
    async def ctf_slash(self, interaction: discord.Interaction, temp: float):
        convert = round(temp * 1.8 + 32, 1)
        await interaction.response.send_message(f":thermometer: {temp}\u00b0C is {convert}\u00b0F")

    @app_commands.command(name="ftc", description="Convert Fahrenheit to Celsius")
    @app_commands.describe(temp="Temperature in Fahrenheit")
    async def ftc_slash(self, interaction: discord.Interaction, temp: float):
        convert = round((temp - 32) / 1.8, 1)
        await interaction.response.send_message(f":thermometer: {temp}\u00b0F is {convert}\u00b0C")


async def setup(bot):
    await bot.add_cog(Temperature(bot))
