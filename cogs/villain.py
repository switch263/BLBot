import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

logger = logging.getLogger(__name__)

OPENINGS = [
    "Ah, {target}... We meet at last.",
    "Well, well, well... if it isn't {target}.",
    "So, {target}, you dare to show your face here?",
    "I've been expecting you, {target}.",
    "{target}... You fool. You absolute buffoon.",
    "At last, {target} arrives. How... predictable.",
    "Oh {target}, sweet naive {target}... you have no idea what's coming.",
    "You think you can just waltz in here, {target}?",
    "The legendary {target}... I expected someone taller.",
    "Silence! {target} has entered, and so begins the end.",
    "Ah yes, {target}. My arch-nemesis. My greatest annoyance.",
    "How quaint. {target} thinks they stand a chance.",
    "Every villain needs a nemesis, and mine is... {target}. Disappointing.",
    "Look who crawled out of their DMs... {target}.",
    "My sensors detected a disturbance in the server. It was you, {target}.",
    "I have conquered entire servers, {target}. You are merely a speed bump.",
]

MIDDLES = [
    "You think your pathetic memes can stop my plan for world domination?",
    "I have amassed an army of bots, and you dare oppose me with... emojis?",
    "My power level is over 9000 and yours is... well, let's not embarrass you.",
    "While you were sleeping, I was studying the blade... and also shitposting.",
    "I have infiltrated every group chat. Every. Single. One.",
    "You cannot comprehend the dark forces I have unleashed upon this server.",
    "My plan has been in motion since before you even created your account.",
    "I have mastered the forbidden arts of copypasta and weaponized cringe.",
    "Do you know how many alt accounts I have? Neither do I. I lost count.",
    "Your precious moderators cannot save you from what I have planned.",
    "I didn't choose the villain life. The villain life chose me. On a Tuesday.",
    "Every reaction you've ever posted has only made me stronger.",
    "You think this is a game? THIS IS A LIFESTYLE.",
    "My evil lair has RGB lighting AND a mini fridge. Can you compete with that?",
    "I have read the terms of service... AND I REJECT THEM.",
    "While you touched grass, I was forging alliances in the shadow realm of Discord.",
]

CLOSINGS = [
    "Foolish mortal... When I am done, you will beg for mercy in my DMs.",
    "Enjoy your last moments of peace. My master plan activates at midnight.",
    "This isn't over, {target}. It has only just begun. *evil laughter*",
    "Remember this day, {target}. The day you almost caught me.",
    "I will return, and next time... I'll bring snacks. EVIL snacks.",
    "Mark my words: your server will tremble before my wrath. Eventually. Maybe after dinner.",
    "You've won this round, {target}, but I have... unlimited data.",
    "The prophecy foretold this encounter. It also said I'd lose. BUT PROPHECIES CAN BE WRONG.",
    "Flee while you can, {target}. My next move will be absolutely devastating. Probably.",
    "When the dust settles, only one of us will remain online. And it will be ME.",
    "*dramatically swirls cape* We shall meet again, {target}. In the next thread.",
    "I would destroy you now, but my pizza just arrived. Consider yourself LUCKY.",
    "You may have allies, but I have... a really good Wi-Fi connection.",
    "This server isn't big enough for the both of us. Someone should boost it.",
    "Tremble before me, {target}! Or don't. I'm a villain, not a cop.",
    "My revenge will be swift, merciless, and probably passive-aggressive.",
]


class Villain(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Villain module has been loaded")

    def _build_monologue(self, author: discord.Member, target: discord.Member) -> discord.Embed:
        name = target.display_name
        opening = random.choice(OPENINGS).format(target=name)
        middle = random.choice(MIDDLES).format(target=name)
        closing = random.choice(CLOSINGS).format(target=name)

        monologue = f"*{opening}*\n\n{middle}\n\n**{closing}**"

        embed = discord.Embed(
            title=f"{author.display_name}'s Villain Monologue",
            description=monologue,
            color=discord.Color.dark_purple(),
        )
        embed.set_thumbnail(url=author.display_avatar.url)
        embed.set_footer(text=f"Directed at {target.display_name}")
        return embed

    @commands.command()
    async def villain(self, ctx, member: discord.Member):
        """Deliver a dramatic villain monologue at someone. Usage: !villain @user"""
        await ctx.send(embed=self._build_monologue(ctx.author, member))

    @app_commands.command(name="villain", description="Deliver a dramatic villain monologue at someone")
    @app_commands.describe(member="Your arch-nemesis")
    async def villain_slash(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.send_message(
            embed=self._build_monologue(interaction.user, member)
        )


async def setup(bot):
    await bot.add_cog(Villain(bot))
