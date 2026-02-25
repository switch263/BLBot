"""
Discord Weather Cog - Improved version using discord.flvrtown.com API

Features:
- Fully async, non-blocking HTTP requests with timeout
- Rich embed responses
- Proper error handling
- Both prefix and slash command support
- Connection pooling for concurrent requests
- Semaphore to prevent API rate limiting
"""

import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
from datetime import datetime
from typing import Optional
import logging

# Configure the API endpoint
WEATHER_API_URL = "https://discord.flvrtown.com"

# Configure logging
logger = logging.getLogger(__name__)


class WeatherCog(commands.Cog):
    """Weather commands using discord.flvrtown.com API"""
    
    def __init__(self, bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None
        self.timeout = aiohttp.ClientTimeout(total=10)  # 10 second timeout
        # Limit concurrent requests to prevent overwhelming the API
        self.request_semaphore = asyncio.Semaphore(10)  # Max 10 concurrent requests
        
    async def cog_load(self):
        """Create aiohttp session with connection pooling when cog loads"""
        # Configure TCP connector for concurrent connections
        connector = aiohttp.TCPConnector(
            limit=100,  # Total connection pool size
            limit_per_host=30,  # Max connections per host
            ttl_dns_cache=300,  # DNS cache TTL in seconds
            enable_cleanup_closed=True
        )
        
        self.session = aiohttp.ClientSession(
            timeout=self.timeout,
            connector=connector,
            raise_for_status=False  # Handle status codes manually
        )
        logger.info("Weather cog loaded with connection-pooled API session")
        
    async def cog_unload(self):
        """Close aiohttp session when cog unloads"""
        if self.session:
            await self.session.close()
        logger.info("Weather cog unloaded")
    
    @commands.Cog.listener()
    async def on_ready(self):
        print("Weather module has been loaded\n-----")

    async def fetch_weather(self, location: str) -> dict:
        """
        Fetch weather data from the API (non-blocking with connection pooling)
        
        Args:
            location: City name, zip code, or address
            
        Returns:
            dict: Weather data
            
        Raises:
            aiohttp.ClientError: Network errors
            asyncio.TimeoutError: Request timeout
            ValueError: Invalid response
        """
        if not self.session:
            # Fallback: create session if not already initialized
            connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
            self.session = aiohttp.ClientSession(timeout=self.timeout, connector=connector)
            
        url = f"{WEATHER_API_URL}/weather"
        params = {"location": location}
        
        # Use semaphore to limit concurrent requests
        async with self.request_semaphore:
            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    try:
                        error_data = await response.json()
                        raise ValueError(error_data.get("error", "Unknown error"))
                    except aiohttp.ContentTypeError:
                        raise ValueError(f"API error: {response.status}")
                
                return await response.json()

    def create_weather_embed(self, data: dict) -> discord.Embed:
        """
        Create a rich embed from weather data
        
        Args:
            data: Weather data from API
            
        Returns:
            discord.Embed: Formatted weather embed
        """
        # Create embed with color based on temperature
        temp = data["current"]["temperature"]
        if temp >= 80:
            color = discord.Color.red()
        elif temp >= 60:
            color = discord.Color.orange()
        elif temp >= 40:
            color = discord.Color.blue()
        else:
            color = discord.Color.from_rgb(135, 206, 250)  # Light blue
        
        embed = discord.Embed(
            title=f"🌤️ Weather for {data['location'].split(',')[0]}",
            description=data["current"]["weather_description"],
            color=color,
            timestamp=datetime.utcnow()
        )
        
        # Current conditions
        current = data["current"]
        embed.add_field(
            name="🌡️ Temperature",
            value=f"**{current['temperature']}°F**\nFeels like {current['feels_like']}°F",
            inline=True
        )
        
        embed.add_field(
            name="💧 Humidity",
            value=f"{current['humidity']}%",
            inline=True
        )
        
        embed.add_field(
            name="💨 Wind",
            value=f"{current['wind_speed']} mph",
            inline=True
        )
        
        # Today's forecast
        today = data["forecast"][0]
        embed.add_field(
            name="📅 Today's Forecast",
            value=f"High: {today['temp_max']}°F | Low: {today['temp_min']}°F",
            inline=False
        )
        
        # Sunrise/Sunset
        sunrise = datetime.fromisoformat(today["sunrise"]).strftime("%I:%M %p")
        sunset = datetime.fromisoformat(today["sunset"]).strftime("%I:%M %p")
        embed.add_field(
            name="🌅 Sun Times",
            value=f"Sunrise: {sunrise}\nSunset: {sunset}",
            inline=True
        )
        
        # Local time
        local_time = datetime.fromisoformat(data["local_time"]).strftime("%I:%M %p")
        embed.add_field(
            name="🕐 Local Time",
            value=local_time,
            inline=True
        )
        
        # Weather alerts (if any)
        if data.get("alerts") and len(data["alerts"]) > 0:
            alert = data["alerts"][0]
            embed.add_field(
                name="⚠️ Weather Alert",
                value=f"**{alert['event']}**\n{alert['headline'][:100]}...",
                inline=False
            )
            embed.color = discord.Color.red()
        
        # 3-day forecast
        forecast_text = ""
        for day in data["forecast"][1:4]:  # Next 3 days
            date = datetime.strptime(day["date"], "%Y-%m-%d").strftime("%a")
            forecast_text += f"**{date}**: {day['temp_min']}°F - {day['temp_max']}°F, {day['weather_description']}\n"
        
        if forecast_text:
            embed.add_field(
                name="📆 3-Day Forecast",
                value=forecast_text,
                inline=False
            )
        
        # Footer
        embed.set_footer(
            text=f"📍 {data['coordinates']['latitude']:.2f}, {data['coordinates']['longitude']:.2f} | {data['timezone']}"
        )
        
        return embed

    @commands.command(name='weather', aliases=['w', 'forecast'])
    async def weather_command(self, ctx, *, location: str):
        """
        Get weather information for a location (non-blocking, allows concurrent requests)
        
        Usage:
            !weather London
            !w 78704
            !w New York, NY
            !forecast Tokyo
            
        Note: Multiple users can request weather simultaneously without blocking each other
        """
        # Create a task to handle typing indicator without blocking the command
        typing_task = asyncio.create_task(self._handle_typing(ctx))
        
        try:
            # Fetch weather data (fully async, won't block other commands)
            data = await self.fetch_weather(location)
            
            # Create embed (fast, synchronous operation)
            embed = self.create_weather_embed(data)
            
            # Cancel typing if still active and send response
            typing_task.cancel()
            await ctx.send(embed=embed)
                
        except asyncio.TimeoutError:
            typing_task.cancel()
            await ctx.send("⏱️ Request timed out. Please try again.")
            logger.error(f"Timeout fetching weather for: {location}")
                
        except aiohttp.ClientError as e:
            typing_task.cancel()
            await ctx.send("❌ Network error. Please try again later.")
            logger.error(f"Network error fetching weather: {e}")
                
        except ValueError as e:
            typing_task.cancel()
            await ctx.send(f"❌ {str(e)}")
            logger.warning(f"Invalid location: {location}")
                
        except KeyError as e:
            typing_task.cancel()
            await ctx.send("❌ Failed to parse weather data. Please try again.")
            logger.error(f"Missing key in weather data: {e}")
                
        except Exception as e:
            typing_task.cancel()
            await ctx.send("❌ An unexpected error occurred.")
            logger.exception(f"Unexpected error in weather command: {e}")
    
    async def _handle_typing(self, ctx):
        """Handle typing indicator without blocking (runs as background task)"""
        try:
            async with ctx.typing():
                # Keep typing active until cancelled
                await asyncio.sleep(3600)  # 1 hour max
        except asyncio.CancelledError:
            pass  # Expected when request completes

    @app_commands.command(name="weather", description="Get weather information for a location")
    @app_commands.describe(location="City name, zip code, or address (e.g., 'London', '78704', 'New York, NY')")
    async def weather_slash(self, interaction: discord.Interaction, location: str):
        """
        Slash command version of weather (non-blocking, supports concurrent requests)
        
        Usage:
            /weather location:London
            /weather location:78704
            
        Note: Multiple users can request weather simultaneously without blocking each other
        """
        # Defer immediately to prevent timeout (non-blocking)
        await interaction.response.defer(thinking=True)
        
        try:
            # Fetch weather data (fully async, uses connection pooling)
            data = await self.fetch_weather(location)
            
            # Create embed (fast, synchronous operation)
            embed = self.create_weather_embed(data)
            
            # Send response
            await interaction.followup.send(embed=embed)
            
        except asyncio.TimeoutError:
            await interaction.followup.send("⏱️ Request timed out. Please try again.")
            logger.error(f"Timeout fetching weather for: {location}")
            
        except aiohttp.ClientError as e:
            await interaction.followup.send("❌ Network error. Please try again later.")
            logger.error(f"Network error fetching weather: {e}")
            
        except ValueError as e:
            await interaction.followup.send(f"❌ {str(e)}")
            logger.warning(f"Invalid location: {location}")
            
        except KeyError as e:
            await interaction.followup.send("❌ Failed to parse weather data. Please try again.")
            logger.error(f"Missing key in weather data: {e}")
            
        except Exception as e:
            await interaction.followup.send("❌ An unexpected error occurred.")
            logger.exception(f"Unexpected error in weather slash command: {e}")


def setup(bot):
    """Load the cog"""
    bot.add_cog(WeatherCog(bot))
