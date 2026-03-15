import discord
from discord.ext import commands
from discord import app_commands
import re
import logging

logger = logging.getLogger(__name__)

WORD_TO_EMOJI = {
    "fire": "\U0001f525",
    "love": "\u2764\ufe0f",
    "heart": "\u2764\ufe0f",
    "dog": "\U0001f415",
    "cat": "\U0001f408",
    "money": "\U0001f4b0",
    "cash": "\U0001f4b5",
    "rich": "\U0001f4b0",
    "sun": "\u2600\ufe0f",
    "moon": "\U0001f319",
    "star": "\u2b50",
    "water": "\U0001f4a7",
    "rain": "\U0001f327\ufe0f",
    "snow": "\u2744\ufe0f",
    "tree": "\U0001f333",
    "flower": "\U0001f33a",
    "rose": "\U0001f339",
    "food": "\U0001f354",
    "pizza": "\U0001f355",
    "beer": "\U0001f37a",
    "wine": "\U0001f377",
    "coffee": "\u2615",
    "tea": "\U0001f375",
    "cake": "\U0001f370",
    "ice": "\U0001f9ca",
    "car": "\U0001f697",
    "plane": "\u2708\ufe0f",
    "rocket": "\U0001f680",
    "house": "\U0001f3e0",
    "home": "\U0001f3e0",
    "phone": "\U0001f4f1",
    "computer": "\U0001f4bb",
    "music": "\U0001f3b5",
    "book": "\U0001f4d6",
    "time": "\u23f0",
    "clock": "\U0001f570\ufe0f",
    "sleep": "\U0001f634",
    "cry": "\U0001f622",
    "sad": "\U0001f622",
    "happy": "\U0001f604",
    "laugh": "\U0001f602",
    "lol": "\U0001f602",
    "angry": "\U0001f621",
    "mad": "\U0001f621",
    "cool": "\U0001f60e",
    "yes": "\u2705",
    "no": "\u274c",
    "ok": "\U0001f44c",
    "good": "\U0001f44d",
    "bad": "\U0001f44e",
    "king": "\U0001f451",
    "queen": "\U0001f451",
    "skull": "\U0001f480",
    "dead": "\U0001f480",
    "ghost": "\U0001f47b",
    "clown": "\U0001f921",
    "brain": "\U0001f9e0",
    "eyes": "\U0001f440",
    "hand": "\u270b",
    "wave": "\U0001f44b",
    "pray": "\U0001f64f",
    "muscle": "\U0001f4aa",
    "strong": "\U0001f4aa",
    "run": "\U0001f3c3",
    "fast": "\U0001f4a8",
    "slow": "\U0001f422",
    "big": "\U0001f4a5",
    "small": "\U0001f90f",
    "hot": "\U0001f525",
    "cold": "\U0001f976",
    "world": "\U0001f30d",
    "earth": "\U0001f30d",
    "bomb": "\U0001f4a3",
    "war": "\u2694\ufe0f",
    "peace": "\u262e\ufe0f",
    "game": "\U0001f3ae",
    "win": "\U0001f3c6",
    "lose": "\U0001f4a9",
    "poop": "\U0001f4a9",
    "trash": "\U0001f5d1\ufe0f",
    "think": "\U0001f914",
    "idea": "\U0001f4a1",
    "light": "\U0001f4a1",
    "dark": "\U0001f311",
    "night": "\U0001f303",
    "party": "\U0001f389",
    "celebrate": "\U0001f389",
    "gift": "\U0001f381",
    "bug": "\U0001f41b",
    "snake": "\U0001f40d",
    "fish": "\U0001f41f",
    "bird": "\U0001f426",
    "baby": "\U0001f476",
    "devil": "\U0001f608",
    "angel": "\U0001f607",
    "100": "\U0001f4af",
    "sweat": "\U0001f4a6",
    "pog": "\U0001f62e",
    "cap": "\U0001f9e2",
}

# Regional indicator letters: A=U+1F1E6 ... Z=U+1F1FF
REGIONAL_A = 0x1F1E6


def _letter_to_regional(ch: str) -> str:
    """Convert a single letter to a regional indicator emoji."""
    if ch.isalpha():
        return chr(REGIONAL_A + (ord(ch.lower()) - ord('a')))
    return ch


def _emojify(text: str) -> str:
    """Replace known words with emoji; convert remaining letters to regional indicators."""
    words = re.split(r'(\s+)', text)
    result = []
    for word in words:
        if word.isspace():
            result.append(word)
            continue
        lower = word.lower().strip(".,!?;:'\"")
        if lower in WORD_TO_EMOJI:
            result.append(WORD_TO_EMOJI[lower])
        else:
            converted = " ".join(_letter_to_regional(ch) for ch in word if ch.isalpha())
            if converted:
                result.append(converted)
            else:
                result.append(word)
    output = " ".join(result)
    if len(output) > 2000:
        output = output[:2000]
    return output


class Emojify(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Emojify module has been loaded")

    @commands.command()
    async def emojify(self, ctx, *, text: str):
        """Convert text to emoji. Usage: !emojify <text>"""
        await ctx.send(_emojify(text))

    @app_commands.command(name="emojify", description="Convert text to emoji madness")
    @app_commands.describe(text="The text to emojify")
    async def emojify_slash(self, interaction: discord.Interaction, text: str):
        await interaction.response.send_message(_emojify(text))


async def setup(bot):
    await bot.add_cog(Emojify(bot))
