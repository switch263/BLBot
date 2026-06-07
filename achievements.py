"""Achievement catalog — pure data, the single source of truth for what can be
earned and what it's worth.

cogs/achievements.py builds a stats `ctx` for a player and evaluates each
entry's `cond(ctx)`. Newly-satisfied achievements are claimed once (idempotent)
and pay their `reward` from the house. No Discord, no DB here.

The `ctx` dict passed to every `cond` has:
    balance, total_won, total_lost, spins, jackpots   (wallet aggregates)
    games        -> {game_name: {"plays": int, "wins": int}}
    total_plays, total_wins, distinct_games            (derived)
    items_owned  -> distinct item count
    rank         -> 1-based coin leaderboard position (0 if unranked)

Tiers fix the point/reward scale so the table stays balanced as it grows.
"""

# Tier → (points, coin reward). Rewards are paid by the house via casino_payout.
BRONZE = (10, 10_000)
SILVER = (25, 50_000)
GOLD = (50, 250_000)
LEGENDARY = (100, 1_000_000)


def _g(ctx, game, field):
    return ctx["games"].get(game, {}).get(field, 0)


# Each entry: id -> dict(name, emoji, desc, tier, cond). Order here is the
# display order in /achievements.
ACHIEVEMENTS = {
    # --- Wealth ---------------------------------------------------------
    "high_roller": {
        "name": "High Roller", "emoji": "💵", "tier": SILVER,
        "desc": "Hold 1,000,000 coins at once.",
        "cond": lambda c: c["balance"] >= 1_000_000,
    },
    "tycoon": {
        "name": "Tycoon", "emoji": "🏦", "tier": GOLD,
        "desc": "Hold 10,000,000 coins at once.",
        "cond": lambda c: c["balance"] >= 10_000_000,
    },
    "made_man": {
        "name": "Made Man", "emoji": "💰", "tier": SILVER,
        "desc": "Win 1,000,000 coins all-time.",
        "cond": lambda c: c["total_won"] >= 1_000_000,
    },
    "high_finance": {
        "name": "High Finance", "emoji": "📈", "tier": GOLD,
        "desc": "Win 10,000,000 coins all-time.",
        "cond": lambda c: c["total_won"] >= 10_000_000,
    },
    "top_dog": {
        "name": "Top Dog", "emoji": "👑", "tier": LEGENDARY,
        "desc": "Reach #1 on the coin leaderboard.",
        "cond": lambda c: c["rank"] == 1,
    },
    # --- Slots / jackpots ----------------------------------------------
    "lucky": {
        "name": "Beginner's Luck", "emoji": "🍀", "tier": BRONZE,
        "desc": "Hit a slots jackpot.",
        "cond": lambda c: c["jackpots"] >= 1,
    },
    "jackpot_junkie": {
        "name": "Jackpot Junkie", "emoji": "🎰", "tier": GOLD,
        "desc": "Hit 10 slots jackpots.",
        "cond": lambda c: c["jackpots"] >= 10,
    },
    "spinaholic": {
        "name": "Spinaholic", "emoji": "🌀", "tier": SILVER,
        "desc": "Spin the slots 250 times.",
        "cond": lambda c: c["spins"] >= 250,
    },
    # --- Game mastery ---------------------------------------------------
    "vault_cracker": {
        "name": "Safecracker", "emoji": "🔓", "tier": SILVER,
        "desc": "Crack 10 vaults.",
        "cond": lambda c: _g(c, "vault", "wins") >= 10,
    },
    "vault_master": {
        "name": "Master Safecracker", "emoji": "🗝️", "tier": GOLD,
        "desc": "Crack 50 vaults.",
        "cond": lambda c: _g(c, "vault", "wins") >= 50,
    },
    "hardcore": {
        "name": "Hardcore", "emoji": "🧨", "tier": GOLD,
        "desc": "Beat the hard vault 5 times.",
        "cond": lambda c: _g(c, "vault_hard", "wins") >= 5,
    },
    "card_shark": {
        "name": "Card Shark", "emoji": "🃏", "tier": SILVER,
        "desc": "Win 25 hands of blackjack.",
        "cond": lambda c: _g(c, "blackjack", "wins") >= 25,
    },
    "wheel_watcher": {
        "name": "Wheel Watcher", "emoji": "🔴", "tier": BRONZE,
        "desc": "Play roulette 50 times.",
        "cond": lambda c: _g(c, "roulette", "plays") >= 50,
    },
    "hot_streak": {
        "name": "Hot Streak", "emoji": "🔥", "tier": SILVER,
        "desc": "Win 20 rounds of Higher/Lower.",
        "cond": lambda c: _g(c, "highlow", "wins") >= 20,
    },
    "master_thief": {
        "name": "Master Thief", "emoji": "🦹", "tier": GOLD,
        "desc": "Pull off 10 successful heists.",
        "cond": lambda c: _g(c, "heist", "wins") >= 10,
    },
    "den_diver": {
        "name": "Den Diver", "emoji": "🦝", "tier": SILVER,
        "desc": "Win the raccoon den 15 times.",
        "cond": lambda c: _g(c, "den", "wins") >= 15,
    },
    "survivor": {
        "name": "Survivor", "emoji": "🔫", "tier": SILVER,
        "desc": "Win a round of Russian Roulette.",
        "cond": lambda c: _g(c, "rr", "wins") >= 1,
    },
    "pawn_king": {
        "name": "Pawn King", "emoji": "💍", "tier": SILVER,
        "desc": "Come out ahead at the pawn shop 10 times.",
        "cond": lambda c: _g(c, "pawnshop", "wins") >= 10,
    },
    # --- Jail / jailbreak ----------------------------------------------
    "escape_artist": {
        "name": "Escape Artist", "emoji": "🕳️", "tier": SILVER,
        "desc": "Break out of jail with /jailbreak.",
        "cond": lambda c: _g(c, "jailbreak", "wins") >= 1,
    },
    "houdini": {
        "name": "Houdini", "emoji": "🎩", "tier": GOLD,
        "desc": "Break out of jail 5 times.",
        "cond": lambda c: _g(c, "jailbreak", "wins") >= 5,
    },
    # --- Lottery --------------------------------------------------------
    "ticket_taker": {
        "name": "Ticket Taker", "emoji": "🎟️", "tier": BRONZE,
        "desc": "Buy 10 lottery tickets.",
        "cond": lambda c: _g(c, "lottery", "plays") >= 10,
    },
    "scratch_addict": {
        "name": "Scratch Addict", "emoji": "🎫", "tier": SILVER,
        "desc": "Buy 50 lottery tickets.",
        "cond": lambda c: _g(c, "lottery", "plays") >= 50,
    },
    # --- Volume / breadth ----------------------------------------------
    "degenerate": {
        "name": "Degenerate", "emoji": "🎲", "tier": BRONZE,
        "desc": "Play 100 games.",
        "cond": lambda c: c["total_plays"] >= 100,
    },
    "no_life": {
        "name": "No Life", "emoji": "💀", "tier": GOLD,
        "desc": "Play 1,000 games.",
        "cond": lambda c: c["total_plays"] >= 1_000,
    },
    "jack_of_all": {
        "name": "Jack of All Trades", "emoji": "🃟", "tier": SILVER,
        "desc": "Play 8 different games.",
        "cond": lambda c: c["distinct_games"] >= 8,
    },
    # --- Items ----------------------------------------------------------
    "collector": {
        "name": "Collector", "emoji": "🎒", "tier": SILVER,
        "desc": "Hold all 3 item types at once.",
        "cond": lambda c: c["items_owned"] >= 3,
    },
}

ALL_ACHIEVEMENTS = tuple(ACHIEVEMENTS.keys())

TOTAL_POINTS = sum(a["tier"][0] for a in ACHIEVEMENTS.values())


def points(ach_id: str) -> int:
    a = ACHIEVEMENTS.get(ach_id)
    return a["tier"][0] if a else 0


def reward(ach_id: str) -> int:
    a = ACHIEVEMENTS.get(ach_id)
    return a["tier"][1] if a else 0
