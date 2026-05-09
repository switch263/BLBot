import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
import sqlite3
from datetime import date, datetime, timedelta
import logging
import economy
from cogs.lootdrop_card import render_card, pick_species, _OBJECT_DISPLAY_NAMES

logger = logging.getLogger(__name__)

# Rarity tiers: (name, color, coin_range, weight, emoji)
# Floor 10k (Common low), ceiling 10M (Mythic high). Each tier roughly 3-4x the previous.
RARITIES = [
    ("Common",    discord.Color.light_grey(),           (10_000,      50_000),     40, "⬜"),
    ("Uncommon",  discord.Color.green(),                (50_000,      200_000),    30, "🟩"),
    ("Rare",      discord.Color.blue(),                 (200_000,     750_000),    18, "🟦"),
    ("Epic",      discord.Color.purple(),               (750_000,     2_000_000),   8, "🟪"),
    ("Legendary", discord.Color.gold(),                 (2_000_000,   5_000_000),   3, "🟨"),
    ("Mythic",    discord.Color.from_rgb(255, 50, 200), (5_000_000,   10_000_000),  1, "🌈"),
    # Divine — once-in-a-blue-moon tier. Always renders the QR-code "Forbidden
    # Codex" card (which scans to a friendly Rickroll). Weight 1 keeps it rare.
    ("Divine",    discord.Color.from_rgb(255, 240, 200), (100_000_000, 150_000_000), 1, "✨"),
]

ITEM_PREFIXES = [
    "Enchanted", "Cursed", "Blessed", "Rusty", "Golden", "Haunted", "Forbidden",
    "Tactical", "Bootleg", "Vintage", "Overclocked", "Sentient", "Discount",
    "Radioactive", "Slightly Used", "Artisanal", "Weaponized", "Holy",
    "Deep-Fried", "Quantum", "Turbo", "Invisible", "Suspiciously Cheap",
    "Crowdfunded", "Limited-Edition", "Counterfeit", "Off-Brand", "Microwaved",
    "AI-Generated", "Open-Source", "Heirloom", "Smuggled", "Unlicensed",
    "Self-Aware", "Whispering", "Possessed", "Reinforced", "Lukewarm",
]

ITEM_OBJECTS = [
    "Gaming Chair", "Mechanical Keyboard", "Energy Drink", "Mouse Pad",
    "Ethernet Cable", "USB Stick", "Graphics Card", "Server Rack",
    "Headset", "Monitor Stand", "Desk Lamp", "Coffee Mug",
    "Pizza Slice", "Doritos Bag", "Mountain Dew", "Hot Pocket",
    "Rubber Duck", "Foam Sword", "Action Figure", "Dice Set",
    "Body Pillow", "Fedora", "Katana", "Trench Coat",
    "Participation Trophy", "Ban Hammer", "Mod Badge", "Discord Nitro Card",
    "Cracked Smartphone", "Lava Lamp", "Beanbag Chair", "Snuggie",
    "Rubber Chicken", "Lockpick Kit", "Nicotine Gum", "Crystal Skull",
    "VHS Tape", "Pog", "Tamagotchi", "Pet Rock",
]

ITEM_SUFFIXES = [
    "of Infinite Snacks", "of Unending Lag", "of Dubious Origin",
    "of Maximum FPS", "of Questionable Taste", "of the Ancient Ones",
    "of Mild Inconvenience", "of Overwhelming Power", "of Sus",
    "of the AFK", "of the Ragequit", "of the Tryhard",
    "of Absolute Unit Energy", "of the Basement Dweller",
    "of the Last Pick", "of Clutch Plays", "of the Carry",
    "that Nobody Asked For", "from Wish.com", "of the One True Gamer",
    "of Yesterday's Patch Notes", "of the Forgotten Discord",
    "of Chronic Latency", "of the Eternal Queue",
    "of the Side Quest", "of Mid Vibes Only",
    "of Suspicious Accuracy", "of the Speedrun Skip",
    "of Dollar-Store Magic", "of Plot Armor",
]

# Snarky one-liners shown under any drop worth less than 100,000 coins —
# basically the bot pointing and laughing when you roll the bottom of the barrel.
LOW_LOOT_SNARK = [
    "Haha, gotcha! Thought you'd get a good loot. I think not.",
    "Don't spend it all in one place. Actually, you couldn't even if you tried.",
    "The loot gods have spoken. They said: lol, no.",
    "Imagine being you opening this. I am imagining it. It's funny.",
    "I would say better luck next time, but let's be real.",
    "This is the kind of drop that builds character. A lot of character.",
    "Pity coins, basically. Here you go, sport.",
    "RNG looked at your wallet and decided: you've had enough.",
    "Congrats! You played yourself.",
    "That'll buy you about half a sad sandwich. Enjoy.",
    "Rolled the dice and got a participation trophy.",
    "I dropped this on purpose, just for you. Out of spite.",
    "Statistically, this is the worst possible outcome. Stats don't lie.",
    "You opened the loot. The loot opened nothing back.",
    "Some people get gold. You get this. That's the deal.",
    "I'd refund this but the universe doesn't accept returns.",
    "Hey, somebody's gotta roll the bad ones. Today, that's you.",
    "This drop personally insulted me on the way out.",
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
    "A pigeon delivered this strapped to its leg.",
    "The vending machine ate your dollar but gave you this.",
    "You won a Kahoot and the prize was real this time.",
    "Found in a couch you swear you've never owned.",
    "A glitch in the matrix coughed this up.",
    "This was wedged inside a library book about taxes.",
    "A mall Santa pressed it into your hand and winked.",
    "It rolled out of a shopping cart in a thunderstorm.",
]


def _current_slot() -> str:
    return "am" if datetime.now().hour < 12 else "pm"


