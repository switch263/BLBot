import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random

class Microwave(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reactions = [
            "💥 *POOF!* Everything is on fire now.",
            "🔋 It's now slightly warm in the middle but frozen on the edges.",
            "✨ It’s glowing a weird shade of neon green. Don't touch it.",
            "🥗 It turned into a salad? How did that happen?",
            "🫠 It has completely melted through the bottom of the microwave.",
            "🔊 *CRACKLE POP* - Is that supposed to make that sound?",
            "🏆 Achievement Unlocked: Molecular Reconstruction.",
            "👻 The item has vanished. I think we opened a portal.",
            "🫠 It's just a puddle of sentient grey goo now.",
            "💎 It compressed into a single, very small diamond. Profit?",
            "🦖 It devolved into a prehistoric version of itself.",
            "🍕 Why does it smell like a Domino's in here now?",
            "🚫 The microwave refused. It has unionized and is on strike.",
            "🌈 It's now vibrating at a frequency that makes everyone's teeth hurt.",
            "🧊 Somehow, it's colder than when it went in. Absolute zero reached.",
            "🦾 It has gained sentience and is currently downloading your search history.",
            "🥨 It tied itself into a complex topological knot.",
            "🎺 It’s just making a loud tromboning noise now. Non-stop.",
            "🍞 It turned into a single slice of slightly burnt sourdough toast.",
            "🧿 You have successfully microwaved a curse into existence.",
            "📦 It's now inside-out. I didn't even know matter could do that."
        ]

    async def run_microwave(self, ctx_or_interaction, item: str):
        response_start = f"Is it a good idea to microwave **{item}**? Let's find out!"
        
        if isinstance(ctx_or_interaction, commands.Context):
            await ctx_or_interaction.send(response_start)
            channel = ctx_or_interaction.channel
        else:
            await ctx_or_interaction.response.send_message(response_start)
            channel = ctx_or_interaction.channel

        # --- Multi-Line Hum Logic ---
        num_lines = random.randint(1, 3)
        
        for i in range(num_lines):
            await asyncio.sleep(random.uniform(0.8, 1.5)) # Short typing-like delay
            
            # 2% chance for the microwave to scream instead
            if random.random() < 0.02:
                hum = "AAAAAAAAAAAAAAAAA"
            else:
                hum = "M" * random.randint(15, 40)
            
            await channel.send(hum)

        # Final Cooking Delay
        await asyncio.sleep(1.5)

        # 10% chance of success, otherwise chaos
        if random.random() < 0.10:
            result = "✅ It's actually... perfectly cooked. A miracle."
        else:
            result = random.choice(self.reactions)
            
        await channel.send(f"... {result}")
        
        # The Finish
        await asyncio.sleep(0.5)
        await channel.send("🔔 **DING!**")

    @commands.command(name="microwave")
    async def microwave_prefix(self, ctx, *, item: str):
        """Microwave something using !microwave [item]"""
        await self.run_microwave(ctx, item)

    @app_commands.command(name="microwave", description="Is it a good idea to microwave this?")
    async def microwave_slash(self, interaction: discord.Interaction, item: str):
        """Microwave something using /microwave"""
        await self.run_microwave(interaction, item)

async def setup(bot):
    await bot.add_cog(Microwave(bot))