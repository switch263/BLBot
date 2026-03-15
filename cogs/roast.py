import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

logger = logging.getLogger(__name__)

OPENERS = [
    "Listen up,",
    "Oh boy,",
    "Brace yourself,",
    "I hate to break it to you,",
    "Not gonna sugarcoat this,",
    "Someone had to say it,",
    "No offense but,",
    "Real talk,",
    "I don't wanna be mean but,",
    "Alright look,",
]

ADJECTIVES = [
    "off-brand", "lukewarm", "discount", "expired", "bootleg", "watered-down",
    "dollar-store", "flat", "stale", "microwaved", "defrosted", "clearance-rack",
    "refurbished", "knock-off", "soggy", "room-temperature", "store-brand",
    "forgotten", "undercooked", "overcooked", "half-baked", "unseasoned",
    "bargain-bin", "last-resort", "participation-trophy", "factory-second",
]

NOUNS = [
    "chicken nugget", "potato", "crouton", "rice cake", "wet sock",
    "screen door on a submarine", "soup sandwich", "glass hammer",
    "chocolate teapot", "paper umbrella", "inflatable dartboard",
    "waterproof sponge", "solar-powered flashlight", "fireproof match",
    "NPC", "tutorial boss", "loading screen tip", "default skin",
    "unread notification", "terms and conditions page",
    "buffering wheel", "CAPTCHA", "404 error", "pop-up ad",
    "Comic Sans resume", "reply-all email", "fax machine",
    "participation medal", "gas station sushi", "airport pizza",
    "hotel pillow", "airplane blanket", "rest stop bathroom",
]

BURNS = [
    "You bring everyone so much joy... when you leave the voice channel.",
    "You're the reason God created the mute button.",
    "If you were a spice, you'd be flour.",
    "You're like a cloud. Everything brightens up when you disappear.",
    "You're not the dumbest person in the world, but you better hope they don't die.",
    "You're the human equivalent of a participation trophy.",
    "Your family tree must be a cactus because everyone on it is a prick.",
    "You're proof that even evolution makes mistakes.",
    "If brains were dynamite, you wouldn't have enough to blow your nose.",
    "You're the reason we have instructions on shampoo bottles.",
    "Somewhere out there, a tree is working very hard to produce oxygen for you. You owe it an apology.",
    "You bring the average down just by being in the server.",
    "You're like a software update — nobody wants you but we're stuck with you.",
    "Your aim in games is about as good as your life choices.",
    "You peaked in the character creation screen.",
    "I'd explain it to you but I left my crayons at home.",
    "You're the loading screen of people.",
    "Your K/D ratio in life is concerning.",
    "If you were any more basic, you'd be a tutorial level.",
    "You look like you'd lose a fight to a captcha.",
]

CLOSERS = [
    "No cap.",
    "And that's being generous.",
    "Sorry not sorry.",
    "Facts.",
    "I said what I said.",
    "Don't @ me.",
    "GG no re.",
    "Get rekt.",
    "Cope.",
    "Skill issue.",
    "Touch grass.",
    "",
    "",
    "",
]


class Roast(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Roast module has been loaded")

    def _generate_roast(self, target: str) -> str:
        """Generate a roast for the target."""
        style = random.choice(["template", "burn"])

        if style == "template":
            opener = random.choice(OPENERS)
            adj = random.choice(ADJECTIVES)
            noun = random.choice(NOUNS)
            closer = random.choice(CLOSERS)
            roast = f"{opener} {target}, you're like a {adj} {noun}. {closer}"
        else:
            burn = random.choice(BURNS)
            closer = random.choice(CLOSERS)
            roast = f"{target} - {burn} {closer}"

        return roast.strip()

    @commands.command()
    async def roast(self, ctx, member: discord.Member = None):
        """Roast someone (or yourself if you're brave)."""
        target = member.mention if member else ctx.author.mention
        await ctx.send(self._generate_roast(target))

    @app_commands.command(name="roast", description="Roast someone with a creative insult")
    @app_commands.describe(member="Who to roast (leave empty to roast yourself)")
    async def roast_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member.mention if member else interaction.user.mention
        await interaction.response.send_message(self._generate_roast(target))


async def setup(bot):
    await bot.add_cog(Roast(bot))
