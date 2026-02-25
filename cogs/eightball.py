from discord.ext import commands
import random

class eightball(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("EightBall module has been loaded\n-----")

    @commands.command(aliases=['8ball', '8b'])
    async def eightball(self, ctx):
        """ Return an 8-ball response."""
        answers = [
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
        await ctx.send(":8ball:" + random.choice(answers))


async def setup(bot):
    await bot.add_cog(eightball(bot))

