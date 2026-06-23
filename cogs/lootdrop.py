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
from items import ITEMS, ALL_ITEMS

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

# Fraction of loot drops that yield an item card instead of coins. Item cards
# are sellable now (see items.py `sell_value`), so a higher rate means more
# realizable value per drop, not just more clutter.
ITEM_DROP_CHANCE = 0.35

# Item-card drops carry Sell / Re-roll buttons. A re-roll burns the card plus
# this fraction of its sell value, then mints a fresh random card — capped at
# one per player per day (stamped in the _REROLL_NS kv namespace).
REROLL_COST_FRACTION = 0.75
_REROLL_NS = "loot_reroll"

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


class ItemDropView(discord.ui.View):
    """Buttons under an item-card drop: sell it for coins, or gamble a re-roll
    (one per day) for a fresh card. Only the player who opened the drop may act.

    Buttons go dead after an hour, or once the card is sold/re-rolled away."""

    def __init__(self, cog: "LootDrop", guild_id: int, owner_id: int, item_key: str):
        super().__init__(timeout=3600)
        self.cog = cog
        self.guild_id = guild_id
        self.owner_id = owner_id
        self.item_key = item_key
        self.message: discord.Message | None = None

        meta = ITEMS.get(item_key, {})
        sell_value = meta.get("sell_value")
        # No sell value → nothing to sell or gamble; strip the buttons entirely.
        if not sell_value:
            self.clear_items()
            self.sell_value = 0
            self.reroll_cost = 0
            return
        self.sell_value = sell_value
        self.reroll_cost = int(sell_value * REROLL_COST_FRACTION)
        self.sell_button.label = f"Sell · {sell_value:,}"
        self.reroll_button.label = f"Re-roll · {self.reroll_cost:,}"

    async def _guard(self, interaction: discord.Interaction) -> bool:
        """Reject clicks from anyone but the drop's owner."""
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "This isn't your loot card — open your own with `/loot`.",
                ephemeral=True,
            )
            return False
        return True

    def _disable_all(self):
        for child in self.children:
            child.disabled = True

    async def on_timeout(self):
        self._disable_all()
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Sell", style=discord.ButtonStyle.success, emoji="💰")
    async def sell_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        if not economy.consume_item(self.guild_id, self.owner_id, self.item_key):
            self._disable_all()
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(
                "That card's already gone from your inventory.", ephemeral=True
            )
            return
        economy.add_coins(self.guild_id, self.owner_id, self.sell_value)
        self._disable_all()
        embed = interaction.message.embeds[0]
        embed.add_field(
            name="💰 Sold",
            value=f"**{self.sell_value:,}** coins added to your wallet.",
            inline=False,
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Re-roll", style=discord.ButtonStyle.danger, emoji="🎲")
    async def reroll_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        ok, message, drop = await self.cog._reroll_item(
            self.guild_id, interaction.user, self.item_key, self.reroll_cost
        )
        if not ok:
            await interaction.response.send_message(message, ephemeral=True)
            return
        # Original card is spent — kill this message's buttons and note it...
        self._disable_all()
        embed = interaction.message.embeds[0]
        embed.add_field(
            name="🎲 Re-rolled",
            value=f"Burned this card + **{self.reroll_cost:,}** coins for a new one below.",
            inline=False,
        )
        await interaction.response.edit_message(embed=embed, view=self)
        # ...then drop the fresh card as its own message with its own buttons.
        new_embed, new_card, new_view = drop
        kwargs = {"embed": new_embed}
        if new_card:
            kwargs["file"] = new_card
        if new_view:
            kwargs["view"] = new_view
        sent = await interaction.followup.send(**kwargs)
        if new_view:
            new_view.message = sent


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
    ) -> tuple[discord.Embed, discord.File | None, discord.ui.View | None]:
        """Returns (embed, optional card file, optional button view). Card is None
        when locked or render fails; the view rides along only on item-card drops."""
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
            return embed, None, None

        # Roll: this drop is either an item card or the usual coin haul.
        if random.random() < ITEM_DROP_CHANCE:
            return await self._open_item_drop(guild_id, user, next_reset_ts)

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
                minted_at=economy.today_str(),
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

        return embed, card_file, None

    async def _open_item_drop(
        self, guild_id: int, user: discord.Member, next_reset_ts: int
    ) -> tuple[discord.Embed, discord.File | None, discord.ui.View | None]:
        """An item-card loot drop: grant a random shop item and render it as a
        card through the same engine the coin drops use. Comes with Sell /
        Re-roll buttons (an ItemDropView)."""
        # Pick which item, weighted by each item's loot_weight.
        keys = list(ALL_ITEMS)
        item_key = random.choices(
            keys, weights=[ITEMS[k]["loot_weight"] for k in keys], k=1
        )[0]
        meta = ITEMS[item_key]
        economy.grant_item(guild_id, user.id, item_key)

        # Roll a rarity purely for card flair — color, frame, sparkle density.
        # Divine is excluded; it's reserved for the special coin-card tier.
        flair_tiers = [r for r in RARITIES if r[0] != "Divine"]
        rarity_name, color, _coin_range, _w, _emoji = random.choices(
            flair_tiers, weights=[r[3] for r in flair_tiers], k=1
        )[0]

        sell_value = meta.get("sell_value")
        worth_line = (
            f"Worth **{sell_value:,}** coins if you `/sell` it.\n"
            if sell_value else ""
        )
        embed = discord.Embed(
            title=f"{meta['emoji']} Item Card Drop! {meta['emoji']}",
            description=(
                f"**{meta['name']}**\n{meta['blurb']}\n\n"
                f"{worth_line}"
                f"Added to your inventory — check it with `/inventory`."
            ),
            color=color,
        )
        embed.add_field(name="Next Drop", value=f"<t:{next_reset_ts}:R>", inline=True)

        card_file: discord.File | None = None
        try:
            buf = await asyncio.to_thread(
                render_card,
                rarity_name=rarity_name,
                item_name=meta["name"],
                coins=0,
                color=color,
                flavor=meta["flavor"],
                is_mythic=(rarity_name == "Mythic"),
                minted_by=user.display_name,
                minted_at=economy.today_str(),
                species=meta.get("card_species") or pick_species(),
                value_text="◆ ITEM CARD ◆",
                name_prefix=False,
            )
            card_file = discord.File(buf, filename="lootcard.png")
            embed.set_image(url="attachment://lootcard.png")
        except Exception as e:
            logger.error(f"Item card render failed, falling back to text embed: {e}")
            embed.set_footer(text=meta["flavor"])

        view = ItemDropView(self, guild_id, user.id, item_key)
        return embed, card_file, view

    async def _reroll_item(
        self, guild_id: int, user: discord.Member, item_key: str, reroll_cost: int
    ) -> tuple[bool, str, tuple | None]:
        """Spend the daily re-roll: burn the card + cost, mint a fresh item drop.
        Returns (ok, error_message, drop) where drop is the (embed, file, view)
        tuple for the new card when ok, else None."""
        today = economy.today_str()
        if economy.kv_get(guild_id, user.id, _REROLL_NS, "date", "") == today:
            return False, "🎲 You've already burned your re-roll today. Back tomorrow, gambler.", None
        # Burn the original card first; bail if it's no longer held.
        if not economy.consume_item(guild_id, user.id, item_key):
            return False, "That card's no longer in your inventory.", None
        # Charge the gambling tax — refund the card if they can't cover it.
        if not economy.try_deduct(guild_id, user.id, reroll_cost):
            economy.grant_item(guild_id, user.id, item_key)
            have = economy.get_coins(guild_id, user.id)
            return False, (
                f"Re-roll costs **{reroll_cost:,}** coins — you've only got "
                f"**{have:,}**. Card kept, no re-roll."
            ), None
        economy.kv_set(guild_id, user.id, _REROLL_NS, "date", today)
        next_reset_ts = int(_next_reset().timestamp())
        drop = await self._open_item_drop(guild_id, user, next_reset_ts)
        return True, "", drop

    @commands.command(aliases=['lootdrop', 'drop'])
    async def loot(self, ctx):
        """Open one of your two daily loot drops (resets at 00:00 and 12:00)."""
        embed, card, view = await self._open_loot(ctx.guild.id, ctx.author)
        kwargs = {"embed": embed}
        if card:
            kwargs["file"] = card
        if view:
            kwargs["view"] = view
        sent = await ctx.send(**kwargs)
        if view:
            view.message = sent

    @app_commands.command(name="loot", description="Open a loot drop. Two per day — resets at 00:00 and 12:00.")
    async def loot_slash(self, interaction: discord.Interaction):
        # Defer up front — the card render takes a few hundred ms and would
        # otherwise risk the 3-second interaction ack window.
        await interaction.response.defer()
        embed, card, view = await self._open_loot(interaction.guild_id, interaction.user)
        kwargs = {"embed": embed}
        if card:
            kwargs["file"] = card
        if view:
            kwargs["view"] = view
        sent = await interaction.followup.send(**kwargs)
        if view:
            view.message = sent


async def setup(bot):
    await bot.add_cog(LootDrop(bot))
