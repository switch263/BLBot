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
from datetime import datetime, timezone
from typing import Optional
import logging

import user_settings

# Configure the API endpoint
WEATHER_API_URL = "https://discord.flvrtown.com"

# Key for this cog's entry in the shared /set registry.
LOCATION_SETTING = "location"

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

        # Register the saveable "location" preference with the shared /set cog,
        # so players can `/set location 78704` and then just `/weather`.
        user_settings.register(
            key=LOCATION_SETTING,
            label="Weather location",
            description="Default city/zip/address for /weather",
            validate=self._validate_location,
        )
        logger.info("Weather cog loaded with connection-pooled API session")

    @staticmethod
    def _validate_location(raw: str) -> str:
        value = raw.strip()
        if not value:
            raise ValueError("Give a real location, e.g. `London`, `78704`, or `New York, NY`.")
        if len(value) > 100:
            raise ValueError("That location is too long.")
        return value
        
    async def cog_unload(self):
        """Close aiohttp session when cog unloads"""
        if self.session:
            await self.session.close()
        logger.info("Weather cog unloaded")
    
    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Weather module has been loaded")

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

    def fahrenheit_to_celsius(self, fahrenheit: float) -> float:
        """Convert Fahrenheit to Celsius"""
        return round((fahrenheit - 32) * 5 / 9, 1)

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
            # Timezone-AWARE UTC. A naive datetime (e.g. datetime.utcnow()) gets
            # read by discord.py as *local* time and shifted by the host offset,
            # which renders the footer as "Tomorrow at …" on a non-UTC host.
            timestamp=datetime.now(timezone.utc)
        )
        
        # Current conditions
        current = data["current"]
        temp_c = self.fahrenheit_to_celsius(current['temperature'])
        feels_c = self.fahrenheit_to_celsius(current['feels_like'])
        embed.add_field(
            name="🌡️ Temperature",
            value=f"**{current['temperature']}°F ({temp_c}°C)**\nFeels like {current['feels_like']}°F ({feels_c}°C)",
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
        high_c = self.fahrenheit_to_celsius(today['temp_max'])
        low_c = self.fahrenheit_to_celsius(today['temp_min'])
        embed.add_field(
            name="📅 Today's Forecast",
            value=f"High: {today['temp_max']}°F ({high_c}°C) | Low: {today['temp_min']}°F ({low_c}°C)",
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
            min_c = self.fahrenheit_to_celsius(day['temp_min'])
            max_c = self.fahrenheit_to_celsius(day['temp_max'])
            forecast_text += f"**{date}**: {day['temp_min']}°F ({min_c}°C) - {day['temp_max']}°F ({max_c}°C), {day['weather_description']}\n"
        
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

    def _resolve_location(self, invoker: discord.abc.User, location: Optional[str],
                          target: Optional[discord.abc.User]) -> tuple[Optional[str], Optional[str]]:
        """Work out which location to fetch. Returns (location, error_message);
        exactly one is non-None.

        Priority: an explicitly named @user's saved location > a typed location >
        the invoker's own saved location.
        """
        if target is not None:
            saved = user_settings.get_value(target.id, LOCATION_SETTING)
            if not saved:
                who = "You haven't" if target.id == invoker.id else f"**{target.display_name}** hasn't"
                return None, (f"{who} saved a location. "
                              f"Set one with `/set location <place>`.")
            return saved, None

        if location and location.strip():
            return location.strip(), None

        saved = user_settings.get_value(invoker.id, LOCATION_SETTING)
        if not saved:
            return None, ("No location given and you haven't saved one. "
                          "Try `/weather London`, or save a default with "
                          "`/set location <place>` and then just `/weather`.")
        return saved, None

    @commands.command(name='weather', aliases=['w', 'forecast'])
    async def weather_command(self, ctx, *, location: str = None):
        """
        Get weather information for a location (non-blocking, allows concurrent requests)
        
        Usage:
            !weather London
            !w 78704
            !w New York, NY
            !forecast Tokyo
            
        Note: Multiple users can request weather simultaneously without blocking each other
        """
        # `!weather @someone` → pull their saved location instead of a typed one.
        target = ctx.message.mentions[0] if ctx.message.mentions else None
        location, error = self._resolve_location(ctx.author, location, target)
        if error:
            await ctx.send(error)
            return

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

    @app_commands.command(name="weather", description="Get weather for a location, a saved default, or another member")
    @app_commands.describe(
        location="City, zip, or address. Omit to use your saved location.",
        user="Show this member's saved location instead.",
    )
    async def weather_slash(self, interaction: discord.Interaction,
                            location: Optional[str] = None,
                            user: Optional[discord.Member] = None):
        """
        Slash command version of weather (non-blocking, supports concurrent requests)

        Usage:
            /weather location:London
            /weather                 (uses your saved location)
            /weather user:@someone   (uses their saved location)

        Note: Multiple users can request weather simultaneously without blocking each other
        """
        resolved, error = self._resolve_location(interaction.user, location, user)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        location = resolved

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


async def setup(bot):
    """Load the cog"""
    await bot.add_cog(WeatherCog(bot))
