import discord
from discord.ext import commands
import random
import requests
import json
from discord.ext import commands

from config import *

description = '''An example bot to showcase the discord.ext.commands extension
module.
There are a number of utility commands being showcased here.'''
bot = commands.Bot(command_prefix='?', description=description)


@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')


@bot.command()
async def roll(ctx, dice: str):
    """Rolls a dice in NdN format."""
    try:
        rolls, limit = map(int, dice.split('d'))
    except Exception:
        await ctx.send('Format has to be in NdN!')
        return

    result = ', '.join(str(random.randint(1, limit)) for r in range(rolls))
    print(result)
    await ctx.send(result)


@bot.command(description='For when you wanna settle the score some other way')
async def choose(ctx, *choices: str):
    """Chooses between multiple choices."""
    await ctx.send(random.choice(choices))


@bot.command()
async def repeat(ctx, times: int, content='repeating...'):
    """Repeats a message multiple times."""
    for i in range(times):
        await ctx.send(content)


@bot.command()
async def joined(ctx, member: discord.Member):
    """Says when a member joined."""
    await ctx.send('{0.name} joined in {0.joined_at}'.format(member))


@bot.command()
async def eightball(ctx):
    """ Return an 8-ball response."""
    answers = [
        "Ask Again Later",
        "Better Not Tell You Now",
        "Concentrate and Ask Again",
        "Don't Count on It",
        "It Is Certain",
        "Most Likely",
        "My Reply is No",
        "My Sources Say No",
        "No",
        "Outlook Good",
        "Outlook Not So Good",
        "Reply Hazy, Try Again",
        "Signs Point to Yes",
        "Yes",
        "Yes, Definitely",
        "You May Rely On It",
    ]
    await ctx.send(":8ball:" + random.choice(answers))

@bot.command()
async def weather(ctx, arg, country='US'):
    print(arg)
    print(country)
    city_name = arg + ',' + country
    print(city_name)
    API_KEY = openweatherapikey
    #api = "http://api.openweathermap.org/data/2.5/forecast?units=metric&q={city}&APPID={key}"
    api = "http://api.openweathermap.org/data/2.5/weather?units=imperial&q={city}&APPID={key}"

    url = api.format(city=city_name, key=API_KEY)
    response = requests.get(url)
    js = response.json()

    print(url)
    print(js)

    if js["cod"] == '404':
        value = "404, dodging a barf"

    else:
        value = "Temperature: {}\n{}, {}\nDescription:{}".format(js["main"]["temp"], js["name"],js["sys"]["country"],js["weather"][0]["main"])

    await ctx.send(value)


@bot.command()
async def test(ctx, *, message):
    await ctx.send(message)

@bot.command()
async def lenny(ctx):
    lenny = requests.get("https://api.lenny.today/v1/random?limit=1").json()
    print(type(lenny))
    await ctx.send(lenny[0]["face"])

bot.run(token)
