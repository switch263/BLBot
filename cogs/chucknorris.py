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
            # Security: Add timeout to prevent hanging requests
            response = requests.get(url, timeout=10)
            response.raise_for_status()  # Raise exception for bad status codes
            chuck_fact = response.json()['value']
            await ctx.send(chuck_fact)
        except requests.exceptions.Timeout:
            await ctx.send('Request timed out. Please try again.')
        except requests.exceptions.RequestException as e:
            await ctx.send('Failed to fetch Chuck Norris fact.')
        except KeyError:
            await ctx.send('Failed to parse Chuck Norris fact response.')
        except Exception:
            await ctx.send('An error occurred.')

def setup(bot):
    bot.add_cog(ChuckNorrisFacts(bot))

