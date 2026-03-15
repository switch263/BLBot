import discord
from discord.ext import commands
from discord import app_commands
import hashlib
import logging

logger = logging.getLogger(__name__)

CLASSES = [
    "Professional Procrastinator",
    "Certified Couch Potato",
    "Level 99 Lurker",
    "Keyboard Warrior",
    "Meme Lord",
    "Discord Gremlin",
    "Chaotic Neutral Barista",
    "Unlicensed Therapist",
    "Full-Stack Disappointment",
    "Tactical Shitposter",
    "Legendary Overthinker",
    "Grandmaster of Naps",
    "Arcane Snack Summoner",
    "Rogue WiFi Thief",
    "Shadow IT Department",
    "Bard of Bad Takes",
    "Paladin of Passive Aggression",
    "Necromancer of Dead Memes",
    "Warlock of Wikipedia Rabbit Holes",
    "Berserker of Bad Decisions",
    "Druid of Doom Scrolling",
    "Cleric of Comfort Food",
    "Ranger of Random Trivia",
    "Monk of Minimal Effort",
]

SPECIAL_ABILITIES = [
    "Can fall asleep literally anywhere",
    "Sends memes at the speed of light",
    "Immune to awkward silences (causes them instead)",
    "Can eat an entire pizza in one sitting",
    "Passive: Makes every conversation weird",
    "Can quote entire movie scripts from memory",
    "Summons snacks from thin air",
    "Instantly knows when someone is wrong on the internet",
    "Can scroll through social media for 8 hours straight",
    "Aura of Mild Disappointment (30 ft radius)",
    "Resistance to touch grass damage",
    "Can type 120 WPM but only in arguments",
    "Ability to procrastinate beyond mortal limits",
    "Gains strength from caffeine overdoses",
    "Can hear a notification from three rooms away",
    "Reflexive 'lol' response to all messages",
    "Double XP from staying up past 3 AM",
    "Critical hit chance on sarcastic remarks",
    "Passive: Always has a relevant GIF",
    "Can survive on ramen for weeks",
    "Uncanny ability to find the worst take in any thread",
    "Power nap recharges all abilities instantly",
    "Immune to spoilers (already spoiled everything)",
    "Can weaponize dad jokes",
]


def _hash_int(user_id: int, salt: str = "") -> int:
    """Deterministic hash of a user ID with optional salt."""
    h = hashlib.sha256(f"{user_id}{salt}".encode()).hexdigest()
    return int(h, 16)


def _stat(user_id: int, stat_name: str) -> int:
    """Generate a deterministic stat (1-20) for a user."""
    return (_hash_int(user_id, stat_name) % 20) + 1


def _pick(user_id: int, salt: str, options: list):
    """Deterministically pick from a list based on user ID."""
    idx = _hash_int(user_id, salt) % len(options)
    return options[idx]


class Lifestats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Lifestats module has been loaded")

    def _build_embed(self, target: discord.Member) -> discord.Embed:
        uid = target.id
        stats = {
            "STR": _stat(uid, "STR"),
            "DEX": _stat(uid, "DEX"),
            "CON": _stat(uid, "CON"),
            "INT": _stat(uid, "INT"),
            "WIS": _stat(uid, "WIS"),
            "CHA": _stat(uid, "CHA"),
        }
        total = sum(stats.values())
        level = (_hash_int(uid, "LEVEL") % 99) + 1
        hp = stats["CON"] * level + _hash_int(uid, "HP") % 50
        char_class = _pick(uid, "CLASS", CLASSES)
        ability = _pick(uid, "ABILITY", SPECIAL_ABILITIES)

        # Color based on total stat points: red (low) -> yellow (mid) -> green (high)
        ratio = (total - 6) / (120 - 6)  # 6 min, 120 max
        if ratio < 0.33:
            color = discord.Color.red()
        elif ratio < 0.66:
            color = discord.Color.gold()
        else:
            color = discord.Color.green()

        stat_block = "\n".join(f"**{k}:** {v} {'█' * v}{'░' * (20 - v)}" for k, v in stats.items())

        embed = discord.Embed(
            title=f"Character Sheet: {target.display_name}",
            color=color,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Class", value=char_class, inline=True)
        embed.add_field(name="Level", value=str(level), inline=True)
        embed.add_field(name="HP", value=str(hp), inline=True)
        embed.add_field(name="Stats", value=stat_block, inline=False)
        embed.add_field(name="Special Ability", value=ability, inline=False)
        embed.set_footer(text=f"Total stat points: {total}/120")
        return embed

    @commands.command()
    async def lifestats(self, ctx, member: discord.Member = None):
        """View someone's RPG character sheet. Usage: !lifestats [@user]"""
        target = member or ctx.author
        await ctx.send(embed=self._build_embed(target))

    @app_commands.command(name="lifestats", description="View someone's fake RPG character sheet")
    @app_commands.describe(member="The user to inspect (defaults to yourself)")
    async def lifestats_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        await interaction.response.send_message(embed=self._build_embed(target))


async def setup(bot):
    await bot.add_cog(Lifestats(bot))
