from discord.ext import commands
import random


class temperature(commands.Cog):
  def __init__(self, bot):
    self.bot = bot

  @commands.Cog.listener()
  async def on_ready(self):
    print("Temperature conversion module has been loaded\n-----")

  @commands.command(aliases=['ctf'])
  async def CTF(self, ctx, temp: int):
    """ converts celcius to fahrenheit"""
    convert = round(temp * 1.8 + 32, 1)
    await ctx.send(":thermometer: " + str(temp) + "°C is " + str(convert) +
                   "°F")

  @commands.command(aliases=['ftc'])
  async def FTC(self, ctx, temp: int):
    """ converts fahrenheit to celcius"""
    convert = round((temp - 32) / 1.8, 1)
    await ctx.send(":thermometer: " + str(temp) + "°F is " + str(convert) +
                   "°C")


def setup(bot):
  bot.add_cog(temperature(bot))
