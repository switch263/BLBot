import discord
from discord.ext import commands
import random
from pathlib import Path
from lenny import lenny
import logging
from datetime import datetime, timedelta
import pytz
import re

logger = logging.getLogger(__name__)

class BasicCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.start_time = datetime.utcnow()

    def has_admin_role(self, user):
        return any(role.name.lower() == "admin" for role in user.roles)

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Basic commands module has been loaded")

    @commands.command(name='ping', aliases=['Ping'], help="Check if the bot is online.")
    async def ping(self, ctx):
        await ctx.send(f"PONG. Latency is {self.bot.latency:.3f}ms")

    @commands.command(help="Rolls a dice in NdN format. Example: !roll 2d6")
    async def roll(self, ctx, dice: str):
        try:
            rolls, limit = map(int, dice.split('d'))
        except ValueError:
            await ctx.send('Format has to be in NdN!')
            return

        result = ', '.join(str(random.randint(1, limit)) for _ in range(rolls))
        await ctx.send(result)


    @commands.command(help="Displays the join date of a member. Example: !joined @member")
    async def joined(self, ctx, member: discord.Member):
        await ctx.send(f'{member.name} joined in {member.joined_at}')

    @commands.command(help="Sends a message. Example: !test Hello! (Admin only)")
    async def test(self, ctx, *, message):
        if self.has_admin_role(ctx.author):
            await ctx.send(message)
        else:
            await ctx.send("You need to have the Admin role to use this command.")

    @commands.command(help="Sends a lenny face.")
    async def lenny(self, ctx):
        await ctx.send(lenny())

    @commands.command(name="reload", aliases=['Reload'], help="Reloads all cogs. Owner only.")
    @commands.is_owner()
    async def reload_cogs(self, ctx):
        try:
            for cog in list(self.bot.cogs):
                logger.info(f"Unloaded {cog}")
                self.bot.unload_extension(f"cogs.{cog.lower()}")
            await ctx.send("All cogs unloaded")
            message = ""
            cog_files = Path("cogs").glob("*.py")
            for file in cog_files:
                cog_name = file.stem
                self.bot.load_extension(f"cogs.{cog_name}")
                message += f"{cog_name} reloaded\n"
            await ctx.send(message)
        except Exception as e:
            await ctx.send(f"Unable to reload cogs. Check console for possible traceback. {e}")

    @reload_cogs.error
    async def reload_cogs_error(self, ctx, error):
        await ctx.send(f"Unable to reload cogs. {error}")

    @commands.command(help="Displays user and guild info. Admin role required.")
    async def info(self, ctx, *, member: discord.Member = None):
        if member is None:
            member = ctx.author

        if self.has_admin_role(ctx.author):
            user = member
            guild = ctx.guild
            roles = [role.name for role in user.roles if role.name != "@everyone"]
            join_date = user.joined_at.replace(tzinfo=pytz.UTC)

            # Calculate duration since joining
            now = datetime.now(pytz.UTC)
            delta = now - join_date
            years = delta.days // 365
            days = delta.days % 365
            hours, remainder = divmod(delta.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)

            info_str = (
                f"User: {user.name}\n"
                f"Roles: {', '.join(roles)}\n"
                f"Guild ID: {guild.id}\n"
                f"User ID: {user.id}\n"
                f"Channel ID: {ctx.channel.id}\n"
                f"Join Date: {join_date.strftime('%Y-%m-%d %H:%M:%S')} "
                f"({years} years {days} days {hours} hours {minutes} minutes {seconds} seconds)"
            )
            await ctx.send(info_str)
        else:
            await ctx.send("You need to have the Admin role to use this command.")

    @commands.command(help="Displays how long the bot has been running. Admin role required.")
    async def uptime(self, ctx):
        """Displays how long the bot has been running."""
        if self.has_admin_role(ctx.author):
            uptime = datetime.utcnow() - self.bot.start_time
            human_readable = str(uptime).split(".")[0]
            await ctx.send(f"I have been online for {human_readable}")
        else:
            await ctx.send("You need to have the Admin role to use this command.")




def setup(bot):
    bot.add_cog(BasicCommands(bot))


