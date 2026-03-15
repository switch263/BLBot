import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

logger = logging.getLogger(__name__)

PICKUP_LINES = [
    # Cheesy
    "Are you a magician? Because whenever I look at you, everyone else disappears.",
    "Do you have a map? Because I just got lost in your eyes.",
    "Is your name Google? Because you have everything I've been searching for.",
    "Are you a parking ticket? Because you've got 'fine' written all over you.",
    "Do you believe in love at first sight, or should I walk by again?",
    "If you were a vegetable, you'd be a cute-cumber.",
    "Are you a campfire? Because you're hot and I want s'more.",
    "Is your dad a boxer? Because you're a knockout.",
    "Do you have a Band-Aid? Because I just scraped my knee falling for you.",
    "Are you Wi-Fi? Because I'm feeling a connection.",
    # Nerdy
    "Are you a 404 error? Because I've been searching for you my whole life.",
    "You must be the square root of -1, because you can't be real.",
    "Are you a keyboard? Because you're just my type.",
    "If you were a CSS property, you'd be `display: stunning`.",
    "Are you a Python exception? Because you've caught my attention.",
    "You must be made of copper and tellurium, because you're Cu-Te.",
    "Are you an API? Because I'd love to get your endpoint.",
    "You had me at 'Hello World'.",
    "Are you a recursive function? Because you keep running through my mind.",
    "I wish I were your derivative so I could lie tangent to your curves.",
    # Absurd
    "Are you a toaster? Because I want to take a bath with you... wait, that came out wrong.",
    "If you were a chicken nugget, you'd be a McNificent.",
    "Are you a bank loan? Because you've got my interest.",
    "Do you like raisins? How about a date?",
    "Are you a time traveler? Because I can see you in my future.",
    "If you were a Transformer, you'd be Optimus Fine.",
    "Are you a beaver? Because daaaaam.",
    "I'm not a photographer, but I can picture us together.",
    "Are you an alien? Because you just abducted my heart.",
    "If you were a burger at McDonald's, you'd be the McGorgeous.",
    "Are you a volcano? Because I lava you.",
    "Do you have a sunburn, or are you always this hot?",
    "Are you a microwave? Because you make my heart go MMMMMMMM.",
    "If beauty were time, you'd be an eternity.",
    "Are you a dictionary? Because you add meaning to my life.",
    "Are you a cat? Because I'm feline a connection between us.",
    "Is your name Chapstick? Because you're da balm.",
    "You must be a broom, because you just swept me off my feet.",
    "Are you a 90-degree angle? Because you're looking right.",
    "If you were a fruit, you'd be a fineapple.",
    "Are you an elevator? Because I want to go down on... wait, let me start over.",
    "Are you a haunted house? Because I'm going to scream when I'm in you... no wait—",
    "Do you work at Subway? Because you just gave me a footlong... impression.",
]


class Pickup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Pickup module has been loaded")

    def _generate_pickup(self, author: discord.Member, target: discord.Member) -> str:
        line = random.choice(PICKUP_LINES)
        return f"{author.mention} looks at {target.mention} and says: {line}"

    @commands.command()
    async def pickup(self, ctx, member: discord.Member):
        """Send a terrible pickup line at someone. Usage: !pickup @user"""
        await ctx.send(self._generate_pickup(ctx.author, member))

    @app_commands.command(name="pickup", description="Send a terrible pickup line at someone")
    @app_commands.describe(member="The target of your affection")
    async def pickup_slash(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.send_message(
            self._generate_pickup(interaction.user, member)
        )


async def setup(bot):
    await bot.add_cog(Pickup(bot))
