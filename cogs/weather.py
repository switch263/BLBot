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
        """ Check the weather at the closest station near you. Defaults to US. Displayed in imperial units. Usage: !weather \"Austin, TX\" or !weather 78704 """
        city_name = arg + ',' + country
        api = "http://api.openweathermap.org/data/2.5/weather?units=imperial&q={city}&APPID={key}"

        url = api.format(city=city_name, key=OPENWEATHER_API_KEY)
        response = requests.get(url)
        js = response.json()

        if js["cod"] == '404':
            value = "Sorry partner, I can't find that location."

        else:
            value = "Station: {}, {}\nTemperature: {}°F (Low {}°F High {}°F)\nHumidity: {}%\nConditions: {}, {}\nWind: {}mph".format(
                js["name"], js["sys"]["country"], js["main"]["temp"],
                js["main"]["temp_min"], js["main"]["temp_max"],
                js["main"]["humidity"], js["weather"][0]["main"],
                js["weather"][0]["description"], js["wind"]["speed"])

        await ctx.send(value)


def setup(bot):
    bot.add_cog(weather(bot))
