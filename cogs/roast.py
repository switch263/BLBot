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
    "Breaking news,",
    "Hot take,",
    "PSA,",
    "Hear ye, hear ye,",
    "Gather round everyone,",
    "Let the record show,",
    "For the record,",
    "Bless your heart,",
    "With all due respect (which is none),",
    "I did the math,",
    "Science has confirmed,",
    "After careful peer review,",
    "The council has voted,",
    "In today's episode of sad,",
    "Buckle up,",
    "Point of order,",
    "Friendly reminder,",
    "Fun fact,",
    "Quick announcement,",
    "I consulted the elders,",
    "The prophecy was true,",
    "Per my last email,",
    "I ran the numbers twice,",
    "The committee has reached a verdict,",
    "Straight from the lab results,",
    "I asked around and,",
    "The intel just came in,",
    "Per the ancient scrolls,",
    "According to my sources,",
    "Local news at 11:",
]

ADJECTIVES = [
    "off-brand", "lukewarm", "discount", "expired", "bootleg", "watered-down",
    "dollar-store", "flat", "stale", "microwaved", "defrosted", "clearance-rack",
    "refurbished", "knock-off", "soggy", "room-temperature", "store-brand",
    "forgotten", "undercooked", "overcooked", "half-baked", "unseasoned",
    "bargain-bin", "last-resort", "participation-trophy", "factory-second",
    "decaf", "low-resolution", "pixelated", "buffering", "laggy", "dial-up",
    "secondhand", "thrift-store", "gas-station", "vending-machine",
    "straight-to-DVD", "out-of-warranty", "recalled", "counterfeit",
    "imitation", "generic", "unsalted", "decaffeinated", "non-alcoholic",
    "sugar-free", "low-budget", "off-season", "day-old", "week-old",
    "freezer-burned", "left-out-overnight", "lint-covered", "waterlogged",
    "deflated", "unplugged", "unlicensed", "uninspired", "beta-version",
    "early-access", "demo-version", "free-trial", "ad-supported",
    "pre-owned", "open-box", "as-is", "final-sale", "misprinted",
    "wrinkled", "off-center", "crooked", "leftover", "reheated",
    "thawed-out", "limp", "mass-produced", "off-key", "low-effort",
    "budget-cut", "discontinued", "back-ordered", "out-of-stock",
    "water-damaged", "sun-bleached", "moth-eaten", "hand-me-down",
    "single-ply", "powdered", "instant", "artificially-flavored",
    "shrink-flated", "side-of-the-road", "dumpster-adjacent",
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
    "decaf espresso", "warm lettuce", "unsalted cracker", "expired coupon",
    "wet napkin", "mystery meat", "school lunch milk carton",
    "Monday morning", "dead pixel", "dial-up modem", "Windows update",
    "printer at 2% ink", "single-ply toilet paper", "elevator music",
    "hold music playlist", "spam folder", "broken vending machine",
    "shopping cart with one bad wheel", "IKEA instruction manual",
    "USB plugged in upside down", "low battery warning", "autoplay video",
    "unskippable ad", "group project member who does nothing",
    "side quest nobody accepts", "respawn timer", "lag spike",
    "disconnected controller", "empty stapler", "dried-out marker",
    "left shoe with no right shoe", "puzzle missing one piece",
    "expired yogurt", "warm soda", "flat energy drink",
    "melted ice cream cone on the sidewalk", "soggy cereal", "burnt toast",
    "raisin cookie pretending to be chocolate chip", "decorative pillow",
    "screen protector with bubbles in it", "knockoff LEGO set",
    "off-brand cereal mascot", "haunted Roomba", "traffic cone",
    "wet cardboard box", "expired parking meter",
    "broken umbrella in a hurricane", "treadmill used as a clothes hanger",
    "fortune cookie without a fortune", "scratch-off ticket that lost",
    "dollar store glow stick", "birthday clown on a Tuesday",
    "mall kiosk salesman", "pop quiz", "failed parallel parking attempt",
    "speed bump", "wrong-way driver in Mario Kart", "expired AOL trial CD",
    "motel ice machine", "broken escalator", "self-checkout error",
    "phone at 1% with no charger", "QR code menu", "lost shopping list",
    "warm mayonnaise sandwich", "ketchup packet with a pinhole leak",
    "free hotel breakfast", "third sequel nobody asked for",
    "tangled pair of earbuds", "couch cushion fort in a thunderstorm",
    "pen at the bank chained to the desk", "browser with 47 toolbars",
    "kazoo solo at a funeral", "deflated bouncy castle",
    "off-brand battery that leaks", "GPS that says 'recalculating'",
    "expired fire extinguisher", "Bluetooth speaker at 10% volume",
    "soggy paper straw", "self-help book in a bargain bin",
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
    "Your microphone quality is the best thing about your opinions, and it's terrible.",
    "You type like you're wearing oven mitts.",
    "Your ping is the only thing higher than your ego.",
    "You're the teammate the enemy team thanks after the match.",
    "You'd be the first eliminated in a game show about being yourself.",
    "Your hot takes are room temperature at best.",
    "You're the reason the tutorial can't be skipped.",
    "You aim like the crosshair owes you money.",
    "You're the kind of player who pings 'enemy missing' after dying to them.",
    "Your build order is alphabetical.",
    "You'd lose a 1v1 against a training dummy.",
    "Your game sense has been AFK since launch day.",
    "You're hardstuck in the tutorial of life.",
    "You queue ranked like it's a charity event for the enemy team.",
    "You're the human equivalent of friendly fire.",
    "Your reaction time is measured in business days.",
    "You're the DLC nobody downloads even when it's free.",
    "Your inventory is full and it's all copium.",
    "You're the pre-order bonus of people: promised a lot, delivered a skin.",
    "You main excuses.",
    "Your highlight reel is a loading screen.",
    "You're proof that matchmaking is broken.",
    "Your character arc is a flat line.",
    "Even the AFK bot contributes more than you.",
    "You're the patch note that just says 'minor bug fixes.'",
    "Your brain runs on integrated graphics.",
    "You've got main character energy and background character stats.",
    "You're the lag in everyone else's day.",
    "Your opinions come with a 'skip ad' button and everyone presses it.",
    "You're the group chat member everyone has on mute.",
    "Your personality is a default settings menu.",
    "You bring great energy — somewhere else, hopefully.",
    "You're the human version of stepping on a LEGO: painful and pointless.",
    "You're the typo in humanity's group project.",
    "If charisma was water, you'd be a drought.",
    "You're a rough draft that got published by accident.",
    "Your vibe is 'meeting that could have been an email.'",
    "You're the pop-up that asks me to rate the app while I'm using it.",
    "You're the cliffhanger of a show that got cancelled.",
    "Your potential filed a missing persons report.",
    "You're the free sample of a product nobody buys.",
    "You're a limited edition, thankfully.",
    "Your comfort zone has a comfort zone.",
    "You're the 'we have food at home' of people.",
    "You're an open book — unfortunately it's a coloring book.",
    "You're the human snooze button.",
    "Your bucket list is a sticky note that says 'maybe later.'",
    "You're a walking 'content unavailable in your region' message.",
    "You're the plot hole in your own story.",
    "Your five-year plan is a screenshot of someone else's.",
    "You're the survey at the end of a phone call.",
    "You're the human form of a forgotten password.",
    "Your aura is 'last slice of pizza that's just crust.'",
    "You're the 'reply all' to a company-wide email.",
    "You're a fire drill during lunch.",
    "Your résumé and your imagination have a lot in common.",
    "You're the recommended video nobody clicks.",
    "You're a software license agreement: long, boring, and ignored.",
    "You're the human equivalent of biting into a grape that's gone bad.",
    "You're the warm middle seat on a full flight.",
    "Your wisdom teeth had more wisdom and they got removed.",
    "You're the 'check engine' light of the friend group: on all the time, ignored by everyone.",
    "You're the password hint that doesn't help.",
    "You're a tutorial pop-up on level 50.",
    "You're the guy who says 'we' when the team wins and 'they' when it loses.",
    "Your search history is just 'how to be interesting' with zero results clicked.",
    "You're the human equivalent of a phone falling on your face in bed.",
    "You're a motivational poster in a room nobody enters.",
    "You're a vibe check that bounced.",
    "You're the encore nobody clapped for.",
    "You're the 'unsubscribe' link that doesn't work.",
    "You're a webinar that could have been a tweet.",
    "You're the human version of autocorrect changing a word to something worse.",
    "You're the demo song on a keyboard at a garage sale.",
    "You're the 'are you still watching?' prompt, except nobody was.",
    "You're a slideshow with 90 slides and zero points.",
    "You're a meeting reminder for a meeting that was cancelled.",
    "You're the human form of decaf instant coffee.",
    "You're the toll booth on the road to fun.",
    "You're the splash zone at a kiddie pool.",
    "You're an out-of-office reply from someone who's in the office.",
    "You're a 'wet floor' sign on a dry floor — pure false advertising.",
    "Your glow-up got rescheduled indefinitely.",
    "You're a captcha that fails YOU.",
    "You're a sequel to a movie nobody saw.",
    "You're the human equivalent of an ad before a 15-second video.",
    "You're the receipt that prints a coupon for something you'll never buy.",
    "You're a fortune teller's day off.",
    "You're the human version of 'terms and conditions apply.'",
    "You're a karaoke machine with one song and it's broken.",
    "You're the friend who says 'I'm five minutes away' from their bed.",
    "You're a phone charger that only works at one specific angle.",
    "You're the human equivalent of remembering the comeback three days later.",
    "You're a gift card with $0.43 left on it.",
    "You're the Wi-Fi bar that shows full signal but nothing loads.",
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
    "Stay mad.",
    "It is what it is.",
    "Womp womp.",
    "L + ratio.",
    "Cry about it.",
    "Take notes.",
    "The truth hurts.",
    "Mic drop.",
    "Case closed.",
    "Court adjourned.",
    "Next question.",
    "Moving on.",
    "Thank you for coming to my TED Talk.",
    "Be better.",
    "Do with that what you will.",
    "Press F.",
    "Uninstall.",
    "Respawn and try again.",
    "Better luck next patch.",
    "Emotional damage.",
    "Seek help.",
    "And everyone agreed.",
    "Source: everyone.",
    "This has been peer reviewed.",
    "The committee thanks you for your time.",
    "Filed under: yikes.",
    "Anyway.",
    "Good talk.",
    "Hope this helps.",
    "Per my last roast.",
    "Carry on.",
    "",
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
            article = "an" if adj[0].lower() in "aeiou" else "a"
            roast = f"{opener} {target}, you're like {article} {adj} {noun}. {closer}"
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
