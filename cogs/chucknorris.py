import discord
import requests
from discord.ext import commands

class ChuckNorrisFacts(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='chucknorris', help='Get a random Chuck Norris fact')
    async def chuck_norris_fact(self, ctx):
        url = 'https://api.chucknorris.io/jokes/random'
        try:
            response = requests.get(url)
            response.raise_for_status()  # Raise exception for bad status codes
            chuck_fact = response.json()['value']
            await ctx.send(chuck_fact)
        except requests.exceptions.RequestException as e:
            await ctx.send(f'Failed to fetch Chuck Norris fact: {e}')
        except KeyError:
            await ctx.send('Failed to parse Chuck Norris fact response.')
        except Exception as e:
            await ctx.send(f'An error occurred: {e}')

def setup(bot):
    bot.add_cog(ChuckNorrisFacts(bot))

