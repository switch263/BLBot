import discord
from discord.ext import commands
from discord import app_commands
from config import DATA_DIR
import os
import random
import sqlite3
from datetime import date
import logging

logger = logging.getLogger(__name__)

# Rarity tiers: (name, color, coin_range, weight, emoji)
RARITIES = [
    ("Common",    discord.Color.light_grey(), (5, 25),      40, "⬜"),
    ("Uncommon",  discord.Color.green(),      (25, 75),     30, "🟩"),
    ("Rare",      discord.Color.blue(),       (75, 200),    18, "🟦"),
    ("Epic",      discord.Color.purple(),     (200, 500),    9, "🟪"),
    ("Legendary", discord.Color.gold(),       (500, 2000),   3, "🟨"),
]

ITEM_PREFIXES = [
    "Enchanted", "Cursed", "Blessed", "Rusty", "Golden", "Haunted", "Forbidden",
    "Tactical", "Bootleg", "Vintage", "Overclocked", "Sentient", "Discount",
    "Radioactive", "Slightly Used", "Artisanal", "Weaponized", "Holy",
    "Deep-Fried", "Quantum", "Turbo", "Invisible", "Suspiciously Cheap",
]

ITEM_OBJECTS = [
    "Gaming Chair", "Mechanical Keyboard", "Energy Drink", "Mouse Pad",
    "Ethernet Cable", "USB Stick", "Graphics Card", "Server Rack",
    "Headset", "Monitor Stand", "Desk Lamp", "Coffee Mug",
    "Pizza Slice", "Doritos Bag", "Mountain Dew", "Hot Pocket",
    "Rubber Duck", "Foam Sword", "Action Figure", "Dice Set",
    "Body Pillow", "Fedora", "Katana", "Trench Coat",
    "Participation Trophy", "Ban Hammer", "Mod Badge", "Discord Nitro Card",
]

ITEM_SUFFIXES = [
    "of Infinite Snacks", "of Unending Lag", "of Dubious Origin",
    "of Maximum FPS", "of Questionable Taste", "of the Ancient Ones",
    "of Mild Inconvenience", "of Overwhelming Power", "of Sus",
    "of the AFK", "of the Ragequit", "of the Tryhard",
    "of Absolute Unit Energy", "of the Basement Dweller",
    "of the Last Pick", "of Clutch Plays", "of the Carry",
    "that Nobody Asked For", "from Wish.com", "of the One True Gamer",
]

FLAVOR_TEXT = [
    "You found this in a dumpster behind GameStop.",
    "It fell from the sky. Don't ask questions.",
    "A mysterious stranger dropped this and ran.",
    "You won this in a claw machine on the first try.",
    "It was just... sitting there. On the ground. Glowing.",
    "Your grandma sent this in a care package.",
    "You found this taped under a park bench.",
    "A raccoon traded this to you for a sandwich.",
    "This was hidden inside a fortune cookie.",
    "A time traveler left this here by mistake.",
    "You pulled this from a stone. Nobody else could.",
    "This materialized after you sneezed three times.",
]


class LootDrop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_file = os.path.join(DATA_DIR, "slots.db")
        self._ensure_table()

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Loot Drop module has been loaded")

    def _ensure_table(self):
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS loot_cooldowns (
                        guild_id INTEGER,
                        user_id INTEGER,
                        last_loot TEXT DEFAULT '',
                        PRIMARY KEY (guild_id, user_id)
                    )
                ''')
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error creating loot table: {e}")

    def _check_and_set_cooldown(self, guild_id: int, user_id: int) -> bool:
        """Returns True if the user can loot, False if on cooldown. Sets cooldown if allowed."""
        today = date.today().isoformat()
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO loot_cooldowns (guild_id, user_id) VALUES (?, ?)",
                    (guild_id, user_id)
                )
                cursor = conn.execute(
                    "SELECT last_loot FROM loot_cooldowns WHERE guild_id = ? AND user_id = ?",
                    (guild_id, user_id)
                )
                last = cursor.fetchone()[0]
                if last == today:
                    return False
                conn.execute(
                    "UPDATE loot_cooldowns SET last_loot = ? WHERE guild_id = ? AND user_id = ?",
                    (today, guild_id, user_id)
                )
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"Database error checking loot cooldown: {e}")
            return False

    def _add_coins(self, guild_id: int, user_id: int, amount: int):
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, 100)",
                    (guild_id, user_id)
                )
                conn.execute(
                    "UPDATE wallets SET coins = coins + ?, total_won = total_won + ? WHERE guild_id = ? AND user_id = ?",
                    (amount, amount, guild_id, user_id)
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error adding loot coins: {e}")

    def _generate_loot(self) -> tuple[str, str, int, discord.Color, str]:
        """Generate a random loot item. Returns (rarity_name, item_name, coins, color, emoji)."""
        weights = [r[3] for r in RARITIES]
        rarity = random.choices(RARITIES, weights=weights, k=1)[0]
        rarity_name, color, coin_range, _, emoji = rarity

        coins = random.randint(coin_range[0], coin_range[1])
        prefix = random.choice(ITEM_PREFIXES)
        obj = random.choice(ITEM_OBJECTS)
        suffix = random.choice(ITEM_SUFFIXES)
        item_name = f"{prefix} {obj} {suffix}"

        return rarity_name, item_name, coins, color, emoji

    async def _open_loot(self, guild_id: int, user: discord.Member) -> discord.Embed:
        if not self._check_and_set_cooldown(guild_id, user.id):
            return discord.Embed(
                title="No Loot Available",
                description="You already opened a loot drop today! Come back tomorrow.",
                color=discord.Color.red()
            )

        rarity_name, item_name, coins, color, emoji = self._generate_loot()
        self._add_coins(guild_id, user.id, coins)

        flavor = random.choice(FLAVOR_TEXT)

        embed = discord.Embed(
            title=f"{emoji} {rarity_name} Loot Drop! {emoji}",
            description=f"**{item_name}**",
            color=color
        )
        embed.add_field(name="Value", value=f"**{coins}** coins added to your wallet!", inline=False)
        embed.add_field(name="Rarity", value=f"{emoji} {rarity_name}", inline=True)
        embed.set_footer(text=flavor)

        return embed

    @commands.command(aliases=['lootdrop', 'drop'])
    async def loot(self, ctx):
        """Open a daily loot drop for random coins!"""
        embed = await self._open_loot(ctx.guild.id, ctx.author)
        await ctx.send(embed=embed)

    @app_commands.command(name="loot", description="Open a daily loot drop for random coins!")
    async def loot_slash(self, interaction: discord.Interaction):
        embed = await self._open_loot(interaction.guild_id, interaction.user)
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(LootDrop(bot))
