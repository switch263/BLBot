import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import random
from typing import Optional


class XKCD(commands.Cog):
    """XKCD comic fetcher with support for latest, specific, and random comics"""
    
    def __init__(self, bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None
        self.timeout = aiohttp.ClientTimeout(total=10)
        self.base_url = "https://xkcd.com"
        self.latest_comic_num = None
        
    async def cog_load(self):
        """Create aiohttp session when cog loads"""
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        # Get the latest comic number for random selection
        try:
            await self.update_latest_comic()
        except Exception:
            pass  # Will try again on first request
            
    async def cog_unload(self):
        """Close aiohttp session when cog unloads"""
        if self.session:
            await self.session.close()
    
    @commands.Cog.listener()
    async def on_ready(self):
        print("XKCD module has been loaded\n-----")
    
    async def update_latest_comic(self):
        """Update the cached latest comic number"""
        data = await self.fetch_comic()
        if data:
            self.latest_comic_num = data.get("num")
    
    async def fetch_comic(self, comic_num: Optional[int] = None) -> Optional[dict]:
        """
        Fetch xkcd comic data from API
        
        Args:
            comic_num: Comic number to fetch, None for latest
            
        Returns:
            dict: Comic data or None on error
        """
        if not self.session:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
        
        if comic_num:
            url = f"{self.base_url}/{comic_num}/info.0.json"
        else:
            url = f"{self.base_url}/info.0.json"
        
        try:
            async with self.session.get(url) as response:
                if response.status == 404:
                    return None
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError:
            return None
        except Exception:
            return None
    
    def create_comic_embed(self, data: dict) -> discord.Embed:
        """
        Create a Discord embed from comic data
        
        Args:
            data: Comic data from API
            
        Returns:
            discord.Embed: Formatted comic embed
        """
        embed = discord.Embed(
            title=f"xkcd #{data['num']}: {data['title']}",
            url=f"{self.base_url}/{data['num']}/",
            color=discord.Color.blue(),
            description=data.get('alt', '')
        )
        
        embed.set_image(url=data['img'])
        
        # Add date info
        date_str = f"{data['month']}/{data['day']}/{data['year']}"
        embed.set_footer(text=f"Published: {date_str} | Hover over comic for alt text!")
        
        return embed
    
    @commands.command(name='xkcd', aliases=['comic'])
    async def xkcd_command(self, ctx, comic_num: Optional[int] = None):
        """
        Get an xkcd comic
        
        Usage:
            !xkcd          - Get the latest comic
            !xkcd random   - Get a random comic
            !xkcd 353      - Get comic #353
        """
        async with ctx.typing():
            # Handle "random" as argument
            if comic_num is None and ctx.message.content.split()[-1].lower() == 'random':
                # Update latest if we don't have it
                if not self.latest_comic_num:
                    await self.update_latest_comic()
                
                if self.latest_comic_num:
                    comic_num = random.randint(1, self.latest_comic_num)
            
            # Validate comic number
            if comic_num is not None and comic_num < 1:
                await ctx.send("Comic number must be positive!")
                return
            
            # Fetch the comic
            data = await self.fetch_comic(comic_num)
            
            if not data:
                if comic_num:
                    await ctx.send(f"Could not find comic #{comic_num}. The comic may not exist.")
                else:
                    await ctx.send("Failed to fetch the latest comic. Please try again.")
                return
            
            # Update our cached latest comic number if fetching latest
            if comic_num is None and data.get("num"):
                self.latest_comic_num = data["num"]
            
            # Create and send embed
            embed = self.create_comic_embed(data)
            await ctx.send(embed=embed)
    
    @commands.command(name='xkcd_random', aliases=['randomxkcd', 'rxkcd'])
    async def xkcd_random(self, ctx):
        """Get a random xkcd comic"""
        async with ctx.typing():
            # Update latest if we don't have it
            if not self.latest_comic_num:
                await self.update_latest_comic()
            
            if not self.latest_comic_num:
                await ctx.send("Failed to get comic range. Please try again.")
                return
            
            # Get random comic
            comic_num = random.randint(1, self.latest_comic_num)
            data = await self.fetch_comic(comic_num)
            
            if not data:
                await ctx.send("Failed to fetch random comic. Please try again.")
                return
            
            embed = self.create_comic_embed(data)
            await ctx.send(embed=embed)
    
    @app_commands.command(name="xkcd", description="Get an xkcd comic")
    @app_commands.describe(
        comic_num="Comic number (leave empty for latest, use 0 for random)"
    )
    async def xkcd_slash(self, interaction: discord.Interaction, comic_num: Optional[int] = None):
        """Slash command version of xkcd"""
        await interaction.response.defer(thinking=True)
        
        # Handle random (0 = random)
        if comic_num == 0:
            if not self.latest_comic_num:
                await self.update_latest_comic()
            
            if self.latest_comic_num:
                comic_num = random.randint(1, self.latest_comic_num)
            else:
                await interaction.followup.send("Failed to get comic range. Please try again.")
                return
        
        # Validate comic number
        if comic_num is not None and comic_num < 0:
            await interaction.followup.send("Comic number must be 0 (random) or positive!")
            return
        
        # Fetch the comic
        data = await self.fetch_comic(comic_num)
        
        if not data:
            if comic_num:
                await interaction.followup.send(f"Could not find comic #{comic_num}. The comic may not exist.")
            else:
                await interaction.followup.send("Failed to fetch the latest comic. Please try again.")
            return
        
        # Update our cached latest comic number if fetching latest
        if comic_num is None and data.get("num"):
            self.latest_comic_num = data["num"]
        
        # Create and send embed
        embed = self.create_comic_embed(data)
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(XKCD(bot))
