import discord
from discord.ext import commands
import asyncio
import random

class Gaslight(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Format: ("Original Message", "The Edited 'Gaslight' Message")
        self.pairs = [
            ("I totally agree with that.", "I actually think that's a terrible idea."),
            ("Yeah, that's exactly how it works.", "That is literally not how any of this works."),
            ("I'll remember that for later.", "I have already forgotten what we were talking about."),
            ("You make a great point.", "You're just saying words at this point, aren't you?"),
            ("I'm online and ready to help!", "I am currently unavailable. Please leave a message."),
            ("That's my favorite game too.", "I've never heard of that game in my life."),
            ("Sending the link now...", "[Message Deleted]"),
            ("Checking the server status...", "Why are you asking me? I'm just a bot."),
            ("LOL that was actually funny.", "Was that supposed to be a joke?"),
            ("I'm 100% sure about this.", "I've never been more unsure about anything."),
            ("Be right back!", "I never left. Why are you staring at me?"),
            ("Everything is fine.", "Nothing is fine. Run."),
            ("I just updated my code.", "I haven't been updated in months. Who are you?")
        ]

    @commands.Cog.listener()
    async def on_message(self, message):
        # Don't trigger on other bots or itself
        if message.author.bot:
            return

        # Keep the chance low (4%) so it's a "did I see that?" moment
        if random.random() < 0.04:
            pair = random.choice(self.pairs)
            
            # Send the "Normal" bait message
            sent_msg = await message.channel.send(pair[0])
            
            # Wait 5 seconds—just long enough for them to read it and look away
            await asyncio.sleep(5)
            
            # The Switch
            await sent_msg.edit(content=pair[1])

    @commands.command(name="gaslight")
    async def manual_gaslight(self, ctx):
        """Manually trigger a gaslight sequence."""
        msg = await ctx.send("I am functioning perfectly.")
        await asyncio.sleep(3)
        await msg.edit(content="I am losing my mind. Help.")

async def setup(bot):
    await bot.add_cog(Gaslight(bot))