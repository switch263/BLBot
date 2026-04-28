import discord
from discord.ext import commands
import random
import re
import logging

logger = logging.getLogger(__name__)

DAD_JOKES = [
    "Why don't skeletons fight each other? They don't have the guts.",
    "I used to hate facial hair, but then it grew on me.",
    "What do you call a fake noodle? An impasta.",
    "Why did the scarecrow win an award? He was outstanding in his field.",
    "I'm reading a book about anti-gravity. It's impossible to put down.",
    "What do you call cheese that isn't yours? Nacho cheese.",
    "Why couldn't the bicycle stand up by itself? It was two tired.",
    "I would tell you a chemistry joke, but I know I wouldn't get a reaction.",
    "Did you hear about the claustrophobic astronaut? He just needed a little space.",
    "What do you call a bear with no teeth? A gummy bear.",
    "I used to play piano by ear, but now I use my hands.",
    "Why do cows have hooves instead of feet? Because they lactose.",
    "What did the ocean say to the beach? Nothing, it just waved.",
    "I'm afraid for the calendar. Its days are numbered.",
    "What do you call a dog that does magic tricks? A Labracadabrador.",
    "Why don't eggs tell jokes? They'd crack each other up.",
    "I got fired from the calendar factory. All I did was take a day off.",
    "What do you call a sleeping dinosaur? A dino-snore.",
    "Why can't you give Elsa a balloon? Because she'll let it go.",
    "I told my wife she was drawing her eyebrows too high. She looked surprised.",
]

TRIGGER_CHANCE = 0.05  # 5%
DAD_JOKE_FOLLOWUP_CHANCE = 0.30  # 30% chance of bonus dad joke after the dad response

# Pattern to match "I'm [something]", "im [something]", "i am [something]"
IM_PATTERN = re.compile(
    r"(?:^|\s)(?:i'?m|i\s+am)\s+(.{2,50})(?:[.!?,;]|$)",
    re.IGNORECASE
)

# Things to ignore (too short, too common, or would be weird)
IGNORE_WORDS = {
    "good", "fine", "ok", "okay", "here", "back", "coming", "going",
    "not", "done", "in", "on", "at", "the", "a", "an", "so", "just",
    "gonna", "going to", "about to", "trying to", "looking for",
}


class DadBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Dad Bot module has been loaded")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if random.random() > TRIGGER_CHANCE:
            return

        match = IM_PATTERN.search(message.content)
        if not match:
            return

        thing = match.group(1).strip().rstrip(".!?,;")

        # Skip boring/common matches
        if thing.lower() in IGNORE_WORDS:
            return
        if len(thing) < 2:
            return

        await message.channel.send(f"Hi {thing}, I'm Dad!")

        if random.random() < DAD_JOKE_FOLLOWUP_CHANCE:
            await message.channel.send(random.choice(DAD_JOKES))


async def setup(bot):
    await bot.add_cog(DadBot(bot))
