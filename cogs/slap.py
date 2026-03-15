import discord
from discord.ext import commands
from discord import app_commands
import random
import time
import logging

logger = logging.getLogger(__name__)

RETALIATION_THRESHOLD = 5  # slaps in a day before bot retaliates
RETALIATION_COOLDOWN = 86400  # 24 hours in seconds

RETALIATION_MESSAGES = [
    "**ENOUGH.** {bot} slaps {user} back with the force of a thousand suns! **KERPOW!**",
    "**OH YOU WANT SOME TOO?** {bot} roundhouse slaps {user} into next week! **WHAM!**",
    "{bot} has had it. {bot} delivers a {adj} counter-slap to {user}'s {target}! **CRITICAL HIT!**",
    "**THE BOT STRIKES BACK.** {bot} unleashes a devastating slap combo on {user}! **THWACK THWACK THWACK!**",
    "{bot} catches {user}'s hand mid-slap and reverses it. {user} slaps themselves! **UNO REVERSE!**",
    "**YOU FOOL.** {bot} has been training for this moment. {user} receives a legendary slap! **KABOOM!**",
    "{bot} pulls out a comically large hand and slaps {user} into orbit. **YEET!**",
    "After {count} slaps today, {bot} snaps. {user} gets absolutely DEMOLISHED. **FATALITY.**",
    "{bot} enters beast mode. {user} is slapped so hard their ancestors felt it. **ANCESTRAL DAMAGE!**",
    "{bot} summons a {adj} slap from the shadow realm. {user} is banished! **BEGONE!**",
    "**ERROR: SLAP LIMIT EXCEEDED.** {bot} blue-screens {user}'s {target} with a {adj} backhand.",
    "{bot} pulls out a medieval gauntlet and delivers {count} slaps in rapid succession to {user}! **COMBO FINISH!**",
    "{bot} has entered the chat. {bot} slaps {user} with a folding chair! **BAH GAWD!**",
    "**TACTICAL SLAP INCOMING.** {bot} air-drops a {adj} slap onto {user}'s {target}! **DIRECT HIT!**",
    "{bot} whispers 'nothing personal, kid' and teleports behind {user}. **SLAP.** {user} never saw it coming.",
    "**SLAP OVERLOAD.** {bot} malfunctions and delivers a {adj} mega-slap to {user}'s entire existence!",
]


