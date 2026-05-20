"""Shared economy database utilities. All economy cogs import from here."""

import sqlite3
import os
import logging
from config import DATA_DIR

logger = logging.getLogger(__name__)

DB_FILE = os.path.join(DATA_DIR, "economy.db")
STARTING_COINS = 100

# Hard ceiling on a single stake, enforced by every game via check_bet().
# One bet can never move more than this — keeps a whale from blowing up the
# house (or another player) in one roll.
MAX_BET = 100_000


def check_bet(bet: int) -> str | None:
    """Validate a player's stake before collecting it. Returns a user-facing
    error string if the bet is non-positive or exceeds MAX_BET, else None.
    Call at the top of every game's bet flow, before transfer_to_house /
    deduct, e.g.:

        err = check_bet(bet)
        if err:
            await reply(err)
            return
    """
    if bet <= 0:
        return "Bet must be greater than 0."
    if bet > MAX_BET:
        return f"Max bet is **{MAX_BET:,}** coins."
    return None


# --- Memorial player ------------------------------------------------------
# kev2tall is an opt-out, exempt player — a member who has passed away. He is
# never jailed and never involved in a heist. As a standing offering, 1.5% of
# every game win and loss is tithed to his wallet, always paid by the house:
# _memorial_house_tithe runs inside transfer_to_house / casino_payout for
# games that route through the house wallet; memorial_tithe is the standalone
# version for games that settle elsewhere (slots, coinflip, roulette, PvP).
MEMORIAL_USER_ID = 361219124979826698  # kev2tall
MEMORIAL_TITHE_PCT = 0.015  # 1.5%


def is_memorial(user_id: int) -> bool:
    """True if user_id is the memorial player (kev2tall)."""
    return user_id == MEMORIAL_USER_ID

# The bot itself is the house. Its Discord user ID is set via set_house_id() on startup.
# Until that happens, fall back to legacy id 0 so older data still resolves.
_LEGACY_HOUSE_ID = 0
_house_id = _LEGACY_HOUSE_ID


def get_house_id() -> int:
    """Return the current house wallet user_id (the bot's ID once set)."""
    return _house_id


def set_house_id(new_id: int):
    """Register the bot's user_id as the house. Migrates any legacy id=0 balances over."""
    global _house_id
    if new_id == _house_id:
        return
    old_id = _house_id
    try:
        with sqlite3.connect(DB_FILE) as conn:
            rows = conn.execute(
                "SELECT guild_id, coins FROM wallets WHERE user_id = ? AND coins != 0",
                (old_id,),
            ).fetchall()
            for guild_id, coins in rows:
                conn.execute(
                    "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, 0)",
                    (guild_id, new_id),
                )
                conn.execute(
                    "UPDATE wallets SET coins = coins + ? WHERE guild_id = ? AND user_id = ?",
                    (coins, guild_id, new_id),
                )
            conn.execute(
                "DELETE FROM wallets WHERE user_id = ?",
                (old_id,),
            )
            conn.commit()
            if rows:
                logger.info(
                    f"Migrated house pot from legacy id {old_id} to {new_id} "
                    f"across {len(rows)} guild(s)."
                )
    except sqlite3.Error as e:
        logger.error(f"Database error migrating house pot: {e}")
    _house_id = new_id


# Maps each canonical game name to its (plays_column, wins_column) on the
# legacy `wallets` table. Used only for the one-shot backfill into game_stats.
_LEGACY_GAME_COLUMNS = {
    "roulette": ("roulette_plays", "roulette_wins"),
    "rr": ("rr_plays", "rr_wins"),
    "heist": ("heists_attempted", "heists_succeeded"),
    "den": ("den_plays", "den_wins"),
    "vault": ("vault_plays", "vault_wins"),
    "vault_hard": ("vault_hard_plays", "vault_hard_wins"),
    "blackjack": ("blackjack_plays", "blackjack_wins"),
    "highlow": ("highlow_plays", "highlow_wins"),
    "pawnshop": ("pawnshop_plays", "pawnshop_wins"),
}


def _backfill_game_stats(conn: sqlite3.Connection):
    """One-shot migration: copy per-game counters from `wallets` into `game_stats`.
    Skips columns that don't exist on a fresh DB (caught via OperationalError)."""
    select_cols = ["guild_id", "user_id"]
    game_order = []
    for game, (plays_col, wins_col) in _LEGACY_GAME_COLUMNS.items():
        select_cols.append(plays_col)
        select_cols.append(wins_col)
        game_order.append(game)
    try:
        rows = conn.execute(f"SELECT {', '.join(select_cols)} FROM wallets").fetchall()
    except sqlite3.OperationalError:
        return  # Fresh DB without the legacy columns — nothing to backfill.
    inserted = 0
    for row in rows:
        guild_id, user_id = row[0], row[1]
        offset = 2
        for game in game_order:
            plays = row[offset] or 0
            wins = row[offset + 1] or 0
            offset += 2
            if plays == 0 and wins == 0:
                continue
            conn.execute(
                "INSERT OR REPLACE INTO game_stats (guild_id, user_id, game, plays, wins) "
                "VALUES (?, ?, ?, ?, ?)",
                (guild_id, user_id, game, plays, wins),
            )
            inserted += 1
    if inserted:
        logger.info(f"Backfilled {inserted} game_stats rows from legacy wallet columns.")


