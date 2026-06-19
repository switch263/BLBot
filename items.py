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
#   "command" — an explicit command (/lawyer plays a jail_card in a hearing,
#               /freespin for bonus_spin, /use to activate a heist_shield)
#   "passive" — fires automatically when relevant
# `price` is the shop cost in coins; buying destroys those coins (a sink).
# `max_owned` (optional) caps how many a player may hold at once — the shop
#   refuses a buy that would exceed it. Omit for no cap.
# `loot_weight` is the relative chance of this item on an item loot drop.
# `card_species` (optional) pins the loot-card art to a specific locked species
# slug in cogs/lootdrop_card.py; omit it to let the card use random art.
ITEMS = {
    JAIL_CARD: {
        "name": "Get Out of Jail Free",
        "emoji": "🃏",
        "price": 25_000_000,
        "max_owned": 3,
        "blurb": "Your lawyer plays it at your hearing for a near-certain win. Hire one with `/lawyer freecard` while jailed. One per day.",
        "flavor": "Signed by the warden. Notarized by nobody. Works 98% of the time.",
        "use": "command",
        "loot_weight": 10,
        "card_species": "get_out_of_jail",
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
        "price": 25_000_000,
        "max_owned": 3,
        "blurb": "Activate with `/use` to block ALL heists against you for the rest of the day. Not automatic — you must raise it.",
        "flavor": "A wall of pure paperwork. Thieves hate it.",
        "use": "command",
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
