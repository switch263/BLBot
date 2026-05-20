"""Item-card catalog — the single source of truth for the bot's buyable and
loot-droppable items.

economy.py stores inventory by the string keys below; this module owns
everything human-facing (names, prices, flavor) plus the loot-drop weights.
Imported by cogs/shop.py, cogs/slots.py, cogs/heist.py, cogs/lootdrop.py and
cogs/lootdrop_card.py. It's a pure data module — no Discord, no DB.
"""

# --- Item keys -------------------------------------------------------------
# These strings are the `item` column in economy's `inventory` table. Never
# rename one without a migration — existing inventories are keyed on them.
JAIL_CARD = "jail_card"
BONUS_SPIN = "bonus_spin"
HEIST_SHIELD = "heist_shield"

# Catalog. `use` is how a player triggers the item:
#   "command" — an explicit command (/use for jail_card,
#               /freespin for bonus_spin)
#   "passive" — fires automatically when relevant (heist_shield on a heist)
# `price` is the shop cost in coins; buying destroys those coins (a sink).
# `loot_weight` is the relative chance of this item on an item loot drop.
ITEMS = {
    JAIL_CARD: {
        "name": "Get Out of Jail Free",
        "emoji": "🃏",
        "price": 5_000_000,
        "blurb": "Instantly tears up your own jail sentence.",
        "flavor": "Signed by the warden. Notarized by nobody. Works anyway.",
        "use": "command",
        "loot_weight": 10,
    },
    BONUS_SPIN: {
        "name": "Bonus Spin",
        "emoji": "🎰",
        "price": 40_000,
        "blurb": "One free slots spin — keep the winnings, risk nothing. Use `/freespin`.",
        "flavor": "The house is feeling generous. Don't get used to it.",
        "use": "command",
        "loot_weight": 50,
    },
    HEIST_SHIELD: {
        "name": "Heist Shield",
        "emoji": "🛡️",
        "price": 3_000_000,
        "blurb": "Automatically blocks the next heist that targets you.",
        "flavor": "A wall of pure paperwork. Thieves hate it.",
        "use": "passive",
        "loot_weight": 15,
    },
}

ALL_ITEMS = tuple(ITEMS.keys())


def item_meta(key: str) -> dict | None:
    """Catalog entry for an item key, or None if the key is unknown."""
    return ITEMS.get(key)


def display(key: str) -> str:
    """'<emoji> <name>' for an item key; falls back to the raw key."""
    m = ITEMS.get(key)
    return f"{m['emoji']} {m['name']}" if m else key


def resolve(text: str) -> str | None:
    """Best-effort match of free-text input to an item key. Accepts the exact
    key, the display name, or a unique case-insensitive substring of either.
    Returns the key, or None if nothing (or more than one thing) matches."""
    if not text:
        return None
    t = text.strip().lower()
    if t in ITEMS:
        return t
    hits = [
        key for key, m in ITEMS.items()
        if t == m["name"].lower() or t in m["name"].lower() or t in key
    ]
    return hits[0] if len(hits) == 1 else None