def _init_db():
    """Create tables if they don't exist."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS wallets (
                    guild_id INTEGER,
                    user_id INTEGER,
                    coins INTEGER DEFAULT 100,
                    total_won INTEGER DEFAULT 0,
                    total_lost INTEGER DEFAULT 0,
                    spins INTEGER DEFAULT 0,
                    jackpots INTEGER DEFAULT 0,
                    last_daily TEXT DEFAULT '',
                    roulette_plays INTEGER DEFAULT 0,
                    roulette_wins INTEGER DEFAULT 0,
                    rr_plays INTEGER DEFAULT 0,
                    rr_wins INTEGER DEFAULT 0,
                    heists_attempted INTEGER DEFAULT 0,
                    heists_succeeded INTEGER DEFAULT 0,
                    den_plays INTEGER DEFAULT 0,
                    den_wins INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS loot_cooldowns (
                    guild_id INTEGER,
                    user_id INTEGER,
                    last_loot TEXT DEFAULT '',
                    last_loot_am TEXT DEFAULT '',
                    last_loot_pm TEXT DEFAULT '',
                    PRIMARY KEY (guild_id, user_id)
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS jail (
                    guild_id INTEGER,
                    user_id INTEGER,
                    until_ts REAL NOT NULL,
                    reason TEXT DEFAULT '',
                    bail_amount INTEGER DEFAULT 0,
                    channel_id INTEGER DEFAULT 0,
                    jailed_at REAL DEFAULT 0,
                    extended_seconds INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                )
            ''')
            # bounty_log: append-only log of bounty placements, used to enforce
            # a rolling guild-wide rate limit.
            conn.execute('''
                CREATE TABLE IF NOT EXISTS bounty_log (
                    guild_id INTEGER NOT NULL,
                    placer_user_id INTEGER NOT NULL,
                    target_user_id INTEGER NOT NULL,
                    bet INTEGER NOT NULL,
                    ts REAL NOT NULL
                )
            ''')
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_bounty_log_guild_ts ON bounty_log (guild_id, ts)"
            )
            # game_stats: per-game play/win counts. Replaces the per-game columns
            # on `wallets` (which are now deprecated but kept for backfill safety).
            conn.execute('''
                CREATE TABLE IF NOT EXISTS game_stats (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    game TEXT NOT NULL,
                    plays INTEGER NOT NULL DEFAULT 0,
                    wins INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id, game)
                )
            ''')
            # house_reserve: the safe-harbor side of the house pot. The house
            # wallet's `coins` is the on-hand (heistable) bucket; this reserve is
            # untouchable by heist/jackpot drains and backstops casino_payout when
            # on-hand is short. Earns interest at HOUSE_INTEREST_APR, compounded
            # lazily on read.
            conn.execute('''
                CREATE TABLE IF NOT EXISTS house_reserve (
                    guild_id INTEGER PRIMARY KEY,
                    coins INTEGER NOT NULL DEFAULT 0,
                    last_interest_ts REAL NOT NULL DEFAULT 0
                )
            ''')
            # cog_kv: the generic per-(guild,user) key-value store. ONE table
            # backs every bit of cog/feature state that isn't a core economy
            # concept — inventory, the Loaded Dice wager, future cooldowns and
            # flags. A cog stores under its own `namespace` via the kv_* /
            # feature helpers and never needs its own table or SQLite handle.
            # `value` is typed per-row (SQLite stores int/real/text as-is).
            # Guild-scoped (not per-user) state uses user_id = 0.
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cog_kv (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value,
                    PRIMARY KEY (guild_id, user_id, namespace, key)
                )
            ''')
            # Migrations: add columns if missing (safe on existing DBs)
            for col, decl in [
                ("last_daily", "TEXT DEFAULT ''"),
                ("roulette_plays", "INTEGER DEFAULT 0"),
                ("roulette_wins", "INTEGER DEFAULT 0"),
                ("rr_plays", "INTEGER DEFAULT 0"),
                ("rr_wins", "INTEGER DEFAULT 0"),
                ("heists_attempted", "INTEGER DEFAULT 0"),
                ("heists_succeeded", "INTEGER DEFAULT 0"),
                ("den_plays", "INTEGER DEFAULT 0"),
                ("den_wins", "INTEGER DEFAULT 0"),
                ("bot_heist_offenses", "INTEGER DEFAULT 0"),
                ("last_bail_received_ts", "REAL DEFAULT 0"),
                ("vault_plays", "INTEGER DEFAULT 0"),
                ("vault_wins", "INTEGER DEFAULT 0"),
                ("vault_hard_plays", "INTEGER DEFAULT 0"),
                ("vault_hard_wins", "INTEGER DEFAULT 0"),
                ("blackjack_plays", "INTEGER DEFAULT 0"),
                ("blackjack_wins", "INTEGER DEFAULT 0"),
                ("highlow_plays", "INTEGER DEFAULT 0"),
                ("highlow_wins", "INTEGER DEFAULT 0"),
                ("pawnshop_plays", "INTEGER DEFAULT 0"),
                ("pawnshop_wins", "INTEGER DEFAULT 0"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE wallets ADD COLUMN {col} {decl}")
                except sqlite3.OperationalError:
                    pass
            # jail: add bail/release-tracking columns for existing rows.
            for col, decl in [
                ("bail_amount", "INTEGER DEFAULT 0"),
                ("channel_id", "INTEGER DEFAULT 0"),
                ("jailed_at", "REAL DEFAULT 0"),
                ("extended_seconds", "INTEGER DEFAULT 0"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE jail ADD COLUMN {col} {decl}")
                except sqlite3.OperationalError:
                    pass
            # loot_cooldowns: split single daily into AM/PM slots. On first
            # migration, copy legacy last_loot into last_loot_am so existing
            # users don't get a free extra AM claim on rollout day.
            for col, decl in [
                ("last_loot_am", "TEXT DEFAULT ''"),
                ("last_loot_pm", "TEXT DEFAULT ''"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE loot_cooldowns ADD COLUMN {col} {decl}")
                    if col == "last_loot_am":
                        conn.execute(
                            "UPDATE loot_cooldowns SET last_loot_am = last_loot "
                            "WHERE last_loot != ''"
                        )
                except sqlite3.OperationalError:
                    pass
            # Schema version. Bump when introducing a one-shot migration.
            #   1 = backfill `game_stats` from per-game wallet columns.
            current_version = conn.execute("PRAGMA user_version").fetchone()[0]
            if current_version < 1:
                _backfill_game_stats(conn)
                conn.execute("PRAGMA user_version = 1")
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error initializing economy: {e}")


_EMPTY_WALLET = {
    "coins": 0, "total_won": 0, "total_lost": 0, "spins": 0, "jackpots": 0,
}


def get_wallet(guild_id: int, user_id: int) -> dict:
    """Get or create a wallet. Returns dict with balance and global stats only.
    Per-game stats live in `game_stats` — use `get_game_stats()` for those."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, ?)",
                (guild_id, user_id, STARTING_COINS)
            )
            conn.commit()
            cursor = conn.execute(
                "SELECT coins, total_won, total_lost, spins, jackpots "
                "FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            )
            row = cursor.fetchone()
            return {
                "coins": row[0], "total_won": row[1], "total_lost": row[2],
                "spins": row[3], "jackpots": row[4],
            }
    except sqlite3.Error as e:
        logger.error(f"Database error getting wallet: {e}")
        return dict(_EMPTY_WALLET)


def record_game(guild_id: int, user_id: int, game: str, won: bool):
    """Upsert a play (and optional win) into game_stats. Replaces the per-game record_* shims."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                "INSERT INTO game_stats (guild_id, user_id, game, plays, wins) "
                "VALUES (?, ?, ?, 1, ?) "
                "ON CONFLICT(guild_id, user_id, game) DO UPDATE SET "
                "plays = plays + 1, wins = wins + excluded.wins",
                (guild_id, user_id, game, 1 if won else 0),
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error recording game play ({game}): {e}")


def get_game_stats(guild_id: int, user_id: int) -> dict[str, dict[str, int]]:
    """Return {game: {'plays': X, 'wins': Y}} for every game this user has played.
    Games the user has never played are absent — callers should default to (0, 0)."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            rows = conn.execute(
                "SELECT game, plays, wins FROM game_stats "
                "WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchall()
            return {game: {"plays": plays, "wins": wins} for game, plays, wins in rows}
    except sqlite3.Error as e:
        logger.error(f"Database error reading game stats: {e}")
        return {}


def get_coins(guild_id: int, user_id: int) -> int:
    """Get coin balance for a user, creating wallet if needed.
    For the house, this returns ON-HAND only (post-normalize) — the safe-harbor
    reserve is not exposed here. Use get_house_state() for the full breakdown."""
    if user_id == get_house_id():
        return get_house_state(guild_id)["on_hand"]
    return get_wallet(guild_id, user_id)["coins"]


def update_wallet(guild_id: int, user_id: int, delta: int, is_jackpot: bool = False):
    """Update wallet after a game. Positive delta = winnings, negative = loss. Increments spins."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            if delta > 0:
                conn.execute(
                    "UPDATE wallets SET coins = coins + ?, total_won = total_won + ?, spins = spins + 1, jackpots = jackpots + ? WHERE guild_id = ? AND user_id = ?",
                    (delta, delta, 1 if is_jackpot else 0, guild_id, user_id)
                )
            else:
                conn.execute(
                    "UPDATE wallets SET coins = coins + ?, total_lost = total_lost + ?, spins = spins + 1 WHERE guild_id = ? AND user_id = ?",
                    (delta, abs(delta), guild_id, user_id)
                )
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error updating wallet: {e}")


def add_coins(guild_id: int, user_id: int, amount: int):
    """Add coins without incrementing spins (for loot, daily, etc)."""
    get_wallet(guild_id, user_id)  # ensure exists
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                "UPDATE wallets SET coins = coins + ?, total_won = total_won + ? WHERE guild_id = ? AND user_id = ?",
                (amount, amount, guild_id, user_id)
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error adding coins: {e}")


def deduct_coins(guild_id: int, user_id: int, amount: int):
    """Deduct coins without incrementing spins."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                "UPDATE wallets SET coins = coins - ?, total_lost = total_lost + ? WHERE guild_id = ? AND user_id = ?",
                (amount, amount, guild_id, user_id)
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error deducting coins: {e}")


def fine_user(guild_id: int, user_id: int, amount: int):
    """Fine a user (coins can't go below 0)."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                "UPDATE wallets SET coins = MAX(0, coins - ?) WHERE guild_id = ? AND user_id = ?",
                (amount, guild_id, user_id)
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error fining user: {e}")


def transfer_coins(guild_id: int, from_id: int, to_id: int, amount: int) -> dict:
    """Atomically transfer coins between users (BEGIN IMMEDIATE + balance check).

    Returns a dict:
      {"ok": True, "sender_balance": X, "receiver_balance": Y}
      {"ok": False, "error": "invalid_amount"}
      {"ok": False, "error": "broke", "have": X, "need": amount}
      {"ok": False, "error": "db"}
    Sender/receiver wallets are created in-transaction if missing.
    """
    if amount <= 0:
        return {"ok": False, "error": "invalid_amount"}
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, ?)",
                (guild_id, from_id, STARTING_COINS),
            )
            conn.execute(
                "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, ?)",
                (guild_id, to_id, STARTING_COINS),
            )
            sender_row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, from_id),
            ).fetchone()
            sender_coins = sender_row[0] if sender_row else 0
            if sender_coins < amount:
                conn.rollback()
                return {"ok": False, "error": "broke", "have": sender_coins, "need": amount}
            conn.execute(
                "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
                (amount, guild_id, from_id),
            )
            conn.execute(
                "UPDATE wallets SET coins = coins + ? WHERE guild_id = ? AND user_id = ?",
                (amount, guild_id, to_id),
            )
            sender_balance = sender_coins - amount
            recv_row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, to_id),
            ).fetchone()
            receiver_balance = recv_row[0] if recv_row else 0
            conn.commit()
            return {
                "ok": True,
                "sender_balance": sender_balance,
                "receiver_balance": receiver_balance,
            }
    except sqlite3.Error as e:
        logger.error(f"Database error transferring coins: {e}")
        return {"ok": False, "error": "db"}


def try_deduct(guild_id: int, user_id: int, amount: int) -> bool:
    """Atomically deduct `amount` only if the wallet has enough. Returns True on success.

    Use this in cogs to take a bet; it closes the TOCTOU window between a balance
    check and the actual deduction. Wallet is created in-transaction if missing.
    """
    if amount <= 0:
        return False
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, ?)",
                (guild_id, user_id, STARTING_COINS),
            )
            cursor = conn.execute(
                "UPDATE wallets SET coins = coins - ?, total_lost = total_lost + ? "
                "WHERE guild_id = ? AND user_id = ? AND coins >= ?",
                (amount, amount, guild_id, user_id, amount),
            )
            if cursor.rowcount == 0:
                conn.rollback()
                return False
            conn.commit()
            return True
    except sqlite3.Error as e:
        logger.error(f"Database error in try_deduct: {e}")
        return False


# --- House liquidity / safe-harbor reserve --------------------------------
# The house has two buckets:
#   on-hand: the house's `coins` in `wallets`. This is what's heistable and
#            what green-roulette can claim. Uncapped — it holds every bet.
#   reserve: `house_reserve.coins`. Untouchable by heist/jackpot drains. Earns
#            interest at HOUSE_INTEREST_APR, compounded lazily on read.
#            casino_payout will top on-hand up from the reserve when on-hand
#            is insufficient — so the bank can't go bankrupt on a single big
#            bet while the investment account still has cash.
# Annualized rate, compounded continuously on read. 0.001 = 0.1% APR.
# Stays scale-invariant: doesn't matter if you read every second or once a month,
# the effective growth equals the APR exactly.
HOUSE_INTEREST_APR = 0.001
_SECONDS_PER_YEAR = 365.25 * 24 * 3600

# Per-event drain caps as random ranges. A successful event rolls uniform(min, max)
# and takes that fraction of on-hand. Living here (not in their cogs) so /pot can
# read the ranges without a cross-cog import and so any future "casino policy"
# tuning happens in one file.
HOUSE_HEIST_MIN_PCT = 0.15
HOUSE_HEIST_MAX_PCT = 0.90
GREEN_JACKPOT_MIN_PCT = 0.75
GREEN_JACKPOT_MAX_PCT = 0.90

# Starting balance seeded into the house's safe-harbor RESERVE on first
# touch (and after any clear_economy wipe). It lives in the reserve — not
# on-hand — so it can't be drained by a heist or a green-jackpot roll; it
# can only ever leave the house via casino_payout's reserve fallback when
# on-hand is short. That's the "can't bankrupt the bot on the first bet"
# guarantee.
HOUSE_STARTING_COINS = 100_000_000


def _ensure_house_wallet(conn: sqlite3.Connection, guild_id: int):
    """Idempotent: create the house's wallet row (on-hand starts at 0) and
    seed the safe-harbor reserve with HOUSE_STARTING_COINS. INSERT OR IGNORE
    on both, so this is a no-op once either row exists — safe to call from
    every code path that touches the house."""
    conn.execute(
        "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, 0)",
        (guild_id, get_house_id()),
    )
    conn.execute(
        "INSERT OR IGNORE INTO house_reserve (guild_id, coins, last_interest_ts) "
        "VALUES (?, ?, 0)",
        (guild_id, HOUSE_STARTING_COINS),
    )


def _normalize_house(conn: sqlite3.Connection, guild_id: int):
    """Apply accrued interest to the safe-harbor reserve. Idempotent. Caller is
    expected to be holding BEGIN IMMEDIATE so the read-modify-write is atomic."""
    import time as _t
    now = _t.time()
    conn.execute(
        "INSERT OR IGNORE INTO house_reserve (guild_id, coins, last_interest_ts) "
        "VALUES (?, ?, ?)",
        (guild_id, HOUSE_STARTING_COINS, now),
    )
    row = conn.execute(
        "SELECT coins, last_interest_ts FROM house_reserve WHERE guild_id = ?",
        (guild_id,),
    ).fetchone()
    reserve_coins = row[0] or 0
    last_ts = row[1] or 0
    # Compound interest on any existing reserve. APR-based: elapsed seconds
    # are converted to fractional years and the growth factor is (1+APR)^years.
    # This stays invariant to read frequency — same end balance whether read once
    # per year or 1000 times per day.
    if reserve_coins > 0 and last_ts > 0 and now > last_ts:
        elapsed_years = (now - last_ts) / _SECONDS_PER_YEAR
        reserve_coins = int(reserve_coins * ((1.0 + HOUSE_INTEREST_APR) ** elapsed_years))
    conn.execute(
        "UPDATE house_reserve SET coins = ?, last_interest_ts = ? WHERE guild_id = ?",
        (reserve_coins, now, guild_id),
    )


def _memorial_house_tithe(conn: sqlite3.Connection, guild_id: int, amount: int) -> int:
    """Within an open transaction, move MEMORIAL_TITHE_PCT of `amount` from the
    house's on-hand wallet to the memorial player (kev2tall). Best-effort —
    tithes only what the house can cover. Returns the coins tithed.

    Used by transfer_to_house (the loss side) and casino_payout (the win side)
    so the house funds the offering and players are never shortchanged."""
    tithe = int(amount * MEMORIAL_TITHE_PCT)
    if tithe <= 0:
        return 0
    house_id = get_house_id()
    house_row = conn.execute(
        "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
        (guild_id, house_id),
    ).fetchone()
    house_coins = house_row[0] if house_row else 0
    pay = min(tithe, max(0, house_coins))
    if pay <= 0:
        return 0
    conn.execute(
        "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, 0)",
        (guild_id, MEMORIAL_USER_ID),
    )
    conn.execute(
        "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
        (pay, guild_id, house_id),
    )
    conn.execute(
        "UPDATE wallets SET coins = coins + ? WHERE guild_id = ? AND user_id = ?",
        (pay, guild_id, MEMORIAL_USER_ID),
    )
    return pay


def memorial_tithe(guild_id: int, amount: int) -> int:
    """Move MEMORIAL_TITHE_PCT of `amount` from the house to the memorial
    player (kev2tall). Standalone, atomic version of _memorial_house_tithe for
    games that settle outside transfer_to_house / casino_payout (slots,
    coinflip, roulette, cockroach, pigderby) — the house still funds the
    offering, it just wasn't otherwise a party to that game's money flow.
    Best-effort: tithes only what the house on-hand can cover. Call once per
    game outcome with the win or loss amount. Returns the coins tithed."""
    tithe = int(amount * MEMORIAL_TITHE_PCT)
    if tithe <= 0:
        return 0
    house_id = get_house_id()
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _ensure_house_wallet(conn, guild_id)
            pay = _memorial_house_tithe(conn, guild_id, amount)
            conn.commit()
            return pay
    except sqlite3.Error as e:
        logger.error(f"Database error in memorial_tithe: {e}")
        return 0


def transfer_to_house(guild_id: int, user_id: int, amount: int) -> dict:
    """Atomic transfer from a user to the house (donations, vig, bet collection).
    After the deposit, normalizes the house (applies interest to the reserve).

    Same return shape as transfer_coins. `receiver_balance` is the on-hand
    wallet, not the total house net worth."""
    if amount <= 0:
        return {"ok": False, "error": "invalid_amount"}
    house_id = get_house_id()
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, ?)",
                (guild_id, user_id, STARTING_COINS),
            )
            _ensure_house_wallet(conn, guild_id)
            sender_row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            sender_coins = sender_row[0] if sender_row else 0
            if sender_coins < amount:
                conn.rollback()
                return {"ok": False, "error": "broke", "have": sender_coins, "need": amount}
            conn.execute(
                "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
                (amount, guild_id, user_id),
            )
            conn.execute(
                "UPDATE wallets SET coins = coins + ? WHERE guild_id = ? AND user_id = ?",
                (amount, guild_id, house_id),
            )
            sender_balance = sender_coins - amount
            _normalize_house(conn, guild_id)
            # Memorial tithe (1.5% of the bet, the loss side) and the Loaded
            # Dice wager record — both skip the memorial player.
            if not is_memorial(user_id):
                _memorial_house_tithe(conn, guild_id, amount)
                _record_wager(conn, guild_id, user_id, amount)
            recv_row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, house_id),
            ).fetchone()
            receiver_balance = recv_row[0] if recv_row else 0
            conn.commit()
            return {
                "ok": True,
                "sender_balance": sender_balance,
                "receiver_balance": receiver_balance,
            }
    except sqlite3.Error as e:
        logger.error(f"Database error in transfer_to_house: {e}")
        return {"ok": False, "error": "db"}


def transfer_to_reserve(guild_id: int, user_id: int, amount: int) -> dict:
    """Atomic transfer from a player's wallet straight into the house's
    safe-harbor reserve — bypassing on-hand and the memorial tithe.

    Used by the kev2tall smite: seized coins go into the protected pot
    (untouchable by heist/jackpot drains, available only to backstop
    casino_payout). Balance-checked; broke senders get a `broke` error.

    Returns the standard transfer-style result dict:
      {"ok": True, "sender_balance": X}
      {"ok": False, "error": "broke", "have": X, "need": Y}
      {"ok": False, "error": "invalid_amount" | "db"}
    """
    if amount <= 0:
        return {"ok": False, "error": "invalid_amount"}
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, ?)",
                (guild_id, user_id, STARTING_COINS),
            )
            conn.execute(
                "INSERT OR IGNORE INTO house_reserve (guild_id, coins, last_interest_ts) "
                "VALUES (?, ?, 0)",
                (guild_id, HOUSE_STARTING_COINS),
            )
            row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            sender_coins = row[0] if row else 0
            if sender_coins < amount:
                conn.rollback()
                return {"ok": False, "error": "broke",
                        "have": sender_coins, "need": amount}
            conn.execute(
                "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
                (amount, guild_id, user_id),
            )
            conn.execute(
                "UPDATE house_reserve SET coins = coins + ? WHERE guild_id = ?",
                (amount, guild_id),
            )
            conn.commit()
            return {"ok": True, "sender_balance": sender_coins - amount}
    except sqlite3.Error as e:
        logger.error(f"Database error in transfer_to_reserve: {e}")
        return {"ok": False, "error": "db"}


def casino_payout(guild_id: int, user_id: int, amount: int) -> int:
    """Pay a casino win from the house to a player.

    Returns the actual coins paid (≤ amount). Atomic. Normalizes the house
    first (applies reserve interest). If on-hand is short, tops it up from
    the safe-harbor reserve by exactly what's needed for this payout — so a
    drained on-hand bucket doesn't silently shortchange a winner. The reserve
    is still invisible to heist/jackpot drains; only payouts can tap it.
    """
    if amount <= 0:
        return 0
    house_id = get_house_id()
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _ensure_house_wallet(conn, guild_id)
            conn.execute(
                "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, ?)",
                (guild_id, user_id, STARTING_COINS),
            )
            _normalize_house(conn, guild_id)
            house_row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, house_id),
            ).fetchone()
            house_coins = house_row[0] if house_row else 0
            shortfall = amount - house_coins
            if shortfall > 0:
                reserve_row = conn.execute(
                    "SELECT coins FROM house_reserve WHERE guild_id = ?",
                    (guild_id,),
                ).fetchone()
                reserve_coins = reserve_row[0] if reserve_row else 0
                topup = min(shortfall, max(0, reserve_coins))
                if topup > 0:
                    conn.execute(
                        "UPDATE house_reserve SET coins = coins - ? WHERE guild_id = ?",
                        (topup, guild_id),
                    )
                    conn.execute(
                        "UPDATE wallets SET coins = coins + ? WHERE guild_id = ? AND user_id = ?",
                        (topup, guild_id, house_id),
                    )
                    house_coins += topup
            pay = min(amount, max(0, house_coins))
            if pay <= 0:
                conn.rollback()
                return 0
            conn.execute(
                "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
                (pay, guild_id, house_id),
            )
            conn.execute(
                "UPDATE wallets SET coins = coins + ?, total_won = total_won + ? "
                "WHERE guild_id = ? AND user_id = ?",
                (pay, pay, guild_id, user_id),
            )
            # Memorial tithe (1.5% of the win, paid by the house on top — the
            # winner keeps 100% of `pay`) and the Loaded Dice settle: a payout
            # landed, so this round is no longer a refundable loss.
            if not is_memorial(user_id):
                _memorial_house_tithe(conn, guild_id, pay)
                _settle_wager(conn, guild_id, user_id)
            conn.commit()
            return pay
    except sqlite3.Error as e:
        logger.error(f"Database error in casino_payout: {e}")
        return 0


def get_house_state(guild_id: int) -> dict:
    """Snapshot of both house buckets. Applies reserve interest as a side
    effect. Returns {'on_hand': X, 'reserve': Y, 'apr': Z}."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _normalize_house(conn, guild_id)
            house_row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, get_house_id()),
            ).fetchone()
            reserve_row = conn.execute(
                "SELECT coins FROM house_reserve WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()
            conn.commit()
            return {
                "on_hand": (house_row[0] if house_row else 0),
                "reserve": (reserve_row[0] if reserve_row else 0),
                "apr": HOUSE_INTEREST_APR,
            }
    except sqlite3.Error as e:
        logger.error(f"Database error in get_house_state: {e}")
        return {"on_hand": 0, "reserve": 0, "apr": HOUSE_INTEREST_APR}


# --- Generic key-value store ----------------------------------------------
# One table (`cog_kv`) holds every bit of per-(guild,user) state that isn't a
# core economy concept: inventory, the Loaded Dice wager, and whatever future
# cogs need. A cog picks a `namespace` and stores under it — no new table, no
# SQLite handle of its own, no economy.py change. Removing a cog? Delete its
# file; its rows are harmless orphans, or wipe them with kv_clear_namespace.
# Guild-scoped (not per-user) state uses user_id = 0.

def kv_get(guild_id: int, user_id: int, namespace: str, key: str, default=None):
    """Read one value, or `default` if the key is unset."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            row = conn.execute(
                "SELECT value FROM cog_kv WHERE guild_id=? AND user_id=? AND namespace=? AND key=?",
                (guild_id, user_id, namespace, key),
            ).fetchone()
            return row[0] if row else default
    except sqlite3.Error as e:
        logger.error(f"Database error in kv_get: {e}")
        return default


def kv_set(guild_id: int, user_id: int, namespace: str, key: str, value):
    """Write one value (int, float or str), overwriting any previous value."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO cog_kv (guild_id, user_id, namespace, key, value) VALUES (?,?,?,?,?) "
                "ON CONFLICT(guild_id, user_id, namespace, key) DO UPDATE SET value=?",
                (guild_id, user_id, namespace, key, value, value),
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error in kv_set: {e}")


def kv_incr(guild_id: int, user_id: int, namespace: str, key: str, by: int = 1):
    """Atomically add `by` to a numeric value (an unset key counts as 0) and
    return the new total. `by` may be negative."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO cog_kv (guild_id, user_id, namespace, key, value) VALUES (?,?,?,?,?) "
                "ON CONFLICT(guild_id, user_id, namespace, key) DO UPDATE SET value = value + ?",
                (guild_id, user_id, namespace, key, by, by),
            )
            row = conn.execute(
                "SELECT value FROM cog_kv WHERE guild_id=? AND user_id=? AND namespace=? AND key=?",
                (guild_id, user_id, namespace, key),
            ).fetchone()
            conn.commit()
            return row[0] if row else by
    except sqlite3.Error as e:
        logger.error(f"Database error in kv_incr: {e}")
        return 0


def kv_delete(guild_id: int, user_id: int, namespace: str, key: str):
    """Delete one key."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "DELETE FROM cog_kv WHERE guild_id=? AND user_id=? AND namespace=? AND key=?",
                (guild_id, user_id, namespace, key),
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error in kv_delete: {e}")


def kv_get_all(guild_id: int, user_id: int, namespace: str) -> dict:
    """Every {key: value} a player holds in `namespace`."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            rows = conn.execute(
                "SELECT key, value FROM cog_kv WHERE guild_id=? AND user_id=? AND namespace=?",
                (guild_id, user_id, namespace),
            ).fetchall()
            return {k: v for k, v in rows}
    except sqlite3.Error as e:
        logger.error(f"Database error in kv_get_all: {e}")
        return {}


def kv_clear_namespace(guild_id: int, namespace: str):
    """Delete every row in a namespace for a guild — cleanup for when a cog is
    retired. economy.py itself is untouched."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "DELETE FROM cog_kv WHERE guild_id=? AND namespace=?",
                (guild_id, namespace),
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error in kv_clear_namespace: {e}")


# --- Inventory / shop items -----------------------------------------------
# Items (shop purchases, loot-drop cards) live in the cog_kv store under the
# "inventory" namespace, keyed item → qty. The catalog (names, prices, effects)
# is items.py; economy.py only moves the counts.
_INV_NS = "inventory"


def grant_item(guild_id: int, user_id: int, item: str, qty: int = 1):
    """Add `qty` of `item` to a player's inventory."""
    if qty <= 0:
        return
    kv_incr(guild_id, user_id, _INV_NS, item, qty)


def consume_item(guild_id: int, user_id: int, item: str, qty: int = 1) -> bool:
    """Atomically remove `qty` of `item` if the player holds at least that many.
    Returns True if consumed, False if they were short."""
    if qty <= 0:
        return False
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT value FROM cog_kv WHERE guild_id=? AND user_id=? AND namespace=? AND key=?",
                (guild_id, user_id, _INV_NS, item),
            ).fetchone()
            have = row[0] if row else 0
            if have < qty:
                conn.rollback()
                return False
            remaining = have - qty
            if remaining > 0:
                conn.execute(
                    "UPDATE cog_kv SET value=? WHERE guild_id=? AND user_id=? AND namespace=? AND key=?",
                    (remaining, guild_id, user_id, _INV_NS, item),
                )
            else:
                conn.execute(
                    "DELETE FROM cog_kv WHERE guild_id=? AND user_id=? AND namespace=? AND key=?",
                    (guild_id, user_id, _INV_NS, item),
                )
            conn.commit()
            return True
    except sqlite3.Error as e:
        logger.error(f"Database error in consume_item: {e}")
        return False


