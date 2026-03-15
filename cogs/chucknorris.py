import discord
import aiohttp
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger(__name__)


class ChuckNorrisFacts(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.timeout = aiohttp.ClientTimeout(total=10)

    async def _fetch_fact(self) -> str:
        """Fetch a random Chuck Norris fact."""
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.get('https://api.chucknorris.io/jokes/random') as response:
                response.raise_for_status()
                data = await response.json()
                return data['value']

    @commands.command(name='chucknorris', help='Get a random Chuck Norris fact')
    async def chuck_norris_fact(self, ctx):
        try:
            await ctx.send(await self._fetch_fact())
        except TimeoutError:
            await ctx.send('Request timed out. Please try again.')
        except aiohttp.ClientError:
            await ctx.send('Failed to fetch Chuck Norris fact.')
        except KeyError:
            await ctx.send('Failed to parse Chuck Norris fact response.')
        except Exception:
            await ctx.send('An error occurred.')

    @app_commands.command(name="chucknorris", description="Get a random Chuck Norris fact")
    async def chuck_norris_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            await interaction.followup.send(await self._fetch_fact())
        except TimeoutError:
            await interaction.followup.send('Request timed out. Please try again.')
        except aiohttp.ClientError:
            await interaction.followup.send('Failed to fetch Chuck Norris fact.')
        except KeyError:
            await interaction.followup.send('Failed to parse Chuck Norris fact response.')
        except Exception:
            await interaction.followup.send('An error occurred.')

async def setup(bot):
    await bot.add_cog(ChuckNorrisFacts(bot))
