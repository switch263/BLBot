import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import logging

logger = logging.getLogger(__name__)


class UrbanDictionary(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.timeout = aiohttp.ClientTimeout(total=10)

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Urban Dictionary module has been loaded")

    async def _lookup(self, term: str) -> discord.Embed | str:
        """Look up a term on Urban Dictionary. Returns an embed or error string."""
        url = "https://api.urbandictionary.com/v0/define"
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, params={"term": term}) as response:
                    response.raise_for_status()
                    data = await response.json()
        except aiohttp.ClientError:
            return "Failed to reach Urban Dictionary. Try again later."
        except Exception as e:
            logger.error(f"Error fetching urban definition: {e}")
            return "An error occurred."

        results = data.get("list", [])
        if not results:
            return f"No definition found for **{term}**."

        entry = results[0]
        definition = entry["definition"].replace("[", "").replace("]", "")
        example = entry.get("example", "").replace("[", "").replace("]", "")

        # Truncate long definitions
        if len(definition) > 1000:
            definition = definition[:997] + "..."
        if len(example) > 500:
            example = example[:497] + "..."

        embed = discord.Embed(
            title=f"Urban Dictionary: {entry['word']}",
            url=entry.get("permalink", ""),
            description=definition,
            color=discord.Color.from_rgb(239, 255, 0)  # UD yellow
        )

        if example:
            embed.add_field(name="Example", value=f"*{example}*", inline=False)

        thumbs_up = entry.get("thumbs_up", 0)
        thumbs_down = entry.get("thumbs_down", 0)
        embed.set_footer(text=f"\U0001f44d {thumbs_up}  \U0001f44e {thumbs_down}  |  by {entry.get('author', 'Anonymous')}")

        return embed

    @commands.command(aliases=['ud', 'define'])
    async def urban(self, ctx, *, term: str):
        """Look up a word on Urban Dictionary."""
        result = await self._lookup(term)
        if isinstance(result, discord.Embed):
            await ctx.send(embed=result)
        else:
            await ctx.send(result)

    @app_commands.command(name="urban", description="Look up a word on Urban Dictionary")
    @app_commands.describe(term="The word or phrase to look up")
    async def urban_slash(self, interaction: discord.Interaction, term: str):
        await interaction.response.defer(thinking=True)
        result = await self._lookup(term)
        if isinstance(result, discord.Embed):
            await interaction.followup.send(embed=result)
        else:
            await interaction.followup.send(result)


async def setup(bot):
    await bot.add_cog(UrbanDictionary(bot))