def item_qty(guild_id: int, user_id: int, item: str) -> int:
    """How many of `item` a player holds."""
    return int(kv_get(guild_id, user_id, _INV_NS, item, 0) or 0)


def get_inventory(guild_id: int, user_id: int) -> dict:
    """Returns {item: qty} for every item the player holds (qty > 0)."""
    return {k: v for k, v in kv_get_all(guild_id, user_id, _INV_NS).items() if v > 0}


def release_from_jail(guild_id: int, user_id: int) -> bool:
    """Clear a player's jail sentence — the Get Out of Jail Free card. Returns
    True if they were actually jailed (so the caller knows the card did work)."""
    import time as _t
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT until_ts FROM jail WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            jailed = bool(row and row[0] > _t.time())
            conn.execute(
                "DELETE FROM jail WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            conn.commit()
            return jailed
    except sqlite3.Error as e:
        logger.error(f"Database error in release_from_jail: {e}")
        return False


# --- Wager tracking (Loaded Dice mulligan) --------------------------------
# A player's most recent bet lives in cog_kv under the "wager" namespace as
# three keys — amount, ts, settled. `settled` flips to 1 once a payout lands;
# an unsettled, recent wager is a refundable loss.
_WAGER_NS = "wager"


def _record_wager(conn: sqlite3.Connection, guild_id: int, user_id: int, amount: int):
    """Within an open transaction: stamp this as the player's most recent,
    unsettled wager. Called from transfer_to_house; slots/coinflip use the
    standalone record_wager()."""
    import time as _t
    now = _t.time()
    for k, v in (("amount", amount), ("ts", now), ("settled", 0)):
        conn.execute(
            "INSERT INTO cog_kv (guild_id, user_id, namespace, key, value) VALUES (?,?,?,?,?) "
            "ON CONFLICT(guild_id, user_id, namespace, key) DO UPDATE SET value=?",
            (guild_id, user_id, _WAGER_NS, k, v, v),
        )


def _settle_wager(conn: sqlite3.Connection, guild_id: int, user_id: int):
    """Within an open transaction: mark the player's last wager settled — a
    payout landed, so it is no longer a refundable loss."""
    conn.execute(
        "UPDATE cog_kv SET value=1 WHERE guild_id=? AND user_id=? AND namespace=? AND key='settled'",
        (guild_id, user_id, _WAGER_NS),
    )


def record_wager(guild_id: int, user_id: int, amount: int):
    """Standalone wager record for games that settle outside transfer_to_house
    (slots, coinflip). Pair with settle_wager() on a win."""
    if amount <= 0:
        return
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _record_wager(conn, guild_id, user_id, amount)
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error in record_wager: {e}")


def settle_wager(guild_id: int, user_id: int):
    """Standalone wager settle (a win) for slots/coinflip. See _settle_wager."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _settle_wager(conn, guild_id, user_id)
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error in settle_wager: {e}")


def refund_last_loss(guild_id: int, user_id: int, max_age_seconds: int = 600) -> dict:
    """Loaded Dice mulligan: if the player has a recent, unsettled losing
    wager, refund it from the house and mark it settled (no double-claims).

    Returns:
      {"ok": True, "refunded": X}
      {"ok": False, "error": "no_loss"}      # nothing recent and unsettled
      {"ok": False, "error": "house_broke"}  # house can't cover the refund
      {"ok": False, "error": "db"}
    """
    import time as _t
    house_id = get_house_id()
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT key, value FROM cog_kv WHERE guild_id=? AND user_id=? AND namespace=?",
                (guild_id, user_id, _WAGER_NS),
            ).fetchall()
            w = {k: v for k, v in rows}
            amount = w.get("amount", 0)
            ts = w.get("ts", 0)
            settled = w.get("settled", 1)
            if settled or amount <= 0 or (_t.time() - ts) > max_age_seconds:
                conn.rollback()
                return {"ok": False, "error": "no_loss"}
            _ensure_house_wallet(conn, guild_id)
            conn.execute(
                "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, ?)",
                (guild_id, user_id, STARTING_COINS),
            )
            house_row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, house_id),
            ).fetchone()
            house_coins = house_row[0] if house_row else 0
            if house_coins < amount:
                conn.rollback()
                return {"ok": False, "error": "house_broke"}
            conn.execute(
                "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
                (amount, guild_id, house_id),
            )
            conn.execute(
                "UPDATE wallets SET coins = coins + ? WHERE guild_id = ? AND user_id = ?",
                (amount, guild_id, user_id),
            )
            conn.execute(
                "UPDATE cog_kv SET value=1 WHERE guild_id=? AND user_id=? AND namespace=? AND key='settled'",
                (guild_id, user_id, _WAGER_NS),
            )
            conn.commit()
            return {"ok": True, "refunded": amount}
    except sqlite3.Error as e:
        logger.error(f"Database error in refund_last_loss: {e}")
        return {"ok": False, "error": "db"}


def disburse(guild_id: int, from_id: int, payments: list[tuple[int, int]]) -> dict:
    """Atomically transfer from `from_id` to many recipients in one transaction.

    `payments` is a list of (recipient_user_id, amount) pairs. Total is debited once
    from the sender. Either all payments go through or none do.

    Returns:
      {"ok": True, "sender_balance": X, "total": T}
      {"ok": False, "error": "invalid_amount"}  # any non-positive share, or empty list
      {"ok": False, "error": "broke", "have": X, "need": T}
      {"ok": False, "error": "db"}
    """
    if not payments or any(amt <= 0 for _, amt in payments):
        return {"ok": False, "error": "invalid_amount"}
    total = sum(amt for _, amt in payments)
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, ?)",
                (guild_id, from_id, STARTING_COINS),
            )
            sender_row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, from_id),
            ).fetchone()
            sender_coins = sender_row[0] if sender_row else 0
            if sender_coins < total:
                conn.rollback()
                return {"ok": False, "error": "broke", "have": sender_coins, "need": total}
            conn.execute(
                "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
                (total, guild_id, from_id),
            )
            for recipient_id, amt in payments:
                conn.execute(
                    "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, ?)",
                    (guild_id, recipient_id, STARTING_COINS),
                )
                conn.execute(
                    "UPDATE wallets SET coins = coins + ?, total_won = total_won + ? "
                    "WHERE guild_id = ? AND user_id = ?",
                    (amt, amt, guild_id, recipient_id),
                )
            conn.commit()
            return {"ok": True, "sender_balance": sender_coins - total, "total": total}
    except sqlite3.Error as e:
        logger.error(f"Database error in disburse: {e}")
        return {"ok": False, "error": "db"}


def award_coins(guild_id: int, user_id: int, amount: int):
    """Award coins and track as winnings without incrementing spins."""
    get_wallet(guild_id, user_id)  # ensure exists
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                "UPDATE wallets SET coins = coins + ?, total_won = total_won + ? WHERE guild_id = ? AND user_id = ?",
                (amount, amount, guild_id, user_id)
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error awarding coins: {e}")


def get_leaderboard(guild_id: int, limit: int = 10) -> list:
    """Get top players by coins. Excludes the house (bot) wallet."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.execute(
                "SELECT user_id, coins, total_won, total_lost, spins, jackpots "
                "FROM wallets WHERE guild_id = ? AND user_id != ? "
                "ORDER BY coins DESC LIMIT ?",
                (guild_id, get_house_id(), limit)
            )
            return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Database error getting leaderboard: {e}")
        return []


