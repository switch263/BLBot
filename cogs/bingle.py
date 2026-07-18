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
    "{target} got bingled at terminal velocity.",
    "Scientists are still studying how hard {target} just got bingled.",
    "{target} got bingled in 4K, 120fps, no skips.",
    "Breaking news: {target} got bingled. More at 11. And at midnight. And forever.",
    "{target} has been bingled. The council has spoken.",
    "A moment of silence for {target}. Bingled.",
    "{target} got bingled so hard their wifi dropped.",
    "The prophecy was true. {target} got bingled.",
    "{target} just got bingled with the force of a thousand suns.",
    "Legends say {target} is still recovering from that bingle. Legends are wrong. They never recovered.",
    "{target} got bingled. HR has been notified. HR laughed.",
    "That bingle had {target}'s name on it. Certified mail. Signature required. Delivered.",
    "{target} tried to dodge. The bingle doesn't miss.",
    "{target} got bingled on their day off. Brutal.",
    "The bingle came from inside the house, {target}.",
    "{target} got bingled and the replay is somehow worse.",
    "Witnesses describe the bingle that hit {target} as 'unnecessary' and 'hilarious'.",
    "{target} got bingled. Their lawyer has advised them not to comment.",
    "{target} just took a bingle to the face. Open casket anyway, they deserve it.",
    "Every server has a {target}. And every {target} gets bingled.",
    "{target} got bingled. Vegas had it at -5000. Everyone saw this coming.",
    "The bingle waited years for this exact moment, {target}. Worth it.",
    "{target} got bingled mid-sentence. Didn't even get to finish their",
    "{target} has been served: one (1) bingle, no refunds.",
    "Bingle delivered to {target}. Photo confirmation attached. It's not flattering.",
    "{target} got bingled and their last words were 'wait, what does bingle mea—'",
    "{target} caught a bingle like it was a cold. Highly contagious. Deeply embarrassing.",
    "Somewhere a bell tolls. It tolls for {target}. Bingled.",
    "{target} got bingled retroactively. Every photo of them is now worse.",
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

CRIT_CHANCE = 1 / 25  # critical bingle: 6 in a row, then a bystander catches one
CRIT_BINGLES = 6

CRIT_INTROS = [
    "🚨 **CRITICAL BINGLE** 🚨 {target} rolled the one number they should never roll.",
    "🚨 **CRITICAL BINGLE** 🚨 The bingle gods have chosen {target}. May they have mercy. (They won't.)",
    "🚨 **CRITICAL BINGLE** 🚨 Everyone stand back. {target} is about to have a very bad time.",
]

CRIT_BYSTANDER_INTROS = [
    "And you know what? {bystander} catches one too. For the hell of it.",
    "The bingle isn't done. It ricochets and hits {bystander}. No reason. It just felt right.",
    "Collateral damage report: {bystander} was standing too close.",
    "{bystander} didn't do anything. Bingled anyway. That's how crits work.",
]


class Bingle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Bingle module has been loaded")

    def _pick_bystander(self, channel, exclude_ids):
        """Random non-bot member of the channel who isn't already involved."""
        members = getattr(channel, "members", None)
        if not members:
            return None
        candidates = [m for m in members if not m.bot and m.id not in exclude_ids]
        return random.choice(candidates) if candidates else None

    async def _critical_bingle(self, target, channel, send_func, followup_func):
        """1-in-25 jackpot: 6 bingles back to back, then a bystander eats one."""
        await send_func(random.choice(CRIT_INTROS).format(target=target.mention))
        volley = random.sample(BINGLE_MESSAGES, CRIT_BINGLES)
        for msg in volley:
            await asyncio.sleep(0.8)
            await followup_func(msg.format(target=target.mention))

        bystander = self._pick_bystander(channel, {target.id})
        if bystander is None:
            return
        await asyncio.sleep(1.5)
        await followup_func(
            random.choice(CRIT_BYSTANDER_INTROS).format(bystander=bystander.mention)
        )
        await asyncio.sleep(0.8)
        await followup_func(
            random.choice(BINGLE_MESSAGES).format(target=bystander.mention)
        )

    async def _send_bingle(self, target, channel, send_func, followup_func):
        """Core bingle logic."""
        if random.random() < CRIT_CHANCE:
            await self._critical_bingle(target, channel, send_func, followup_func)
            return

        msg = random.choice(BINGLE_MESSAGES).format(target=target.mention)
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
            extra = random.choice(BINGLE_MESSAGES).format(target=target.mention)
            await followup_func(extra)

    @commands.command(aliases=["Bingle", "BINGLE"])
    async def bingle(self, ctx, member: discord.Member = None):
        """Get bingled. Or bingle someone else."""
        if member is None:
            member = ctx.author
        await self._send_bingle(member, ctx.channel, ctx.send, ctx.send)

    @app_commands.command(name="bingle", description="Get bingled, or bingle someone")
    @app_commands.describe(member="The unlucky soul to bingle (leave empty to bingle yourself)")
    async def bingle_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        if member is None:
            member = interaction.user
        await self._send_bingle(
            member,
            interaction.channel,
            interaction.response.send_message,
            interaction.channel.send,
        )


async def setup(bot):
    await bot.add_cog(Bingle(bot))
