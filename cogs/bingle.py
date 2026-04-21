import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
import logging

logger = logging.getLogger(__name__)

# The many ways one can get bingled
BINGLE_MESSAGES = [
    "{target} got bingled. Nobody is surprised.",
    "Get bingled, {target}. You earned this one.",
    "{target} just got bingled and honestly it was long overdue.",
    "Rough day to be {target}. Bingled.",
    "{target} walked right into that bingle. Couldn't have happened to a more deserving person.",
    "And just like that, {target} got bingled. Hate to see it. Actually no I don't.",
    "{target} got bingled. The group chat is going to hear about this one.",
    "Everybody point and laugh. {target} got bingled.",
    "{target} got bingled. Add it to the list of things that didn't go their way.",
    "Oh no. Oh no no no. {target} just got bingled.",
    "{target} got absolutely, unequivocally, undeniably bingled.",
    "That's a bingle, {target}. Take the L and move on.",
    "Imagine getting bingled in front of everyone. Couldn't be— oh wait, it's {target}.",
    "{target} got bingled. I'd say it gets better but I'd be lying.",
    "Congrats {target}, you just got bingled. This will be on your permanent record.",
    "{target} got bingled so bad even the lurkers are laughing.",
    "Not even close. {target} got bingled.",
    "{target} got bingled. Someone screenshot this before they delete their account.",
    "The bingle has spoken. {target} is done.",
    "That wasn't even a fair fight. {target} got bingled from the jump.",
    "{target} showed up just to get bingled. Respect the commitment I guess.",
    "Another day, another bingle for {target}. Tragic.",
    "Get bingled, {target}. Don't worry, it only stings for the rest of your life.",
    "{target} just caught a stray bingle. Wrong place, wrong time, wrong person.",
    "{target} got bingled and there's nothing anyone can do about it now.",
    "Hate to be the bearer of bad news but {target} just got bingled beyond repair.",
    "{target} really thought they were safe. Bingled.",
    "Someone check on {target}. Actually don't. They got bingled. Let them sit with it.",
    "{target} got bingled into irrelevance.",
    "You know what they say— get bingled or get bingled. Either way, {target} got bingled.",
]

# Extra flavor that can appear after the main message
BINGLE_FOLLOWUPS = [
    "Couldn't have happened to a nicer person.",
    "And they were never the same after that.",
    "Some say they're still bingled to this day.",
    "That one's gonna follow them around for a while.",
    "No coming back from that.",
    "They should probably just log off.",
    "Somebody call the bingle police. Actually, don't. They deserved it.",
    "Pain.",
    "And not a single person was shocked.",
    "The worst part? They'll be back for more.",
]

COMBO_CHANCE = 0.15  # 15% chance for a double bingle

COMBO_INTROS = [
    "Oh, we're not done—",
    "Hold on, there's more—",
    "Wait wait wait—",
    "Actually, one more—",
    "They thought it was over—",
]


class Bingle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Bingle module has been loaded")

    async def _send_bingle(self, target_mention: str, send_func, followup_func):
        """Core bingle logic."""
        msg = random.choice(BINGLE_MESSAGES).format(target=target_mention)
        await send_func(msg)

        # Maybe add a followup
        if random.random() < 0.3:
            await asyncio.sleep(1)
            await followup_func(f"*{random.choice(BINGLE_FOLLOWUPS)}*")

        # Combo bingle
        if random.random() < COMBO_CHANCE:
            await asyncio.sleep(1.2)
            await followup_func(random.choice(COMBO_INTROS))
            await asyncio.sleep(0.8)
            extra = random.choice(BINGLE_MESSAGES).format(target=target_mention)
            await followup_func(extra)

    @commands.command(aliases=["Bingle", "BINGLE"])
    async def bingle(self, ctx, member: discord.Member = None):
        """Get bingled. Or bingle someone else."""
        if member is None:
            member = ctx.author
        await self._send_bingle(member.mention, ctx.send, ctx.send)

    @app_commands.command(name="bingle", description="Get bingled, or bingle someone")
    @app_commands.describe(member="The unlucky soul to bingle (leave empty to bingle yourself)")
    async def bingle_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        if member is None:
            member = interaction.user
        await self._send_bingle(
            member.mention,
            interaction.response.send_message,
            interaction.channel.send,
        )


async def setup(bot):
    await bot.add_cog(Bingle(bot))