def get_total_economy(guild_id: int) -> int:
    """Sum of all coins across the guild — every player wallet, the house on-hand,
    AND the house safe-harbor reserve. The reserve is real money even though it
    isn't heistable, so it counts toward total circulation."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            wallets_total = conn.execute(
                "SELECT COALESCE(SUM(coins), 0) FROM wallets WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()[0] or 0
            reserve_row = conn.execute(
                "SELECT coins FROM house_reserve WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()
            reserve_total = (reserve_row[0] if reserve_row else 0) or 0
            return int(wallets_total) + int(reserve_total)
    except sqlite3.Error as e:
        logger.error(f"Database error reading total economy: {e}")
        return 0


def get_server_stats(guild_id: int) -> dict:
    """Get aggregate economy stats for a server. Excludes the house (bot) wallet."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*), SUM(coins), SUM(total_won), SUM(total_lost), SUM(spins), SUM(jackpots) "
                "FROM wallets WHERE guild_id = ? AND user_id != ?",
                (guild_id, get_house_id())
            )
            row = cursor.fetchone()
            return {
                "players": row[0] or 0,
                "total_coins": row[1] or 0,
                "total_won": row[2] or 0,
                "total_lost": row[3] or 0,
                "total_spins": row[4] or 0,
                "total_jackpots": row[5] or 0,
            }
    except sqlite3.Error as e:
        logger.error(f"Database error getting server stats: {e}")
        return {"players": 0, "total_coins": 0, "total_won": 0, "total_lost": 0, "total_spins": 0, "total_jackpots": 0}


