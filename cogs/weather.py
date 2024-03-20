from discord.ext import commands
import requests
import os

API_KEY = os.environ.get('WEATHER_API_KEY')
API_URL = os.environ.get('WEATHER_API_URL')

class weather(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("Weather module has been loaded\n-----")

    @commands.command(name='Weather', aliases=['weather', 'w'])
    async def weather(self, ctx, arg):
        """ Checks Weather. !w 78704, !w London, UK, etc"""
        lookup = arg.replace(" ", "+")
        api = f"{API_URL}\"{lookup}\"/{API_KEY}"
        response = requests.get(api)
        js = response.json()
        weather_message = js["discord"]
        await ctx.send(f"{weather_message}")

def setup(bot):
    bot.add_cog(weather(bot))

