import discord
from discord.ext import commands
import random
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

TRIGGER_CHANCE = 0.15  # 15% when in the time window

RESPONSES = [
    "why are you awake",
    "go to bed",
    "bro it's {time}. sleep.",
    "nothing good happens after 2am. go to bed.",
    "the fact that you're typing right now at {time} is concerning",
    "your body is begging you to sleep and you're out here posting",
    "imagine being awake right now. couldn't be me. wait.",
    "Sir/Ma'am this is a {time} message. Put the phone down.",
    "do you know what time it is? it's {time}. go to sleep.",
    "the sleep paralysis demon is waiting for you to close your eyes. might as well get it over with.",
    "you're awake at {time} and for WHAT",
    "your future self is going to hate you tomorrow morning",
    "the melatonin gummies are RIGHT THERE",
    "this is a wellness check. it's {time}. go to bed.",
    "every hour you stay up past 2am removes a year from your life. I made that up but it felt true.",
    "the pillow misses you. go.",
    "nobody has ever had a good idea at {time}",
    "you're going to regret this at 7am",
    "the bags under your eyes are getting their own zip code",
    "your circadian rhythm just filed for divorce",
    "you know what's cool? sleeping. you know what's not cool? being awake at {time}.",
    "i'm a bot and even I think you should go to bed",
    "touch pillow",
    "the bed is right there. it's free. it's comfortable. go.",
    "at this point you're not staying up late, you're getting up early. go to bed.",
]


class SleepPolice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Sleep Police module has been loaded")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if not message.content or message.content.startswith(("!", "/")):
            return

        # Check if it's between 2am-5am UTC
        now = datetime.now(timezone.utc)
        if now.hour < 2 or now.hour >= 5:
            return

        if random.random() > TRIGGER_CHANCE:
            return

        time_str = now.strftime("%I:%M %p")
        response = random.choice(RESPONSES).format(time=time_str)
        await message.reply(response, mention_author=False)


async def setup(bot):
    await bot.add_cog(SleepPolice(bot))
