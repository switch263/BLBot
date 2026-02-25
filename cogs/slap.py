import discord
from discord.ext import commands
import random

class Slaps(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.random_generator = random.SystemRandom()  

        self.slap_sounds = [
            "WHAP", "THWACK", "SMACK", "POW", "BIFF", "WHAM", "SLAP", 
            "KERPOW", "SPLAT", "BONK", "BOP", "BLAM", "ZOOM", "SWISH", 
            "CRUNCH", "OOOF", "SMUSH", "KABOOM", "ZAP", "FLAP" # ...add more!
        ]

        self.slap_adjectives = [
            "thunderous", "vicious", "stinging", "humiliating", "unexpected", "swift", "comical",
            "playful", "cartoony", "wobbly", "bouncy", "surreal", "jelly-like", "fishy", 
            "noodle-based", "ridiculous", "absurd", "cosmic"  # ...add more!
        ]

        self.slap_targets = [
            "face", "cheek", "ego", "behind", "pride", "sense of humor", "hopes and dreams",
            "funny bone", "patience", "noodle", "sense of reality", "expectations"  #...add more!
        ]

    @commands.command()
    async def slap(self, ctx, member: discord.Member = None):
        if member is None:
            # Use self.random_generator for choices 
            if self.random_generator.random() < 0.8:  
                member = ctx.author
                target = self.random_generator.choice(self.slap_targets)
                await ctx.send(f"{ctx.author.mention} delivers a {self.random_generator.choice(self.slap_adjectives)} {self.random_generator.choice(self.slap_sounds)} to their own {target}!")
            else:  
                member = self.random_generator.choice(ctx.channel.members)
                await ctx.send(f"{ctx.author.mention} surprises {member.mention} with a {self.random_generator.choice(self.slap_adjectives)} {self.random_generator.choice(self.slap_sounds)}!")
        else:
            target = self.random_generator.choice(self.slap_targets)
            await ctx.send(f"{ctx.author.mention} delivers a {self.random_generator.choice(self.slap_adjectives)} {self.random_generator.choice(self.slap_sounds)} to {member.mention}'s {target}!")

async def setup(bot):
    await bot.add_cog(Slaps(bot))

