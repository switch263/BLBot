import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

logger = logging.getLogger(__name__)

ANSWERS = [
    "Ask Again Later",
    "Better Not Tell You Now",
    "Concentrate and Ask Again",
    "Don't Count on It",
    "It Is Certain",
    "Most Likely",
    "My Reply is No",
    "My Sources Say No",
    "No",
    "Outlook Good",
    "Outlook Not So Good",
    "Reply Hazy, Try Again",
    "Signs Point to Yes",
    "Yes",
    "Yes, Definitely",
    "You May Rely On It",
]


class EightBall(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("EightBall module has been loaded")

    @commands.command(aliases=['8ball', '8b'])
    async def eightball(self, ctx):
        """ Return an 8-ball response."""
        await ctx.send(":8ball:" + random.choice(ANSWERS))

    @app_commands.command(name="8ball", description="Ask the magic 8-ball a question")
    @app_commands.describe(question="Your question for the 8-ball")
    async def eightball_slash(self, interaction: discord.Interaction, question: str):
        await interaction.response.send_message(f"**Q:** {question}\n:8ball: {random.choice(ANSWERS)}")


async def setup(bot):
    await bot.add_cog(EightBall(bot))