def get_pot(guild_id: int) -> int:
    """On-hand house coins — the heistable / payout-funded bucket.
    For the full breakdown (on-hand + safe-harbor reserve) call get_house_state."""
    return get_house_state(guild_id)["on_hand"]


# Per-game record_* shims. All delegate to record_game(); kept so existing cog
# imports keep working. New cogs should call record_game directly.
def record_roulette(guild_id, user_id, won): record_game(guild_id, user_id, "roulette", won)
def record_rr(guild_id, user_id, won): record_game(guild_id, user_id, "rr", won)
def record_vault(guild_id, user_id, won): record_game(guild_id, user_id, "vault", won)
def record_vault_hard(guild_id, user_id, won): record_game(guild_id, user_id, "vault_hard", won)
def record_blackjack(guild_id, user_id, won): record_game(guild_id, user_id, "blackjack", won)
def record_highlow(guild_id, user_id, won): record_game(guild_id, user_id, "highlow", won)
def record_pawnshop(guild_id, user_id, won): record_game(guild_id, user_id, "pawnshop", won)
def record_heist(guild_id, user_id, succeeded): record_game(guild_id, user_id, "heist", succeeded)


def jail_user(guild_id: int, user_id: int, duration_seconds: int, reason: str = "",
              bail_amount: int = 0, channel_id: int = 0):
    """Lock a user out of casino activities for `duration_seconds` from now.
    If already jailed longer, keep the later deadline.
    `bail_amount` and `channel_id` are stored so /bail and the release-message
    loop can find them later.

    The memorial player (kev2tall) is exempt — jailing him is a silent no-op.
    Since every jail path (heist busts, bounties, /jail, extends) routes
    through here, this single guard makes him un-jailable everywhere."""
    if is_memorial(user_id):
        return
    import time as _t
    now = _t.time()
    until = now + duration_seconds
    try:
        with sqlite3.connect(DB_FILE) as conn:
            existing = conn.execute(
                "SELECT until_ts FROM jail WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            if existing and existing[0] > until:
                return  # already jailed longer
            conn.execute(
                "INSERT OR REPLACE INTO jail "
                "(guild_id, user_id, until_ts, reason, bail_amount, channel_id, jailed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (guild_id, user_id, until, reason, int(bail_amount), int(channel_id), now),
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error jailing user: {e}")


def get_jail_info(guild_id: int, user_id: int) -> dict | None:
    """Returns the user's jail row as a dict, or None if not jailed (or row missing).
    Does NOT delete expired rows — the release-message loop is responsible for cleanup."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            row = conn.execute(
                "SELECT until_ts, reason, bail_amount, channel_id, jailed_at "
                "FROM jail WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            if not row:
                return None
            return {
                "until_ts": row[0],
                "reason": row[1] or "",
                "bail_amount": row[2] or 0,
                "channel_id": row[3] or 0,
                "jailed_at": row[4] or 0.0,
            }
    except sqlite3.Error as e:
        logger.error(f"Database error reading jail info: {e}")
        return None


def get_active_jails(guild_id: int) -> list[dict]:
    """Return every currently-jailed user in a guild (until_ts in the future),
    ordered by soonest release first."""
    import time as _t
    now = _t.time()
    try:
        with sqlite3.connect(DB_FILE) as conn:
            rows = conn.execute(
                "SELECT user_id, until_ts, reason, bail_amount, channel_id, jailed_at, extended_seconds "
                "FROM jail WHERE guild_id = ? AND until_ts > ? ORDER BY until_ts ASC",
                (guild_id, now),
            ).fetchall()
            return [
                {
                    "user_id": r[0], "until_ts": r[1], "reason": r[2] or "",
                    "bail_amount": r[3] or 0, "channel_id": r[4] or 0,
                    "jailed_at": r[5] or 0.0, "extended_seconds": r[6] or 0,
                }
                for r in rows
            ]
    except sqlite3.Error as e:
        logger.error(f"Database error reading active jails: {e}")
        return []


def get_expired_jails() -> list[dict]:
    """Return every jail row whose sentence has expired. Used by the release-message loop."""
    import time as _t
    now = _t.time()
    try:
        with sqlite3.connect(DB_FILE) as conn:
            rows = conn.execute(
                "SELECT guild_id, user_id, reason, bail_amount, channel_id, jailed_at "
                "FROM jail WHERE until_ts <= ?",
                (now,),
            ).fetchall()
            return [
                {
                    "guild_id": r[0], "user_id": r[1], "reason": r[2] or "",
                    "bail_amount": r[3] or 0, "channel_id": r[4] or 0,
                    "jailed_at": r[5] or 0.0,
                }
                for r in rows
            ]
    except sqlite3.Error as e:
        logger.error(f"Database error scanning expired jails: {e}")
        return []


BAIL_COOLDOWN_SECONDS = 7 * 24 * 60 * 60  # one bail per jailed user per week


def bail_cooldown_remaining(guild_id: int, user_id: int) -> int:
    """Seconds until this user can be bailed out again. 0 if no cooldown active."""
    import time as _t
    try:
        with sqlite3.connect(DB_FILE) as conn:
            row = conn.execute(
                "SELECT last_bail_received_ts FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            if not row or not row[0]:
                return 0
            remaining = int(row[0] + BAIL_COOLDOWN_SECONDS - _t.time())
            return max(0, remaining)
    except sqlite3.Error as e:
        logger.error(f"Database error reading bail cooldown: {e}")
        return 0


def pay_bail(guild_id: int, jailed_user_id: int, payer_user_id: int) -> dict:
    """Atomically pay bail to release a jailed user. Bail money goes to the house.

    Self-bail IS allowed at this layer — the caller is responsible for any
    "only-self-when-jailed" policy on top.

    Returns a dict with `ok` (bool) and either `amount`/`reason`/`channel_id` on success
    or `error` describing the failure path. Caller is responsible for messaging."""
    import time as _t
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            jail_row = conn.execute(
                "SELECT until_ts, reason, bail_amount, channel_id FROM jail "
                "WHERE guild_id = ? AND user_id = ?",
                (guild_id, jailed_user_id),
            ).fetchone()
            if not jail_row:
                conn.rollback()
                return {"ok": False, "error": "not_jailed"}
            until_ts, reason, bail_amount, channel_id = jail_row
            if until_ts <= _t.time():
                conn.rollback()
                return {"ok": False, "error": "sentence_done"}
            if not bail_amount or bail_amount <= 0:
                conn.rollback()
                return {"ok": False, "error": "no_bail"}
            cd_row = conn.execute(
                "SELECT last_bail_received_ts FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, jailed_user_id),
            ).fetchone()
            last_bail = cd_row[0] if cd_row and cd_row[0] else 0
            cooldown_remaining = int(last_bail + BAIL_COOLDOWN_SECONDS - _t.time()) if last_bail else 0
            if cooldown_remaining > 0:
                conn.rollback()
                return {"ok": False, "error": "cooldown", "cooldown_remaining": cooldown_remaining}
            payer_row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, payer_user_id),
            ).fetchone()
            payer_coins = payer_row[0] if payer_row else 0
            if payer_coins < bail_amount:
                conn.rollback()
                return {"ok": False, "error": "broke", "need": bail_amount, "have": payer_coins}
            conn.execute(
                "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
                (bail_amount, guild_id, payer_user_id),
            )
            house_id = get_house_id()
            _ensure_house_wallet(conn, guild_id)
            conn.execute(
                "UPDATE wallets SET coins = coins + ? WHERE guild_id = ? AND user_id = ?",
                (bail_amount, guild_id, house_id),
            )
            conn.execute(
                "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, ?)",
                (guild_id, jailed_user_id, STARTING_COINS),
            )
            conn.execute(
                "UPDATE wallets SET last_bail_received_ts = ? WHERE guild_id = ? AND user_id = ?",
                (_t.time(), guild_id, jailed_user_id),
            )
            conn.execute(
                "DELETE FROM jail WHERE guild_id = ? AND user_id = ?",
                (guild_id, jailed_user_id),
            )
            conn.commit()
            return {
                "ok": True,
                "amount": bail_amount,
                "reason": reason or "",
                "channel_id": channel_id or 0,
            }
    except sqlite3.Error as e:
        logger.error(f"Database error paying bail: {e}")
        return {"ok": False, "error": "db"}


def extend_jail(guild_id: int, jailed_user_id: int, payer_user_id: int,
                additional_seconds: int, cost: int, max_total_extension_seconds: int) -> dict:
    """Atomically pay to extend a jail sentence. Money goes to the house.

    Caller passes the desired extension in seconds and the corresponding cost; this
    function enforces only:
      - the jailed user is currently jailed (not expired)
      - payer != jailed user
      - payer has enough coins
      - cumulative extension after this call does not exceed max_total_extension_seconds

    Returns a dict with `ok` plus either `new_until_ts`/`extended_seconds`/`channel_id`
    on success, or `error` on failure."""
    import time as _t
    if jailed_user_id == payer_user_id:
        return {"ok": False, "error": "self"}
    if is_memorial(jailed_user_id):
        return {"ok": False, "error": "memorial"}
    if additional_seconds <= 0 or cost <= 0:
        return {"ok": False, "error": "invalid_amount"}
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            jail_row = conn.execute(
                "SELECT until_ts, extended_seconds, channel_id FROM jail "
                "WHERE guild_id = ? AND user_id = ?",
                (guild_id, jailed_user_id),
            ).fetchone()
            if not jail_row:
                conn.rollback()
                return {"ok": False, "error": "not_jailed"}
            until_ts, already_extended, channel_id = jail_row
            already_extended = already_extended or 0
            if until_ts <= _t.time():
                conn.rollback()
                return {"ok": False, "error": "sentence_done"}
            if already_extended + additional_seconds > max_total_extension_seconds:
                conn.rollback()
                return {
                    "ok": False,
                    "error": "cap",
                    "already_extended": already_extended,
                    "cap_seconds": max_total_extension_seconds,
                }
            payer_row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, payer_user_id),
            ).fetchone()
            payer_coins = payer_row[0] if payer_row else 0
            if payer_coins < cost:
                conn.rollback()
                return {"ok": False, "error": "broke", "need": cost, "have": payer_coins}
            new_until_ts = until_ts + additional_seconds
            new_extended = already_extended + additional_seconds
            conn.execute(
                "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
                (cost, guild_id, payer_user_id),
            )
            house_id = get_house_id()
            _ensure_house_wallet(conn, guild_id)
            conn.execute(
                "UPDATE wallets SET coins = coins + ? WHERE guild_id = ? AND user_id = ?",
                (cost, guild_id, house_id),
            )
            conn.execute(
                "UPDATE jail SET until_ts = ?, extended_seconds = ? "
                "WHERE guild_id = ? AND user_id = ?",
                (new_until_ts, new_extended, guild_id, jailed_user_id),
            )
            conn.commit()
            return {
                "ok": True,
                "new_until_ts": new_until_ts,
                "extended_seconds": new_extended,
                "channel_id": channel_id or 0,
            }
    except sqlite3.Error as e:
        logger.error(f"Database error extending jail: {e}")
        return {"ok": False, "error": "db"}


def place_jail_bounty(guild_id: int, placer_user_id: int, target_user_id: int,
                     bet: int, success: bool, jail_seconds: int,
                     channel_id: int, reason: str = "Jailed by bounty",
                     guild_limit: int = 0, guild_window_seconds: int = 0,
                     user_limit: int = 0, user_window_seconds: int = 0) -> dict:
    """Atomically charge a bounty bet and (on success) jail the target.

    Two stackable rate limits are supported (both must pass; pass 0 to disable):
      - Guild-wide: at most `guild_limit` placements in the last `guild_window_seconds`
        across all users in this guild.
      - Per user:   at most `user_limit` placements in the last `user_window_seconds`
        by THIS placer in this guild.

    On a hit, nothing is charged and `error` is either `"rate_limited_user"` or
    `"rate_limited_guild"` along with `seconds_until_slot` for that specific limit.
    The per-user check runs first so the user gets the more actionable message.

    Returns a dict with `ok` plus result fields, or `error` describing the failure."""
    import time as _t
    if placer_user_id == target_user_id:
        return {"ok": False, "error": "self"}
    if is_memorial(target_user_id):
        return {"ok": False, "error": "memorial"}
    if bet <= 0:
        return {"ok": False, "error": "invalid_bet"}
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            now = _t.time()
            if user_limit > 0 and user_window_seconds > 0:
                u_cutoff = now - user_window_seconds
                u_in_window = conn.execute(
                    "SELECT ts FROM bounty_log "
                    "WHERE guild_id = ? AND placer_user_id = ? AND ts >= ? ORDER BY ts ASC",
                    (guild_id, placer_user_id, u_cutoff),
                ).fetchall()
                if len(u_in_window) >= user_limit:
                    oldest_ts = u_in_window[0][0]
                    conn.rollback()
                    return {
                        "ok": False,
                        "error": "rate_limited_user",
                        "limit": user_limit,
                        "window_seconds": user_window_seconds,
                        "seconds_until_slot": max(0, int(oldest_ts + user_window_seconds - now)),
                    }
            if guild_limit > 0 and guild_window_seconds > 0:
                g_cutoff = now - guild_window_seconds
                g_in_window = conn.execute(
                    "SELECT ts FROM bounty_log WHERE guild_id = ? AND ts >= ? ORDER BY ts ASC",
                    (guild_id, g_cutoff),
                ).fetchall()
                if len(g_in_window) >= guild_limit:
                    oldest_ts = g_in_window[0][0]
                    conn.rollback()
                    return {
                        "ok": False,
                        "error": "rate_limited_guild",
                        "limit": guild_limit,
                        "window_seconds": guild_window_seconds,
                        "seconds_until_slot": max(0, int(oldest_ts + guild_window_seconds - now)),
                    }
            payer_row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, placer_user_id),
            ).fetchone()
            payer_coins = payer_row[0] if payer_row else 0
            if payer_coins < bet:
                conn.rollback()
                return {"ok": False, "error": "broke", "need": bet, "have": payer_coins}
            conn.execute(
                "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
                (bet, guild_id, placer_user_id),
            )
            house_id = get_house_id()
            _ensure_house_wallet(conn, guild_id)
            conn.execute(
                "UPDATE wallets SET coins = coins + ? WHERE guild_id = ? AND user_id = ?",
                (bet, guild_id, house_id),
            )
            conn.execute(
                "INSERT INTO bounty_log (guild_id, placer_user_id, target_user_id, bet, ts) "
                "VALUES (?, ?, ?, ?, ?)",
                (guild_id, placer_user_id, target_user_id, bet, now),
            )
            jail_until = None
            if success:
                # Don't shorten an existing longer sentence.
                existing = conn.execute(
                    "SELECT until_ts FROM jail WHERE guild_id = ? AND user_id = ?",
                    (guild_id, target_user_id),
                ).fetchone()
                proposed_until = now + jail_seconds
                if existing and existing[0] > proposed_until:
                    # Already locked up longer — bounty money still gone, but no extra jail time.
                    conn.commit()
                    return {
                        "ok": True, "success": True, "jailed_longer": True,
                        "jail_until": existing[0],
                    }
                conn.execute(
                    "INSERT OR REPLACE INTO jail "
                    "(guild_id, user_id, until_ts, reason, bail_amount, channel_id, jailed_at, extended_seconds) "
                    "VALUES (?, ?, ?, ?, 0, ?, ?, 0)",
                    (guild_id, target_user_id, proposed_until, reason, channel_id, now),
                )
                jail_until = proposed_until
            conn.commit()
            return {"ok": True, "success": success, "jail_until": jail_until}
    except sqlite3.Error as e:
        logger.error(f"Database error placing bounty: {e}")
        return {"ok": False, "error": "db"}


def clear_expired_jail(guild_id: int, user_id: int) -> bool:
    """Delete an expired jail row. Returns True if a row was removed. Used by the release loop."""
    import time as _t
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.execute(
                "DELETE FROM jail WHERE guild_id = ? AND user_id = ? AND until_ts <= ?",
                (guild_id, user_id, _t.time()),
            )
            conn.commit()
            return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error(f"Database error clearing expired jail: {e}")
        return False


def increment_bot_heist_offenses(guild_id: int, user_id: int) -> int:
    """Bump the user's bot-heist offense count and return the new total."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, ?)",
                (guild_id, user_id, STARTING_COINS),
            )
            conn.execute(
                "UPDATE wallets SET bot_heist_offenses = bot_heist_offenses + 1 "
                "WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            row = conn.execute(
                "SELECT bot_heist_offenses FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            conn.commit()
            return int(row[0]) if row else 1
    except sqlite3.Error as e:
        logger.error(f"Database error incrementing bot heist offenses: {e}")
        return 1


def unjail_user(guild_id: int, user_id: int) -> bool:
    """Clear a user's jail sentence. Returns True if they were actually in jail."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.execute(
                "DELETE FROM jail WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error(f"Database error unjailing user: {e}")
        return False


def jail_remaining(guild_id: int, user_id: int) -> int:
    """Return seconds remaining on a user's jail sentence. 0 if not jailed.
    Does NOT delete expired rows — the release-message loop announces release
    and then cleans up, so cleanup must happen there, not here."""
    import time as _t
    try:
        with sqlite3.connect(DB_FILE) as conn:
            row = conn.execute(
                "SELECT until_ts FROM jail WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            if not row:
                return 0
            remaining = int(row[0] - _t.time())
            return max(0, remaining)
    except sqlite3.Error as e:
        logger.error(f"Database error checking jail: {e}")
        return 0


def jail_message(guild_id: int, user_id: int) -> str | None:
    """Returns a user-facing string if jailed, else None. Cogs call this to gate play."""
    remaining = jail_remaining(guild_id, user_id)
    if remaining <= 0:
        return None
    h, rem = divmod(remaining, 3600)
    m, _s = divmod(rem, 60)
    if h > 0:
        return f"🚔 **You're in casino jail** for another **{h}h {m}m**. No bets, no gambling. Should've been nicer to the house."
    return f"🚔 **You're in casino jail** for another **{m}m**. No bets, no gambling."


def record_den(guild_id, user_id, won): record_game(guild_id, user_id, "den", won)


# --- Admin: hard-reset the economy ----------------------------------------

# Tables wiped by clear_economy(); `game_stats` is deliberately omitted so
# leaderboards (play counts / win counts) survive a reset. Edit this list if
# the caller wants a different blast radius.
_CLEAR_ECONOMY_TABLES = (
    "wallets",
    "jail",
    "cog_kv",          # inventory, wager, any future feature state
    "house_reserve",
    "bounty_log",
    "loot_cooldowns",
)


def clear_economy(guild_id: int) -> dict:
    """Hard-reset the economy for one guild. Wipes wallets, the house pot
    (on-hand + reserve), all jail sentences, the cog_kv store (inventory,
    Loaded Dice wager, any cog-owned state), the bounty rate-limit log, and
    loot cooldowns. PRESERVES `game_stats` so leaderboards aren't erased.

    All deletions run in a single transaction — either every table clears or
    none do. Returns a dict {table_name: rows_deleted}.

    Callers should require human approval before invoking — there is no undo.
    """
    counts: dict[str, int] = {}
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            for tbl in _CLEAR_ECONOMY_TABLES:
                try:
                    cur = conn.execute(
                        f"DELETE FROM {tbl} WHERE guild_id = ?", (guild_id,),
                    )
                    counts[tbl] = cur.rowcount
                except sqlite3.OperationalError:
                    # Table not present in this DB — log and continue.
                    counts[tbl] = 0
            conn.commit()
            return counts
    except sqlite3.Error as e:
        logger.error(f"Database error in clear_economy: {e}")
        return {}


# Initialize DB on import
_init_db()