def _next_reset() -> datetime:
    """Next moment a fresh slot opens — noon today (if before noon) or midnight tomorrow."""
    now = datetime.now()
    if now.hour < 12:
        return now.replace(hour=12, minute=0, second=0, microsecond=0)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


class LootDrop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Loot Drop module has been loaded")

    def _check_and_set_cooldown(self, guild_id: int, user_id: int) -> bool:
        """Returns True if the current AM/PM slot is fresh and stamps it."""
        today = date.today().isoformat()
        column = f"last_loot_{_current_slot()}"  # safe: derived from a closed set
        try:
            with sqlite3.connect(economy.DB_FILE) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO loot_cooldowns (guild_id, user_id) VALUES (?, ?)",
                    (guild_id, user_id)
                )
                cursor = conn.execute(
                    f"SELECT {column} FROM loot_cooldowns WHERE guild_id = ? AND user_id = ?",
                    (guild_id, user_id)
                )
                last = (cursor.fetchone()[0] or "")
                if last == today:
                    return False
                conn.execute(
                    f"UPDATE loot_cooldowns SET {column} = ? WHERE guild_id = ? AND user_id = ?",
                    (today, guild_id, user_id)
                )
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"Database error checking loot cooldown: {e}")
            return False

    def _generate_loot(self) -> tuple[str, str, int, discord.Color, str, str]:
        """Generate a random loot item. Returns (rarity_name, item_name, coins, color, emoji, species).

        The species drives both the card art and the noun in the item name, so
        the title and the picture always agree."""
        weights = [r[3] for r in RARITIES]
        rarity = random.choices(RARITIES, weights=weights, k=1)[0]
        rarity_name, color, coin_range, _, emoji = rarity

        coins = random.randint(coin_range[0], coin_range[1])
        # Divine tier always rolls the Forbidden Codex (QR card); other tiers
        # pick a random object from the standard pool.
        if rarity_name == "Divine":
            species = "qr_rickroll"
            item_name = "Forbidden Codex"
        else:
            species = pick_species()
            prefix = random.choice(ITEM_PREFIXES)
            suffix = random.choice(ITEM_SUFFIXES)
            species_word = _OBJECT_DISPLAY_NAMES.get(species,
                                                      species.replace("_", " ").title())
            # Match render_card's grammar fix — drop a leading "The" so the
            # nickname-prepended title doesn't double-article ("the The Goat").
            if species_word.lower().startswith("the "):
                species_word = species_word[4:]
            item_name = f"{prefix} {species_word} {suffix}"

        return rarity_name, item_name, coins, color, emoji, species

    async def _open_loot(
        self, guild_id: int, user: discord.Member
    ) -> tuple[discord.Embed, discord.File | None]:
        """Returns (embed, optional card file). Card is None when locked or render fails."""
        next_reset_ts = int(_next_reset().timestamp())
        if not self._check_and_set_cooldown(guild_id, user.id):
            slot = _current_slot().upper()
            embed = discord.Embed(
                title="🔒 Loot Locked",
                description=(
                    f"You've already cracked open the **{slot}** drop.\n"
                    f"Two drops a day — one resets at **00:00**, the other at **12:00**.\n"
                    f"Next drop opens <t:{next_reset_ts}:R>."
                ),
                color=discord.Color.red(),
            )
            return embed, None

        rarity_name, item_name, coins, color, emoji, species = self._generate_loot()
        economy.add_coins(guild_id, user.id, coins)

        flavor = random.choice(FLAVOR_TEXT)
        slot = _current_slot()

        description = f"**{item_name}**"
        if coins < 100_000:
            description += f"\n*{random.choice(LOW_LOOT_SNARK)}*"

        embed = discord.Embed(
            title=f"{emoji} {rarity_name} Loot Drop! {emoji}",
            description=description,
            color=color,
        )
        embed.add_field(name="Next Drop", value=f"<t:{next_reset_ts}:R>", inline=True)

        # Render card off the event loop — pure-Python pixel work would otherwise
        # block heartbeats on slower hosts.
        card_file: discord.File | None = None
        try:
            buf = await asyncio.to_thread(
                render_card,
                rarity_name=rarity_name,
                item_name=item_name,
                coins=coins,
                color=color,
                flavor=flavor,
                is_mythic=(rarity_name == "Mythic"),
                minted_by=user.display_name,
                minted_at=datetime.utcnow().strftime("%Y-%m-%d"),
                species=species,
            )
            card_file = discord.File(buf, filename="lootcard.png")
            embed.set_image(url="attachment://lootcard.png")
        except Exception as e:
            # Fall back to text-only embed; never block a payout because rendering broke.
            logger.error(f"Loot card render failed, falling back to text embed: {e}")
            embed.add_field(
                name="Value",
                value=f"**{coins:,}** coins added to your wallet!",
                inline=False,
            )
            embed.add_field(name="Slot", value=slot.upper(), inline=True)
            embed.set_footer(text=flavor)

        return embed, card_file

    @commands.command(aliases=['lootdrop', 'drop'])
    async def loot(self, ctx):
        """Open one of your two daily loot drops (resets at 00:00 and 12:00)."""
        embed, card = await self._open_loot(ctx.guild.id, ctx.author)
        await ctx.send(embed=embed, file=card) if card else await ctx.send(embed=embed)

    @app_commands.command(name="loot", description="Open a loot drop. Two per day — resets at 00:00 and 12:00.")
    async def loot_slash(self, interaction: discord.Interaction):
        # Defer up front — the card render takes a few hundred ms and would
        # otherwise risk the 3-second interaction ack window.
        await interaction.response.defer()
        embed, card = await self._open_loot(interaction.guild_id, interaction.user)
        if card:
            await interaction.followup.send(embed=embed, file=card)
        else:
            await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(LootDrop(bot))
