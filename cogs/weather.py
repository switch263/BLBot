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
        """ Checks Weather. !w 78704, !w London, UK, etc"""
        city_name = arg + ',' + country
        api = "http://api.openweathermap.org/data/2.5/weather?units=imperial&q={city}&APPID={key}"

        url = api.format(city=city_name, key=OPENWEATHER_API_KEY)
        response = requests.get(url)
        js = response.json()

        if js["cod"] == '404':
            value = ":cowboy: Sorry partner, I can't find that location."
            await ctx.send(value)


        weather_condition = js["weather"][0]["main"]
        weather_name = js["name"]
        weather_country = js["sys"]["country"]
        weather_temp_f = js["main"]["temp"] 
        weather_temp_c = round((js["main"]["temp"] - 32) / 1.8, 1)
        weather_humidity = js["main"]["humidity"]
        weather_description = js["weather"][0]["description"]
        weather_wind_mph = js["wind"]["speed"]
        weather_wind_kph = round(js["wind"]["speed"] * 1.609, 1)


        await ctx.send(f"**Weather Report:** {weather_name}, {weather_country}\n**Temperature:** {weather_temp_f}°f / {weather_temp_c}°c **Conditions:** {weather_condition}, {weather_description} **Humidity:** {weather_humidity}% **Wind Speed:** {weather_wind_mph}mph / {weather_wind_kph}kph")

def setup(bot):
    bot.add_cog(weather(bot))

