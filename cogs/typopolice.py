import discord
from discord.ext import commands
import random
import logging

logger = logging.getLogger(__name__)

TRIGGER_CHANCE = 0.02  # 2%

# "Corrections" that are completely wrong
WRONG_CORRECTIONS = [
    ("the", "thé (it's French, look it up)"),
    ("what", "hwat"),
    ("you", "thou"),
    ("your", "you're* ... wait no... yore*... actually I don't know anymore"),
    ("their", "they're* ... or there* ... honestly who even knows"),
    ("its", "it's* (I think) (don't quote me on this)"),
    ("should", "shöuld"),
    ("would", "wo'uld (the apostrophe is silent)"),
    ("could", "cou'ld"),
    ("because", "becauseth"),
    ("like", "lyke (old English, very classy)"),
    ("just", "joust"),
    ("really", "reallé"),
    ("actually", "akshually"),
    ("literally", "litcherally"),
    ("probably", "probababably"),
    ("definitely", "definately... wait... defanitely... definently... you know what nevermind"),
    ("going", "göing"),
    ("people", "peeple"),
    ("something", "somethign"),
    ("nothing", "nothingk"),
    ("everything", "everythang"),
    ("think", "thonk"),
    ("know", "knöw (the ö is silent)"),
    ("right", "wright"),
    ("good", "goüd"),
    ("great", "grate*... no wait that's a cheese thing"),
    ("maybe", "mayhaps"),
    ("though", "tho'ugh"),
    ("enough", "enought"),
]

CORRECTION_FORMATS = [
    '*{correction}\n(sorry, had to)',
    'Did you mean *"{correction}"*?',
    'I think the correct spelling is *{correction}*.',
    'Actually it\'s *{correction}*. Common mistake.',
    '*{correction}\nSource: I made it up',
    'Um actually, it\'s spelled *{correction}*. 🤓',
    '*{correction}\n(I\'m probably wrong but I\'m committed now)',
    'The dictionary says it\'s *{correction}* but the dictionary is also wrong sometimes.',
    'Fun fact: it\'s actually *{correction}*. Not a fun fact. Not even a fact.',
    '*{correction}\n- sent from my high horse',
]


class TypoPolice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Typo Police module has been loaded")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if not message.content or message.content.startswith(("!", "/")):
            return

        if random.random() > TRIGGER_CHANCE:
            return

        words = message.content.lower().split()
        # Find any correctable words in the message
        matches = []
        for original, correction in WRONG_CORRECTIONS:
            if original in words:
                matches.append((original, correction))

        if not matches:
            return

        original, correction = random.choice(matches)
        fmt = random.choice(CORRECTION_FORMATS)
        await message.reply(fmt.format(correction=correction), mention_author=False)


async def setup(bot):
    await bot.add_cog(TypoPolice(bot))
