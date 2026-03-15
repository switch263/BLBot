import discord
from discord.ext import commands
from discord import app_commands
import random
import os
import logging

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data_files")


def _load_lines(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.error(f"Data file not found: {filepath}")
        return []


# Templates for insult formatting - {noun} gets replaced with the insult word
TEMPLATES = [
    "you're a {noun}",
    "you absolute {adj} {noun}",
    "you {adj} waste of a {noun}",
    "you industrial-strength {noun}",
    "you're the human equivalent of a {noun}",
    "you unbelievable {adj} {noun}",
    "you are, without a doubt, a {adj} {noun}",
    "you spectacularly {adj} {noun}",
    "you're what happens when a {noun} gains sentience",
    "you {adj} soggy {noun}",
    "you're a {noun} wrapped in a {noun}",
    "you {adj} {noun} of a human being",
    "if you were any more of a {noun}, you'd need a license",
    "you make other {noun}s look good",
    "you're like a {noun} but with less value",
]

ADJECTIVES = [
    "useless", "expired", "discount", "off-brand", "lukewarm", "stale",
    "soggy", "overcooked", "undercooked", "room-temperature", "half-baked",
    "watered-down", "defrosted", "microwaved", "bargain-bin", "bootleg",
    "refurbished", "moldy", "crusty", "dusty", "rusty", "musty",
    "rancid", "putrid", "festering", "decomposing", "fermenting",
    "unseasoned", "flavorless", "store-brand", "clearance-rack",
]


SAVAGE_CHANCE = 0.25  # 25% chance for a full savage insult instead of template


class Insult(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.insults = _load_lines(os.path.join(DATA_DIR, "insults.txt"))
        self.savages = _load_lines(os.path.join(DATA_DIR, "savage_insults.txt"))

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Insult module has been loaded")

    def _generate_insult(self) -> str | None:
        if not self.insults:
            return None
        # 25% chance for a full savage insult
        if self.savages and random.random() < SAVAGE_CHANCE:
            return random.choice(self.savages)
        noun = random.choice(self.insults)
        template = random.choice(TEMPLATES)
        adj = random.choice(ADJECTIVES)
        # Get a second noun for the double-noun template
        noun2 = random.choice(self.insults)
        result = template.replace("{noun}", noun, 1).replace("{noun}", noun2).replace("{adj}", adj)
        return result

    @commands.command(aliases=['Insult'])
    async def insult(self, ctx, member: discord.Member = None):
        """ Insult the target if one is given, otherwise insult the user that asked. """
        insult = self._generate_insult()
        if insult is None:
            await ctx.send("Error: Insult list not found or empty.")
            return
        if member:
            await ctx.send(f"Hey, {member.mention}! {ctx.message.author.mention} said {insult}!")
        else:
            await ctx.send(f"Hey, {ctx.message.author.mention}! {insult}!")

    @app_commands.command(name="insult", description="Insult someone (or yourself)")
    @app_commands.describe(member="The person to insult (leave empty to insult yourself)")
    async def insult_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        insult = self._generate_insult()
        if insult is None:
            await interaction.response.send_message("Error: Insult list not found or empty.")
            return
        if member:
            await interaction.response.send_message(f"Hey, {member.mention}! {interaction.user.mention} said {insult}!")
        else:
            await interaction.response.send_message(f"Hey, {interaction.user.mention}! {insult}!")


async def setup(bot):
    await bot.add_cog(Insult(bot))
