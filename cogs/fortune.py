import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

logger = logging.getLogger(__name__)

FORTUNES = [
    "A beautiful, smart, and loving person will be coming into your life... oh wait, that's your reflection.",
    "You will find great success. In what, we're not sure. Probably not this.",
    "A surprise awaits you. It's not a good one.",
    "Today is a good day to make someone else do your work.",
    "Your future is bright. Your present? Questionable.",
    "You will step on a Lego within 48 hours.",
    "An unexpected windfall is coming your way. Probably bird poop.",
    "The stars say you're amazing. The stars are terrible judges of character.",
    "Great things come to those who wait. You've been waiting too long though.",
    "Your soulmate is closer than you think. Check behind the couch.",
    "You will make a life-changing decision today. You'll regret it tomorrow.",
    "A great adventure awaits! It's called Monday.",
    "Someone is thinking about you right now. They're not happy about it.",
    "You will become famous. On a wanted poster.",
    "Today you will find money on the ground. It will be a penny. Heads down.",
    "Love is around the corner. So is a parking ticket.",
    "Your gaming skills will improve drastically. Just kidding, you're hopeless.",
    "A wise person once said nothing. Be like that person.",
    "You are destined for greatness. But today ain't the day.",
    "Something you lost will turn up. It won't be your dignity.",
    "In the next 24 hours, you will breathe. Probably.",
    "Trust your instincts. Unless your instincts got you here.",
    "The journey of a thousand miles begins with a single step. Yours begins with tripping.",
    "You will receive a compliment today. It will be sarcastic.",
    "Your lucky day is tomorrow. Today? Not so much.",
    "A closed mouth gathers no foot. Open yours less.",
    "You will meet someone who changes your life. It's the IRS.",
    "Believe in yourself. Nobody else is going to.",
    "The answer you seek is within you. So is last night's Taco Bell.",
    "You're about to receive sage advice. This isn't it.",
]

LUCKY_COLORS = [
    "Beige (the most thrilling of colors)",
    "That weird green your walls turn at 3am",
    "Whatever color that stain on your shirt is",
    "Vantablack (like your soul)",
    "RGB (all of them, simultaneously)",
    "The blue screen of death",
    "Invisible",
    "Printer ink cyan (the most expensive color)",
    "Faded receipt paper white",
    "Gas station bathroom tile gray",
    "Clearance rack orange",
    "Participation ribbon blue",
    "Expired milk white",
    "Check engine light amber",
]

CHINESE_WORDS = [
    ("ji", "chicken"),
    ("mao", "cat"),
    ("gou", "dog"),
    ("shui", "water"),
    ("huo", "fire"),
    ("yue", "moon"),
    ("xing", "star"),
    ("shan", "mountain"),
    ("he", "river"),
    ("hua", "flower"),
    ("shu", "book"),
    ("ren", "person"),
    ("da", "big"),
    ("xiao", "small"),
    ("hao", "good"),
    ("chi", "eat"),
    ("he", "drink"),
    ("peng you", "friend"),
    ("kuai le", "happy"),
    ("xie xie", "thank you"),
]


class FortuneCookie(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Fortune Cookie module has been loaded")

    def _crack_cookie(self) -> discord.Embed:
        """Generate a fortune cookie embed."""
        fortune = random.choice(FORTUNES)
        lucky_numbers = sorted(random.sample(range(1, 100), 6))
        lucky_color = random.choice(LUCKY_COLORS)
        word = random.choice(CHINESE_WORDS)

        embed = discord.Embed(
            title="Fortune Cookie",
            description=f"*{fortune}*",
            color=discord.Color.from_rgb(255, 204, 0)
        )

        embed.add_field(
            name="Lucky Numbers",
            value=" - ".join(str(n) for n in lucky_numbers),
            inline=True
        )

        embed.add_field(
            name="Lucky Color",
            value=lucky_color,
            inline=True
        )

        embed.add_field(
            name="Learn Chinese",
            value=f"**{word[0]}** - {word[1]}",
            inline=True
        )

        embed.set_footer(text="Disclaimer: This fortune is for entertainment purposes only. We are not responsible for any life decisions made based on this cookie.")

        return embed

    @commands.command(aliases=['fortunecookie', 'cookie'])
    async def fortune(self, ctx):
        """Crack open a fortune cookie."""
        await ctx.send(embed=self._crack_cookie())

    @app_commands.command(name="fortune", description="Crack open a fortune cookie")
    async def fortune_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self._crack_cookie())


async def setup(bot):
    await bot.add_cog(FortuneCookie(bot))