class Slaps(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.random_generator = random.SystemRandom()
        self.slap_tracker = {}  # (guild_id, user_id) -> {"count": int, "reset_time": float}

        self.slap_sounds = [
            "WHAP", "THWACK", "SMACK", "POW", "BIFF", "WHAM", "SLAP",
            "KERPOW", "SPLAT", "BONK", "BOP", "BLAM", "ZOOM", "SWISH",
            "CRUNCH", "OOOF", "SMUSH", "KABOOM", "ZAP", "FLAP",
            "CLONK", "THUD", "CRACK", "WALLOP", "CLAP", "BASH",
            "TWACK", "WHOMP", "KLONK", "DONK", "FWAP", "YOINK",
            "PUNT", "KAPOW", "WACK", "PLONK", "SKADOOSH", "SCHMACK",
            "CLATTER", "THWONK",
        ]

        self.slap_adjectives = [
            "thunderous", "vicious", "stinging", "humiliating", "unexpected", "swift", "comical",
            "playful", "cartoony", "wobbly", "bouncy", "surreal", "jelly-like", "fishy",
            "noodle-based", "ridiculous", "absurd", "cosmic", "devastating", "legendary",
            "earth-shattering", "soul-crushing", "bone-rattling", "gravity-defying", "interdimensional",
            "nuclear", "catastrophic", "ungodly", "unforgivable", "disrespectful",
            "flamboyant", "theatrical", "dramatic", "cinematic", "Oscar-worthy",
            "suspicious", "questionable", "chaotic", "diabolical", "unholy",
            "emotionally devastating", "spiritually damaging", "legally questionable",
            "scientifically impossible", "historically unprecedented", "philosophically confusing",
        ]

        self.slap_targets = [
            "face", "cheek", "ego", "behind", "pride", "sense of humor", "hopes and dreams",
            "funny bone", "patience", "noodle", "sense of reality", "expectations",
            "self-esteem", "dignity", "will to live", "browser history", "credit score",
            "K/D ratio", "love life", "search history", "entire bloodline", "future children",
            "gaming chair", "forehead", "social standing", "career prospects",
            "remaining brain cells", "vibes", "aura", "chakras", "third eye",
            "moral compass", "sense of direction", "taste in music",
        ]

        self.slap_weapons = [
            "a wet fish", "a rubber chicken", "a foam noodle", "a rolled-up newspaper",
            "a comically large spoon", "a Nokia 3310", "a baguette", "an IKEA catalog",
            "a flip-flop (la chancla)", "a keyboard", "a folding chair",
            "a pool noodle", "a cactus", "a frozen burrito", "an encyclopedia",
            "a traffic cone", "a rubber duck", "a cast-iron skillet",
            "a slice of cold pizza", "their own shoe", "a Croc",
            "an oversized foam finger", "a garden hose", "a bag of Doritos",
            "a steering wheel", "a stop sign", "someone else's prosthetic leg",
            "a vintage rotary phone", "a taxidermied salmon", "a didgeridoo",
        ]

    def _track_slap(self, guild_id: int, user_id: int) -> int:
        """Track a slap and return the user's count for today."""
        key = (guild_id, user_id)
        now = time.time()
        entry = self.slap_tracker.get(key)

        if entry is None or now >= entry["reset_time"]:
            self.slap_tracker[key] = {"count": 1, "reset_time": now + RETALIATION_COOLDOWN}
            return 1

        entry["count"] += 1
        return entry["count"]

    def _generate_slap(self, author: discord.Member, member: discord.Member = None, channel_members=None):
        """Generate a slap message string."""
        rng = self.random_generator
        use_weapon = rng.random() < 0.3  # 30% chance to use a weapon

        if member is None:
            if rng.random() < 0.8:
                target = rng.choice(self.slap_targets)
                if use_weapon:
                    return f"{author.mention} delivers a {rng.choice(self.slap_adjectives)} {rng.choice(self.slap_sounds)} to their own {target} using {rng.choice(self.slap_weapons)}!"
                return f"{author.mention} delivers a {rng.choice(self.slap_adjectives)} {rng.choice(self.slap_sounds)} to their own {target}!"
            else:
                if channel_members:
                    random_member = rng.choice(channel_members)
                    if use_weapon:
                        return f"{author.mention} surprises {random_member.mention} with a {rng.choice(self.slap_adjectives)} {rng.choice(self.slap_sounds)} using {rng.choice(self.slap_weapons)}!"
                    return f"{author.mention} surprises {random_member.mention} with a {rng.choice(self.slap_adjectives)} {rng.choice(self.slap_sounds)}!"
                target = rng.choice(self.slap_targets)
                return f"{author.mention} delivers a {rng.choice(self.slap_adjectives)} {rng.choice(self.slap_sounds)} to their own {target}!"
        else:
            target = rng.choice(self.slap_targets)
            if use_weapon:
                return f"{author.mention} delivers a {rng.choice(self.slap_adjectives)} {rng.choice(self.slap_sounds)} to {member.mention}'s {target} using {rng.choice(self.slap_weapons)}!"
            return f"{author.mention} delivers a {rng.choice(self.slap_adjectives)} {rng.choice(self.slap_sounds)} to {member.mention}'s {target}!"

    def _generate_retaliation(self, bot_name: str, user: discord.Member, count: int) -> str:
        rng = self.random_generator
        msg = random.choice(RETALIATION_MESSAGES)
        return msg.format(
            bot=bot_name,
            user=user.mention,
            adj=rng.choice(self.slap_adjectives),
            target=rng.choice(self.slap_targets),
            count=count,
        )

    async def _do_slap(self, guild_id: int, author: discord.Member, member: discord.Member,
                       channel_members, send_func, followup_func):
        """Core slap logic with retaliation."""
        count = self._track_slap(guild_id, author.id)
        slap_msg = self._generate_slap(author, member, channel_members)
        await send_func(slap_msg)

        if count >= RETALIATION_THRESHOLD:
            retaliation = self._generate_retaliation(self.bot.user.display_name, author, count)
            await followup_func(retaliation)

    @commands.command()
    async def slap(self, ctx, member: discord.Member = None):
        await self._do_slap(ctx.guild.id, ctx.author, member, ctx.channel.members, ctx.send, ctx.send)

    @app_commands.command(name="slap", description="Slap someone (or yourself)")
    @app_commands.describe(member="The person to slap (leave empty for chaos)")
    async def slap_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        channel_members = interaction.channel.members if hasattr(interaction.channel, 'members') else None
        await interaction.response.send_message(self._generate_slap(interaction.user, member, channel_members))
        count = self._track_slap(interaction.guild_id, interaction.user.id)
        if count >= RETALIATION_THRESHOLD:
            retaliation = self._generate_retaliation(self.bot.user.display_name, interaction.user, count)
            await interaction.channel.send(retaliation)

async def setup(bot):
    await bot.add_cog(Slaps(bot))
