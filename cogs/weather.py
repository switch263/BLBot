from discord.ext import commands
from config import *
import requests
import os

OPENWEATHER_API_KEY = os.environ.get('OPENWEATHER_API_KEY')

class weather(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @commands.Cog.listener()
    async def on_ready(self):
        print("Weather module has been loaded\n-----")

    @commands.command(name='Weather', aliases=['weather', 'w'])
    async def weather(self, ctx, arg, country='US'):
        city_name = arg + ',' + country
        api = "http://api.openweathermap.org/data/2.5/weather?units=imperial&q={city}&APPID={key}"

        url = api.format(city=city_name, key=OPENWEATHER_API_KEY)
        response = requests.get(url)
        js = response.json()

        if js["cod"] == '404':
            value = "Sorry partner, I can't find that location."

        else:
            value = "Station: {1}, {2}\nTemperature: {3}°F (Low {4} High {5})\nHumidity: {6}\nConditions: {7}, {8}\nWind: {9}mph".format(
                    js["name"],
                    js["sys"]["country"],
                    js["main"]["temp"],
                    js["main"]["temp_min"],
                    js["main"]["temp_max"],
                    js["main"]["humidity"],
                    js["weather"][0]["main"],
                    js["weather"][0]["description"],
                    js["wind"]["speed"])

        await ctx.send(value)

def setup(bot):
    bot.add_cog(weather(bot))
