"""Shared economy database utilities. All economy cogs import from here."""

import sqlite3
from contextlib import contextmanager
import json
import os
import logging
from datetime import datetime
from config import DATA_DIR

logger = logging.getLogger(__name__)

DB_FILE = os.path.join(DATA_DIR, "economy.db")
STARTING_COINS = 100

# --- The coin ceiling -------------------------------------------------------
# SQLite's INTEGER is a signed 64-bit value, and when an integer expression
# overflows that range SQLite does NOT raise — it silently promotes the result
# to REAL. `coins = coins + 1` on a big enough wallet quietly turns the column
# into 9.223372036854776e+18, every read after that hands cogs a float,
# f"{coins:,}" prints scientific-notation garbage, and anything doing exact
# integer money math downstream breaks. So no stored coin figure is ever
# allowed anywhere near the 64-bit edge.
#
# MAX_COINS is the hard ceiling on every stored money figure: wallets, both
# house buckets, bank accounts, and the lifetime total_won/total_lost/net_won
# counters.
#
# WHY THIS EXACT NUMBER. It is the literal maximum a SQLite INTEGER can hold —
# the ceiling is now the storage limit itself, with NO margin left. Getting
# here required proving nothing binds below it:
#
#   * The saturating credits `MIN(coins + ?, MAX_COINS)` are safe at any cap.
#     If the inner add overflows, SQLite promotes it to a REAL that is by
#     definition further from zero than the cap, so MIN()/MAX() returns the
#     integer cap and the overflow is absorbed. Verified, not assumed.
#   * Guild-wide totals are summed in Python (_sum_money), where ints are
#     arbitrary precision, so a server of N maxed wallets is not a constraint.
#     Keeping SUM() in SQL would have forced a far lower ceiling.
#   * The wealth leaderboard's `w.coins + COALESCE(b.value, 0)` was the one
#     money expression with no clamp to absorb a promotion; it sums in Python.
#
# THE RULE THAT KEEPS THIS SAFE, now that the buffer is gone: every money
# expression SQL evaluates must be a single column, a SUBTRACTION, or an
# addition wrapped in a MIN()/MAX() clamp. A bare multi-term money sum in SQL
# (`a + b`, unclamped) promotes straight to REAL at these values and silently
# corrupts the row — the exact bug this ceiling exists to prevent. Sum in
# Python instead; it costs nothing at per-guild row counts.
#
# Past this point the only way up is abandoning INTEGER storage for zero-padded
# TEXT with all arithmetic in Python. Ordering and the `WHERE coins >= ?`
# balance guard survive that; SQL arithmetic does not, and net_won would need a
# bias offset for negatives. That is a full migration of every money write.
#
# Credits SATURATE at the ceiling — they never wrap and never promote to REAL.
# Two-sided moves (transfers, payouts) shrink the move to the receiver's
# remaining headroom BEFORE debiting the sender, so saturation never destroys
# coins mid-transfer. Practically: a maxed-out wallet simply can't be paid
# more, and the coins stay where they were.
MAX_COINS = 2**63 - 1  # 9,223,372,036,854,775,807 — int64 max, the hard edge
_SQLITE_MAX_INT = 2**63 - 1


def coins_int(value) -> int:
    """Coerce a money figure read out of the DB to a plain, sane int.

    Anything that came back as a REAL (a pre-ceiling row that already
    overflowed) is truncated, junk becomes 0, and the result is clamped to
    [0, MAX_COINS]. Use on every coin figure economy.py hands to a cog, so a
    legacy corrupted row can never leak a float into game math or a format
    string."""
    try:
        n = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0
    if n <= 0:
        return 0
    return n if n <= MAX_COINS else MAX_COINS


def clamp_amount(value) -> int:
    """Coerce an amount coming INTO an economy helper to [0, MAX_COINS].
    Same as coins_int; named for the input side so call sites read clearly."""
    return coins_int(value)


def _signed_int(value) -> int:
    """coins_int for counters that are legitimately negative (net_won)."""
    try:
        n = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(-MAX_COINS, min(MAX_COINS, n))


def headroom(current: int) -> int:
    """Coins that can still be credited to a balance of `current` before it
    hits the ceiling. Two-sided moves clamp to this so nothing is destroyed."""
    return max(0, MAX_COINS - coins_int(current))


# Saturating-credit SQL fragments. A bare `coins = coins + ?` is exactly what
# walks a column into 64-bit overflow; these pin the result at the ceiling
# instead. Use them for EVERY money credit in this file — MAX_COINS is an int
# literal interpolated at import, never user input. A column that is already a
# corrupted REAL heals on its first write through one of these, because
# MIN(9.2e18, 1e15) returns the integer ceiling.
_ADD_COINS = f"coins = MIN(coins + ?, {MAX_COINS})"
_ADD_TOTAL_WON = f"total_won = MIN(total_won + ?, {MAX_COINS})"
_ADD_TOTAL_LOST = f"total_lost = MIN(total_lost + ?, {MAX_COINS})"
_ADD_NET_WON = f"net_won = MAX(-{MAX_COINS}, MIN(net_won + ?, {MAX_COINS}))"
_SUB_NET_WON = f"net_won = MAX(-{MAX_COINS}, MIN(net_won - ?, {MAX_COINS}))"
_ADD_KV_VALUE = f"value = MIN(value + ?, {MAX_COINS})"

# --- Weekly winnings tax --------------------------------------------------
# The economy's main coin sink (cogs/taxes.py). It's an income tax on GROSS
# winnings: once a week each player is assessed WINNINGS_TAX_PCT of everything
# they won since the last levy (total_won now minus the snapshot taken last
# week), independent of what they later lost or spent. Win nothing and you owe
# nothing. We snapshot total_won rather than the wallet-balance delta so that
# winnings churned back into losses or spending are still taxed — every win
# path bumps total_won (casino_payout, slots/coinflip update_wallet, roulette
# award_coins, cockroach/pigderby/loot add_coins), so it's a complete and
# game-agnostic measure. The bill is locked at levy time; players get TAX_GRACE_SECONDS
# to pay it (coins flow to the house on-hand — a closed loop, not burned). Miss
# the deadline and you're a tax evader: the house seizes the bill plus a cut of
# your wallet and jails you (graduated, see the penalty block below). The levy
# notice posts to the #TAX_CHANNEL_NAME channel and is the ONLY reminder.
WINNINGS_TAX_PCT = 0.15          # 15% of the week's gross winnings
TAX_PERIOD_SECONDS = 7 * 24 * 3600   # one levy per week
TAX_GRACE_SECONDS = 24 * 3600        # 24h to pay before enforcement
TAX_CHANNEL_NAME = "game-spam"       # where the weekly notice posts

# Graduated penalties for missing the deadline (cogs/taxes.py). The seizure is
# always the unpaid tax bill PLUS a penalty cut of the wallet, capped at what
# the evader actually holds, and routed to the house (closed loop).
#   1st offense: bill + 25% of wallet, 48h jail, Get Out of Jail Free works.
#   2nd+ offense: bill + 50% of wallet, 72h jail, GOOJF card disabled.
# Offense level decays one tier after TAX_DECAY_WEEKS consecutive on-time pays.
TAX_PENALTY_PCT_1 = 0.25         # first-offense wallet penalty
TAX_PENALTY_PCT_2 = 0.50         # repeat-offense wallet penalty
TAX_JAIL_SECONDS = 48 * 3600         # first-offense sentence
TAX_JAIL_REPEAT_SECONDS = 72 * 3600  # repeat-offense sentence (GOOJF disabled)
TAX_DECAY_WEEKS = 4                   # on-time pays needed to drop an offense tier

# Monthly wealth tax (cogs/taxes.py). On the WEALTH_TAX_DAYth of each month
# (local time), anyone whose TOTAL wealth — wallet + bank — exceeds
# WEALTH_TAX_THRESHOLD is assessed WEALTH_TAX_PCT of that total. Unlike the
# winnings tax there's no bill or grace window: by definition the levy is a
# tiny fraction of what they hold, so the house collects on the spot (wallet
# first, then bank — closed loop, coins go to house on-hand). No jail, no
# offense tracking; it's a haircut, not a crime.
WEALTH_TAX_PCT = 0.01                    # 1% of total wealth
WEALTH_TAX_THRESHOLD = 1_000_000_000     # only fortunes above 1B are taxed
WEALTH_TAX_DAY = 15                      # day of the month it fires


def check_bet(bet: int) -> str | None:
    """Validate a player's stake before collecting it. Returns a user-facing
    error string if the bet is non-positive or past the MAX_COINS ceiling,
    else None. There is no bet cap below the ceiling — and the ceiling is a
    storage limit, not a game-balance one (see the MAX_COINS note). Call at the
    top of every game's bet flow, before transfer_to_house / deduct, e.g.:

        err = check_bet(bet)
        if err:
            await reply(err)
            return
    """
    if bet <= 0:
        return "Bet must be greater than 0."
    if bet > MAX_COINS:
        return f"Bet is too large — the ceiling is {MAX_COINS:,} coins."
    return None


# --- Memorial player ------------------------------------------------------
# kev2tall is an opt-out, exempt player — a member who has passed away. He is
# never jailed and never involved in a heist.
#
# The old standing offering (a tithe of every win/loss, paid by the house to
# his wallet) is RETIRED as of the wealth-tax rebalance: the rate is pinned to
# 0.0, so _memorial_house_tithe / memorial_tithe short-circuit and every
# callsite is a no-op. The tithe plumbing is left in place (cheap, harmless,
# trivially revivable) rather than ripped out of a dozen cogs. Kev's jail/heist
# exemptions are unaffected — only the offering is gone. See the weekly wealth
# tax (cogs/taxes.py) for the sink that replaced it.
MEMORIAL_USER_ID = 361219124979826698  # kev2tall
MEMORIAL_TITHE_PCT = 0.0  # retired — was 1.5%; see note above


def is_memorial(user_id: int) -> bool:
    """True if user_id is the memorial player (kev2tall)."""
    return user_id == MEMORIAL_USER_ID

# The bot itself is the house. Its Discord user ID is set via set_house_id() on startup.
# Until that happens, fall back to legacy id 0 so older data still resolves.
_LEGACY_HOUSE_ID = 0
_house_id = _LEGACY_HOUSE_ID


def now_local() -> datetime:
    """Current local time as a tz-aware datetime, honoring the standard `TZ`
    env var. Use this for any 'what day/time is it' logic so day boundaries
    follow the configured timezone."""
    return datetime.now().astimezone()


def today_str() -> str:
    """Today's date as 'YYYY-MM-DD' in local time (honors the `TZ` env var).
    The single source of truth for any 'once per calendar day' / 'good for the
    rest of the day' gate (jail cards, heist shields)."""
    return datetime.now().strftime("%Y-%m-%d")


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
                    f"UPDATE wallets SET {_ADD_COINS} WHERE guild_id = ? AND user_id = ?",
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


# Every stored money figure, as (table, column, allow_negative). The repair
# migration and the read paths both work off this list — add a new money column
# here and it's covered.
_MONEY_COLUMNS = [
    ("wallets", "coins", False),
    ("wallets", "total_won", False),
    ("wallets", "total_lost", False),
    ("wallets", "net_won", True),
    ("house_reserve", "coins", False),
]


def _repair_overflowed_money(conn: sqlite3.Connection):
    """One-shot migration: heal money that ran past 64-bit and got silently
    promoted to REAL, plus anything sitting above the new ceiling.

    A column SQLite turned into 9.223372036854776e+18 reads back as a float
    forever after — that's the scientific notation showing up in wallets and
    payouts. This pins every money figure back into [0, MAX_COINS] (or
    [-MAX_COINS, MAX_COINS] for net_won) as a real INTEGER. It's a haircut on
    balances that were nonsense anyway; the saturating credits added alongside
    it mean nothing can climb back out of range."""
    repaired = 0
    for table, column, allow_negative in _MONEY_COLUMNS:
        floor = -MAX_COINS if allow_negative else 0
        try:
            # COALESCE + inner CAST before the clamp: MIN(NULL, x) is NULL, and
            # SQLite sorts TEXT above every number, so a null or junk cell would
            # otherwise "repair" to NULL or to the ceiling. Both become 0.
            cur = conn.execute(
                f"UPDATE {table} SET {column} = "
                f"CAST(MAX(?, MIN(CAST(COALESCE({column}, 0) AS INTEGER), ?)) AS INTEGER) "
                f"WHERE typeof({column}) != 'integer' OR {column} > ? OR {column} < ?",
                (floor, MAX_COINS, MAX_COINS, floor),
            )
        except sqlite3.OperationalError:
            continue  # table/column not on this DB yet
        repaired += cur.rowcount or 0
    # Bank balances live in cog_kv, where `value` is deliberately untyped —
    # only the balance rows are money (interest_ts is a REAL on purpose).
    try:
        cur = conn.execute(
            "UPDATE cog_kv SET value = "
            "CAST(MAX(0, MIN(CAST(COALESCE(value, 0) AS INTEGER), ?)) AS INTEGER) "
            "WHERE namespace = ? AND key = ? "
            "AND (typeof(value) != 'integer' OR value > ? OR value < 0)",
            (MAX_COINS, _BANK_NS, _BANK_KEY, MAX_COINS),
        )
        repaired += cur.rowcount or 0
    except sqlite3.OperationalError:
        pass
    if repaired:
        logger.warning(
            f"Repaired {repaired} money value(s) that had overflowed 64-bit "
            f"into floats or exceeded the {MAX_COINS:,} coin ceiling."
        )


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
                    net_won INTEGER DEFAULT 0,
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
                    no_release INTEGER DEFAULT 0,
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
            # concept — inventory, future cooldowns and flags. A cog stores
            # under its own `namespace` via the kv_* / feature helpers and
            # never needs its own table or SQLite handle.
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
                # net_won: lifetime NET gambling profit (payouts minus stakes),
                # the basis for the weekly winnings tax. Distinct from total_won,
                # which counts GROSS payouts (incl. the returned stake) and stays
                # the lifetime "Total Won" brag stat. See cogs/taxes.py.
                ("net_won", "INTEGER DEFAULT 0"),
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
                ("no_release", "INTEGER DEFAULT 0"),
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
            #   2 = repair money columns that overflowed 64-bit into REAL.
            current_version = conn.execute("PRAGMA user_version").fetchone()[0]
            if current_version < 1:
                _backfill_game_stats(conn)
                conn.execute("PRAGMA user_version = 1")
            if current_version < 2:
                _repair_overflowed_money(conn)
                conn.execute("PRAGMA user_version = 2")
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
            # coins_int, not raw row values: a row that overflowed before the
            # ceiling existed comes back as a float, and cogs must never see one.
            return {
                "coins": coins_int(row[0]), "total_won": coins_int(row[1]),
                "total_lost": coins_int(row[2]),
                "spins": int(row[3] or 0), "jackpots": int(row[4] or 0),
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
        delta = max(-MAX_COINS, min(MAX_COINS, int(delta)))
        with sqlite3.connect(DB_FILE) as conn:
            if delta > 0:
                # `delta` is already the NET result for these games (slots,
                # coinflip), so it feeds net_won directly (the tax basis).
                conn.execute(
                    f"UPDATE wallets SET {_ADD_COINS}, {_ADD_TOTAL_WON}, {_ADD_NET_WON}, "
                    "spins = spins + 1, jackpots = jackpots + ? WHERE guild_id = ? AND user_id = ?",
                    (delta, delta, delta, 1 if is_jackpot else 0, guild_id, user_id)
                )
            else:
                conn.execute(
                    f"UPDATE wallets SET coins = coins + ?, {_ADD_TOTAL_LOST}, "
                    f"{_ADD_NET_WON}, spins = spins + 1 WHERE guild_id = ? AND user_id = ?",
                    (delta, abs(delta), delta, guild_id, user_id)
                )
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error updating wallet: {e}")


def add_coins(guild_id: int, user_id: int, amount: int):
    """Add coins without incrementing spins (for loot, daily, etc)."""
    get_wallet(guild_id, user_id)  # ensure exists
    amount = clamp_amount(amount)
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                f"UPDATE wallets SET {_ADD_COINS}, {_ADD_TOTAL_WON} WHERE guild_id = ? AND user_id = ?",
                (amount, amount, guild_id, user_id)
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error adding coins: {e}")


def deduct_coins(guild_id: int, user_id: int, amount: int):
    """Deduct coins without incrementing spins."""
    amount = clamp_amount(amount)
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                f"UPDATE wallets SET coins = coins - ?, {_ADD_TOTAL_LOST} WHERE guild_id = ? AND user_id = ?",
                (amount, amount, guild_id, user_id)
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error deducting coins: {e}")


def fine_user(guild_id: int, user_id: int, amount: int):
    """Fine a user (coins can't go below 0)."""
    amount = clamp_amount(amount)
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
      {"ok": True, "sender_balance": X, "receiver_balance": Y, "amount": moved}
      {"ok": False, "error": "invalid_amount"}
      {"ok": False, "error": "broke", "have": X, "need": amount}
      {"ok": False, "error": "capped"}   # receiver is already at MAX_COINS
      {"ok": False, "error": "db"}
    Sender/receiver wallets are created in-transaction if missing.

    `amount` is trimmed to the receiver's remaining headroom under MAX_COINS
    (`"amount"` reports what actually moved) so the ceiling never swallows
    coins mid-transfer — the untransferable remainder stays with the sender.
    """
    amount = clamp_amount(amount)
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
            sender_coins = coins_int(sender_row[0] if sender_row else 0)
            if sender_coins < amount:
                conn.rollback()
                return {"ok": False, "error": "broke", "have": sender_coins, "need": amount}
            recv_row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, to_id),
            ).fetchone()
            receiver_coins = coins_int(recv_row[0] if recv_row else 0)
            amount = min(amount, headroom(receiver_coins))
            if amount <= 0:
                conn.rollback()
                return {"ok": False, "error": "capped", "have": receiver_coins}
            conn.execute(
                "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
                (amount, guild_id, from_id),
            )
            conn.execute(
                f"UPDATE wallets SET {_ADD_COINS} WHERE guild_id = ? AND user_id = ?",
                (amount, guild_id, to_id),
            )
            conn.commit()
            return {
                "ok": True,
                "sender_balance": sender_coins - amount,
                "receiver_balance": receiver_coins + amount,
                "amount": amount,
            }
    except sqlite3.Error as e:
        logger.error(f"Database error transferring coins: {e}")
        return {"ok": False, "error": "db"}


# --- Transaction plumbing ---------------------------------------------------
# Every write helper used to hand-roll the same dance: connect, BEGIN
# IMMEDIATE, remember to rollback on each early exit, commit, log on
# sqlite3.Error. `_tx` is that dance with a name. Pattern for new helpers:
#
#     try:
#         with _tx("my_helper") as conn:
#             ...reads...
#             if not valid:
#                 raise _Abort(fallback_value)   # rolls back, carries result
#             ...writes...
#         return success_value
#     except _Abort as a:
#         return a.result
#     except sqlite3.Error:
#         return db_error_fallback              # _tx already logged it
#
# The connection is always closed (the bare `with sqlite3.connect(...)` the
# old code used never closed it).

class _Abort(Exception):
    """Raised inside a _tx block to roll back and hand `result` back."""

    def __init__(self, result=None):
        self.result = result


@contextmanager
def _tx(op: str):
    """One immediate-mode write transaction: BEGIN IMMEDIATE on entry, commit
    on clean exit, rollback on _Abort or sqlite3.Error (the latter logged
    under `op` and re-raised)."""
    conn = sqlite3.connect(DB_FILE)
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except _Abort:
        conn.rollback()
        raise
    except sqlite3.Error as e:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        logger.error(f"Database error in {op}: {e}")
        raise
    finally:
        conn.close()


def try_deduct(guild_id: int, user_id: int, amount: int) -> bool:
    """Atomically deduct `amount` only if the wallet has enough. Returns True on success.

    Use this in cogs to take a bet; it closes the TOCTOU window between a balance
    check and the actual deduction. Wallet is created in-transaction if missing.
    """
    amount = clamp_amount(amount)
    if amount <= 0:
        return False
    try:
        with _tx("try_deduct") as conn:
            conn.execute(
                "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, ?)",
                (guild_id, user_id, STARTING_COINS),
            )
            cursor = conn.execute(
                f"UPDATE wallets SET coins = coins - ?, {_ADD_TOTAL_LOST} "
                "WHERE guild_id = ? AND user_id = ? AND coins >= ?",
                (amount, amount, guild_id, user_id, amount),
            )
            if cursor.rowcount == 0:
                raise _Abort(False)
        return True
    except _Abort as a:
        return a.result
    except sqlite3.Error:
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
# Annualized rate, compounded continuously on read. 0.15 = 15% APR.
# Stays scale-invariant: doesn't matter if you read every second or once a month,
# the effective growth equals the APR exactly.
HOUSE_INTEREST_APR = 0.15
_SECONDS_PER_YEAR = 365.25 * 24 * 3600

# Elapsed time is clamped before compounding: a corrupt or zeroed timestamp
# would otherwise ask for (1.15 ** a_few_thousand), which is inf as a float and
# a balance that instantly pins at the ceiling.
_MAX_INTEREST_YEARS = 50.0


def _grow(balance: int, apr: float, years: float) -> int:
    """Compound `balance` at `apr` for `years`, clamped to the coin ceiling.

    Both interest accruals (house reserve, player bank) go through this so
    neither can compound a balance into 64-bit overflow — which is what turned
    wallets into floats in the first place."""
    balance = coins_int(balance)
    if balance <= 0 or years <= 0:
        return balance
    years = min(years, _MAX_INTEREST_YEARS)
    try:
        grown = int(balance * ((1.0 + apr) ** years))
    except (OverflowError, ValueError):
        return MAX_COINS
    return coins_int(grown)

# Per-event drain caps as random ranges. A successful event rolls uniform(min, max)
# and takes that fraction of on-hand. Living here (not in their cogs) so /pot can
# read the ranges without a cross-cog import and so any future "casino policy"
# tuning happens in one file.
# Green is a 1-in-37 event (any green bet that hits 0), far more frequent than
# a 1-in-125 vault heist — so its take band is much narrower. At 5–15% the
# expected drain per green bet (~0.27% of on-hand) roughly matches the expected
# drain per heist attempt (~0.24%), instead of nuking the pot every ~37 bets.
HOUSE_HEIST_MIN_PCT = 0.0
HOUSE_HEIST_MAX_PCT = 0.60
GREEN_JACKPOT_MIN_PCT = 0.05
GREEN_JACKPOT_MAX_PCT = 0.15

# Rob-the-house odds tiers, rolled in cogs/heist.py (mutually exclusive,
# checked rarest-first off one roll; anything past them is a bust → jail).
# Here rather than in the cog so /pot can display them.
BOT_HEIST_BOTH_ODDS = 1 / 5000    # THE FULL SWEEP: vault AND safe-deposit boxes
BOT_HEIST_BOXES_ODDS = 1 / 1000   # safe-deposit boxes only
BOT_HEIST_VAULT_ODDS = 1 / 125    # vault only

# Starting balance seeded into the house's safe-harbor RESERVE on first
# touch (and after any clear_economy wipe). It lives in the reserve — not
# on-hand — so it can't be drained by a heist or a green-jackpot roll; it
# can only ever leave the house via casino_payout's reserve fallback when
# on-hand is short. That's the "can't bankrupt the bot on the first bet"
# guarantee.
HOUSE_STARTING_COINS = 100_000_000

# Weekly replenishment: if total house funds (on-hand + reserve) drop below
# HOUSE_LOW_WATER_PCT of the seed, the upkeep task tops the reserve back up so
# the combined house funds reach HOUSE_STARTING_COINS again. This is a safety
# net — under normal play the house grows on its own. Tuned here, read by the
# house_upkeep cog's weekly loop.
HOUSE_LOW_WATER_PCT = 0.25


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
    """Apply accrued interest to the safe-harbor reserve, then self-heal a
    tapped reserve from on-hand. Idempotent. Caller is expected to be holding
    BEGIN IMMEDIATE so the read-modify-write is atomic."""
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
    reserve_coins = coins_int(row[0])
    last_ts = row[1] or 0
    # Compound interest on any existing reserve. APR-based: elapsed seconds
    # are converted to fractional years and the growth factor is (1+APR)^years.
    # This stays invariant to read frequency — same end balance whether read once
    # per year or 1000 times per day. Compounding is the main engine that walks
    # a balance toward the 64-bit edge, so the result is ceiling-clamped.
    if reserve_coins > 0 and last_ts > 0 and now > last_ts:
        elapsed_years = (now - last_ts) / _SECONDS_PER_YEAR
        reserve_coins = _grow(reserve_coins, HOUSE_INTEREST_APR, elapsed_years)
    # Self-heal: a payout that tapped the reserve leaves it below the seed.
    # Refill the deficit from on-hand (a transfer, nothing minted) so the
    # insurance bucket is always the first thing house revenue rebuilds.
    # replenish_house_if_low stays as the mint-backstop for a house that's
    # broke in BOTH buckets.
    deficit = HOUSE_STARTING_COINS - reserve_coins
    if deficit > 0:
        conn.execute(
            "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, 0)",
            (guild_id, get_house_id()),
        )
        on_hand_row = conn.execute(
            "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
            (guild_id, get_house_id()),
        ).fetchone()
        heal = min(deficit, on_hand_row[0] if on_hand_row else 0)
        if heal > 0:
            conn.execute(
                "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
                (heal, guild_id, get_house_id()),
            )
            reserve_coins += heal
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
    house_coins = coins_int(house_row[0] if house_row else 0)
    pay = min(tithe, house_coins)
    if pay <= 0:
        return 0
    conn.execute(
        "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, 0)",
        (guild_id, MEMORIAL_USER_ID),
    )
    memorial_row = conn.execute(
        "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
        (guild_id, MEMORIAL_USER_ID),
    ).fetchone()
    pay = min(pay, headroom(memorial_row[0] if memorial_row else 0))
    if pay <= 0:
        return 0
    conn.execute(
        "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
        (pay, guild_id, house_id),
    )
    conn.execute(
        f"UPDATE wallets SET {_ADD_COINS} WHERE guild_id = ? AND user_id = ?",
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


def transfer_to_house(guild_id: int, user_id: int, amount: int, is_bet: bool = True) -> dict:
    """Atomic transfer from a user to the house (donations, vig, bet collection).
    After the deposit, normalizes the house (applies interest to the reserve).

    `is_bet` (default True): treat this as a gambling stake, so it lowers the
    player's net_won (the weekly-tax basis) by `amount`. A matching win comes
    back through casino_payout, which raises net_won — so net over a game is
    payout minus stake. Pure sinks that are NOT bets (paying tax, bail, fees,
    burning coins) pass is_bet=False so they don't shrink the tax basis.

    Same return shape as transfer_coins. `receiver_balance` is the on-hand
    wallet, not the total house net worth.

    Unlike transfer_coins this does NOT refuse when the house on-hand is at
    MAX_COINS — refusing would make every game unplayable. The credit saturates
    instead, so a stake collected into a maxed-out house is simply burned. That
    only bites at a quadrillion coins on hand, and burning is the safe
    direction to fail.

    A BET from a house shareholder is refused outright (`shareholder`) — they
    hold a piece of the house, so they don't play against it. Non-bet payments
    (is_bet=False: tax, bail, fees) still go through. Living in this one
    function is what makes the rule impossible to bypass. Their dividend is
    NOT taken here: it comes out of profit on a poll (settle_house_dividends),
    so nothing is skimmed off the top of a stake."""
    amount = clamp_amount(amount)
    if amount <= 0:
        return {"ok": False, "error": "invalid_amount"}
    if is_bet and is_shareholder(guild_id, user_id):
        return {"ok": False, "error": "shareholder"}
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
            sender_coins = coins_int(sender_row[0] if sender_row else 0)
            if sender_coins < amount:
                conn.rollback()
                return {"ok": False, "error": "broke", "have": sender_coins, "need": amount}
            # A bet lowers the player's net winnings (the weekly-tax basis); a
            # matching win restores it via casino_payout. Non-bet sinks skip this.
            if is_bet:
                conn.execute(
                    f"UPDATE wallets SET coins = coins - ?, {_SUB_NET_WON} WHERE guild_id = ? AND user_id = ?",
                    (amount, amount, guild_id, user_id),
                )
            else:
                conn.execute(
                    "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
                    (amount, guild_id, user_id),
                )
            conn.execute(
                f"UPDATE wallets SET {_ADD_COINS} WHERE guild_id = ? AND user_id = ?",
                (amount, guild_id, house_id),
            )
            sender_balance = sender_coins - amount
            _normalize_house(conn, guild_id)
            # Memorial tithe (1.5% of the bet, the loss side) — skips the
            # memorial player so he doesn't tithe to himself.
            if not is_memorial(user_id):
                _memorial_house_tithe(conn, guild_id, amount)
            recv_row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, house_id),
            ).fetchone()
            receiver_balance = coins_int(recv_row[0] if recv_row else 0)
            conn.commit()
            return {
                "ok": True,
                "sender_balance": sender_balance,
                "receiver_balance": receiver_balance,
                "amount": amount,
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
    amount = clamp_amount(amount)
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
            sender_coins = coins_int(row[0] if row else 0)
            if sender_coins < amount:
                conn.rollback()
                return {"ok": False, "error": "broke",
                        "have": sender_coins, "need": amount}
            conn.execute(
                "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
                (amount, guild_id, user_id),
            )
            conn.execute(
                f"UPDATE house_reserve SET {_ADD_COINS} WHERE guild_id = ?",
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

    The payout is also trimmed to the winner's remaining headroom under
    MAX_COINS — a wallet at the ceiling simply can't be paid more, and the
    untaken coins stay in the house rather than overflowing the column. That
    clamp deliberately happens AFTER the bankruptcy check, so hitting the
    ceiling is never mistaken for the house being short.
    """
    amount = clamp_amount(amount)
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
            house_coins = coins_int(house_row[0] if house_row else 0)
            shortfall = amount - house_coins
            if shortfall > 0:
                reserve_row = conn.execute(
                    "SELECT coins FROM house_reserve WHERE guild_id = ?",
                    (guild_id,),
                ).fetchone()
                reserve_coins = coins_int(reserve_row[0] if reserve_row else 0)
                topup = min(shortfall, reserve_coins)
                if topup > 0:
                    conn.execute(
                        "UPDATE house_reserve SET coins = coins - ? WHERE guild_id = ?",
                        (topup, guild_id),
                    )
                    conn.execute(
                        f"UPDATE wallets SET {_ADD_COINS} WHERE guild_id = ? AND user_id = ?",
                        (topup, guild_id, house_id),
                    )
                    house_coins += topup
            pay = min(amount, max(0, house_coins))
            if pay < amount:
                # THE HOUSE IS BANKRUPT: both buckets are drained and a winner
                # is still owed money. Log the event for cogs/bankruptcy.py,
                # which covers the shortfall out of player bank accounts and
                # opens the economy-reset referendum.
                _record_bankruptcy_event(conn, guild_id, user_id, amount, pay)
            # Ceiling clamp, after the bankruptcy check: coins the winner has
            # no room for are left in the house, not overflowed into their wallet.
            winner_row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            capped = min(pay, headroom(winner_row[0] if winner_row else 0))
            if capped < pay:
                # Their wallet, their problem — cogs/coincap.py says so out loud.
                _record_ceiling_event(conn, guild_id, user_id, pay, capped, "payout")
            pay = capped
            if pay <= 0:
                conn.commit()  # keep the interest normalization + the event
                return 0
            conn.execute(
                "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
                (pay, guild_id, house_id),
            )
            conn.execute(
                f"UPDATE wallets SET {_ADD_COINS}, {_ADD_TOTAL_WON}, {_ADD_NET_WON} "
                "WHERE guild_id = ? AND user_id = ?",
                (pay, pay, pay, guild_id, user_id),
            )
            # Memorial tithe (1.5% of the win, paid by the house on top — the
            # winner keeps 100% of `pay`). Skips the memorial player.
            if not is_memorial(user_id):
                _memorial_house_tithe(conn, guild_id, pay)
            conn.commit()
            return pay
    except sqlite3.Error as e:
        logger.error(f"Database error in casino_payout: {e}")
        return 0


def refund_from_house(guild_id: int, user_id: int, amount: int) -> int:
    """Undo a transfer_to_house: pay `amount` back from the house to a player
    WITHOUT touching total_won / net_won and without the memorial tithe — this
    is a refund (dissolved lobby, cancelled event), not a win. Draws on-hand
    first, then the reserve, exactly like casino_payout. Returns actual coins
    refunded (0 only if both house buckets are empty, or the player is at the
    MAX_COINS ceiling)."""
    amount = clamp_amount(amount)
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
            house_coins = coins_int(house_row[0] if house_row else 0)
            shortfall = amount - house_coins
            if shortfall > 0:
                reserve_row = conn.execute(
                    "SELECT coins FROM house_reserve WHERE guild_id = ?",
                    (guild_id,),
                ).fetchone()
                reserve_coins = coins_int(reserve_row[0] if reserve_row else 0)
                topup = min(shortfall, reserve_coins)
                if topup > 0:
                    conn.execute(
                        "UPDATE house_reserve SET coins = coins - ? WHERE guild_id = ?",
                        (topup, guild_id),
                    )
                    conn.execute(
                        f"UPDATE wallets SET {_ADD_COINS} WHERE guild_id = ? AND user_id = ?",
                        (topup, guild_id, house_id),
                    )
                    house_coins += topup
            player_row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            affordable = min(amount, max(0, house_coins))
            pay = min(affordable, headroom(player_row[0] if player_row else 0))
            if pay < affordable:
                _record_ceiling_event(conn, guild_id, user_id, affordable, pay, "refund")
            if pay <= 0:
                # Nothing moved, but a logged ceiling strike must survive.
                conn.commit()
                return 0
            conn.execute(
                "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
                (pay, guild_id, house_id),
            )
            conn.execute(
                f"UPDATE wallets SET {_ADD_COINS} WHERE guild_id = ? AND user_id = ?",
                (pay, guild_id, user_id),
            )
            conn.commit()
            return pay
    except sqlite3.Error as e:
        logger.error(f"Database error in refund_from_house: {e}")
        return 0


def _sum_money(conn: sqlite3.Connection, sql: str, params: tuple) -> int:
    """Sum a money column by fetching the rows and adding them up in Python.

    Deliberately NOT `SELECT SUM(col)`: SQLite computes SUM in 64-bit ints and
    silently promotes the result to REAL on overflow, which would make the
    guild-wide totals the binding constraint on MAX_COINS (a guild of N maxed
    wallets would have to stay under 2**63). Python ints are arbitrary
    precision, so the aggregates can never overflow no matter how rich the
    server gets, and the ceiling only has to keep a SINGLE value in range.
    Row counts here are per-guild player counts — summing them costs nothing.
    """
    return sum(coins_int(r[0]) for r in conn.execute(sql, params).fetchall())


def get_house_state(guild_id: int) -> dict:
    """Snapshot of the safe harbor and the on-hand pot. Applies reserve
    interest as a side effect. `banked` is the sum of every player bank
    account — those live in the safe harbor too (earning BANK_INTEREST_APR),
    but they're depositor money, not house money, so they're reported
    separately from `reserve`.
    Returns {'on_hand', 'reserve', 'apr', 'banked', 'bank_apr'}."""
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
            banked = _sum_money(
                conn,
                "SELECT value FROM cog_kv WHERE guild_id=? AND namespace=? AND key=?",
                (guild_id, _BANK_NS, _BANK_KEY))
            conn.commit()
            return {
                "on_hand": coins_int(house_row[0] if house_row else 0),
                "reserve": coins_int(reserve_row[0] if reserve_row else 0),
                "apr": HOUSE_INTEREST_APR,
                "banked": banked,
                "bank_apr": BANK_INTEREST_APR,
            }
    except sqlite3.Error as e:
        logger.error(f"Database error in get_house_state: {e}")
        return {"on_hand": 0, "reserve": 0, "apr": HOUSE_INTEREST_APR,
                "banked": 0, "bank_apr": BANK_INTEREST_APR}


def replenish_house_if_low(guild_id: int) -> dict:
    """Safety net for a near-drained house. If total house funds (on-hand +
    reserve) have fallen below HOUSE_LOW_WATER_PCT of HOUSE_STARTING_COINS, add
    coins to the safe-harbor reserve so the combined total is back at the seed.
    No-op otherwise. Applies reserve interest first (via _normalize_house) so
    the comparison uses current balances. Atomic under BEGIN IMMEDIATE.

    Returns {'replenished': bool, 'added': int, 'on_hand': X, 'reserve': Y}.
    Intended to be called on a schedule (see the house_upkeep cog)."""
    low_water = int(HOUSE_STARTING_COINS * HOUSE_LOW_WATER_PCT)
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _ensure_house_wallet(conn, guild_id)
            _normalize_house(conn, guild_id)
            on_hand = coins_int((conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, get_house_id()),
            ).fetchone() or [0])[0])
            reserve = coins_int((conn.execute(
                "SELECT coins FROM house_reserve WHERE guild_id = ?",
                (guild_id,),
            ).fetchone() or [0])[0])
            total = on_hand + reserve
            added = 0
            if total < low_water:
                added = HOUSE_STARTING_COINS - total
                reserve = coins_int(reserve + added)
                conn.execute(
                    "UPDATE house_reserve SET coins = ? WHERE guild_id = ?",
                    (reserve, guild_id),
                )
            conn.commit()
            return {
                "replenished": added > 0,
                "added": added,
                "on_hand": on_hand,
                "reserve": reserve,
            }
    except sqlite3.Error as e:
        logger.error(f"Database error in replenish_house_if_low: {e}")
        return {"replenished": False, "added": 0, "on_hand": 0, "reserve": 0}


# --- House bankruptcy ------------------------------------------------------
# There is no bet cap, so a big enough win can drain BOTH house buckets and
# still leave the winner short — that's a bankruptcy. casino_payout logs the
# event here; cogs/bankruptcy.py picks it up and settles the debt one of two
# ways: usually the money printer (mint_house_bailout), but a
# BANKRUPTCY_ROB_CHANCE roll instead covers it out of everyone else's bank
# accounts (cover_house_shortfall).

_BANKRUPTCY_NS = "bankruptcy"
_PENDING_KEY = "pending"  # shared key name for every guild-scoped event queue
_BANKRUPTCY_MAX_PENDING = 10  # backstop against a broke house shorting in a loop

BANKRUPTCY_ROB_CHANCE = 0.01  # odds the debt is taken from everyone's banks
                              # instead of minted


# --- Ceiling strikes -------------------------------------------------------
# A payout the MAX_COINS ceiling refused to deliver. The winner is rich enough
# to have broken the storage engine, so the coins stay in the house and
# cogs/coincap.py drains this queue to tell them, publicly, exactly whose fault
# that is. Same guild-scoped pending-list plumbing as bankruptcy events, so no
# game cog needs to know this exists — every path through casino_payout /
# refund_from_house / mint_house_bailout participates for free.
_CEILING_NS = "coincap"
_CEILING_MAX_PENDING = 10


def _record_ceiling_event(conn: sqlite3.Connection, guild_id: int, user_id: int,
                          owed: int, paid: int, source: str):
    """Within an open transaction, log that the coin ceiling swallowed part of
    a payout. `owed` is what the player had coming, `paid` what their wallet
    had room for; the difference is what their hoarding cost them."""
    lost = int(owed) - int(paid)
    if lost <= 0:
        return
    _append_pending_event(conn, guild_id, _CEILING_NS,
                          {"user_id": user_id, "owed": int(owed),
                           "paid": int(paid), "lost": lost, "source": source},
                          _CEILING_MAX_PENDING)


def pop_ceiling_events(guild_id: int) -> list[dict]:
    """Atomically take (and clear) the guild's pending ceiling strikes.
    Each is {"user_id", "owed", "paid", "lost", "source", "ts"}."""
    return _pop_pending_events(guild_id, _CEILING_NS, "pop_ceiling_events")


def _append_pending_event(conn: sqlite3.Connection, guild_id: int, namespace: str,
                          event: dict, max_pending: int):
    """Within an open transaction, append one event to a guild-scoped pending
    list in cog_kv (user_id=0, key `pending`). Silently drops the event once
    the list is `max_pending` long — a backstop against a broken loop filling
    the row forever. A watcher cog drains it with _pop_pending_events."""
    import time as _t
    row = conn.execute(
        "SELECT value FROM cog_kv WHERE guild_id=? AND user_id=0 AND namespace=? AND key=?",
        (guild_id, namespace, _PENDING_KEY),
    ).fetchone()
    try:
        events = json.loads(row[0]) if row and row[0] else []
        if not isinstance(events, list):
            events = []
    except (json.JSONDecodeError, TypeError):
        events = []
    if len(events) >= max_pending:
        return
    events.append({**event, "ts": int(_t.time())})
    conn.execute(
        "INSERT INTO cog_kv (guild_id, user_id, namespace, key, value) VALUES (?,0,?,?,?) "
        "ON CONFLICT(guild_id, user_id, namespace, key) DO UPDATE SET value=excluded.value",
        (guild_id, namespace, _PENDING_KEY, json.dumps(events)),
    )


def _pop_pending_events(guild_id: int, namespace: str, op: str) -> list[dict]:
    """Atomically take (and clear) a guild's pending event list."""
    try:
        with _tx(op) as conn:
            row = conn.execute(
                "SELECT value FROM cog_kv WHERE guild_id=? AND user_id=0 AND namespace=? AND key=?",
                (guild_id, namespace, _PENDING_KEY),
            ).fetchone()
            if not row or not row[0]:
                raise _Abort([])
            conn.execute(
                "DELETE FROM cog_kv WHERE guild_id=? AND user_id=0 AND namespace=? AND key=?",
                (guild_id, namespace, _PENDING_KEY),
            )
            try:
                events = json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                events = []
        return events if isinstance(events, list) else []
    except _Abort as a:
        return a.result
    except sqlite3.Error:
        return []


def _record_bankruptcy_event(conn: sqlite3.Connection, guild_id: int,
                             user_id: int, owed: int, paid: int):
    """Within an open transaction, append one bankruptcy event to the guild's
    pending list. cogs/bankruptcy.py drains the list."""
    _append_pending_event(conn, guild_id, _BANKRUPTCY_NS,
                          {"user_id": user_id, "owed": int(owed), "paid": int(paid)},
                          _BANKRUPTCY_MAX_PENDING)


def pop_bankruptcy_events(guild_id: int) -> list[dict]:
    """Atomically take (and clear) the guild's pending bankruptcy events.
    Each is {"user_id", "owed", "paid", "ts"}. Empty list if none."""
    return _pop_pending_events(guild_id, _BANKRUPTCY_NS, "pop_bankruptcy_events")


def cover_house_shortfall(guild_id: int, winner_id: int, shortfall: int) -> dict:
    """Emergency bankruptcy cover: seize an equal percentage of EVERY player
    bank account (the winner's own and the memorial player's excepted) into the
    house on-hand, then pay the winner what they're still owed. The percentage
    is exactly what's needed to cover the shortfall, capped at 100% — this is
    the one deliberately uncapped drain in the economy, and it only fires when
    someone has already emptied both house buckets. Atomic.

    Returns {"pct", "seized", "accounts", "paid", "still_short"}.
    """
    shortfall = clamp_amount(shortfall)
    out = {"pct": 0.0, "seized": 0, "accounts": 0, "paid": 0,
           "still_short": shortfall}
    if shortfall <= 0:
        return out
    house_id = get_house_id()
    try:
        with _tx("cover_house_shortfall") as conn:
            conn.execute(
                "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, 0)",
                (guild_id, house_id),
            )
            rows = conn.execute(
                "SELECT user_id FROM cog_kv "
                "WHERE guild_id=? AND namespace=? AND key=? AND value > 0",
                (guild_id, _BANK_NS, _BANK_KEY),
            ).fetchall()
            balances = []
            total_banked = 0
            for (uid,) in rows:
                if uid == winner_id or is_memorial(uid):
                    continue
                bal = _accrue_bank_interest(conn, guild_id, uid)
                if bal > 0:
                    balances.append((uid, bal))
                    total_banked += bal
            pct = min(1.0, shortfall / total_banked) if total_banked > 0 else 0.0
            seized = 0
            accounts = 0
            for uid, bal in balances:
                take = bal if pct >= 1.0 else int(bal * pct)
                if take <= 0:
                    continue
                conn.execute(
                    "UPDATE cog_kv SET value = value - ? "
                    "WHERE guild_id=? AND user_id=? AND namespace=? AND key=?",
                    (take, guild_id, uid, _BANK_NS, _BANK_KEY),
                )
                seized += take
                accounts += 1
            if seized > 0:
                conn.execute(
                    f"UPDATE wallets SET {_ADD_COINS} WHERE guild_id = ? AND user_id = ?",
                    (seized, guild_id, house_id),
                )
            conn.execute(
                "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, ?)",
                (guild_id, winner_id, STARTING_COINS),
            )
            house_row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, house_id),
            ).fetchone()
            winner_row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, winner_id),
            ).fetchone()
            pay = min(shortfall,
                      coins_int(house_row[0] if house_row else 0),
                      headroom(winner_row[0] if winner_row else 0))
            if pay > 0:
                conn.execute(
                    "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
                    (pay, guild_id, house_id),
                )
                conn.execute(
                    f"UPDATE wallets SET {_ADD_COINS}, {_ADD_TOTAL_WON}, "
                    f"{_ADD_NET_WON} WHERE guild_id = ? AND user_id = ?",
                    (pay, pay, pay, guild_id, winner_id),
                )
            out = {"pct": pct, "seized": seized, "accounts": accounts,
                   "paid": pay, "still_short": shortfall - pay}
        return out
    except sqlite3.Error:
        return out


def mint_house_bailout(guild_id: int, winner_id: int, amount: int) -> int:
    """Settle a bankruptcy debt with the money printer: mint `amount` fresh
    coins straight into the winner's wallet (with the total_won/net_won bumps a
    casino win gets — this IS their winnings, just inflation-funded). This is
    deliberate money creation, same class as replenish_house_if_low. Atomic.
    Returns the coins actually minted (== amount unless the winner's wallet is
    at the MAX_COINS ceiling, or 0 on bad input / DB error)."""
    amount = clamp_amount(amount)
    if amount <= 0:
        return 0
    try:
        with _tx("mint_house_bailout") as conn:
            conn.execute(
                "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, ?)",
                (guild_id, winner_id, STARTING_COINS),
            )
            row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, winner_id),
            ).fetchone()
            room = min(amount, headroom(row[0] if row else 0))
            if room < amount:
                # Don't _Abort on a fully-capped bailout: that would roll back
                # the strike we just logged. Commit the event, mint nothing.
                _record_ceiling_event(conn, guild_id, winner_id, amount, room, "bailout")
            amount = room
            if amount <= 0:
                return 0
            conn.execute(
                f"UPDATE wallets SET {_ADD_COINS}, {_ADD_TOTAL_WON}, "
                f"{_ADD_NET_WON} WHERE guild_id = ? AND user_id = ?",
                (amount, amount, amount, guild_id, winner_id),
            )
        return amount
    except sqlite3.Error:
        return 0


# --- Generic key-value store ----------------------------------------------
# One table (`cog_kv`) holds every bit of per-(guild,user) state that isn't a
# core economy concept: inventory, and whatever future cogs need. A cog picks
# a `namespace` and stores under it — no new table, no
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


def kv_claim(guild_id: int, user_id: int, namespace: str, key: str, value) -> bool:
    """Atomically set `key` only if it is not already present. Returns True if
    this call created it (the first claim), False if it already existed.

    For one-shot awards (achievement unlocks) this makes granting idempotent
    even when two events race to award the same thing — only the first wins, so
    the caller pays the reward exactly once."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                "INSERT OR IGNORE INTO cog_kv (guild_id, user_id, namespace, key, value) "
                "VALUES (?,?,?,?,?)",
                (guild_id, user_id, namespace, key, value),
            )
            inserted = cur.rowcount == 1
            conn.commit()
            return inserted
    except sqlite3.Error as e:
        logger.error(f"Database error in kv_claim: {e}")
        return False


def kv_all_in_namespace(guild_id: int, namespace: str) -> dict:
    """Every player's keys in a namespace for one guild, as
    {user_id: {key: value}}. Used for guild-wide rollups (e.g. an achievement
    leaderboard) where per-user kv_get_all would mean one query per member."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            rows = conn.execute(
                "SELECT user_id, key, value FROM cog_kv WHERE guild_id=? AND namespace=?",
                (guild_id, namespace),
            ).fetchall()
            out: dict = {}
            for user_id, key, value in rows:
                out.setdefault(user_id, {})[key] = value
            return out
    except sqlite3.Error as e:
        logger.error(f"Database error in kv_all_in_namespace: {e}")
        return {}


def kv_incr(guild_id: int, user_id: int, namespace: str, key: str, by: int = 1):
    """Atomically add `by` to a numeric value (an unset key counts as 0) and
    return the new total. `by` may be negative.

    Saturates at ±MAX_COINS: cog counters have no business anywhere near the
    64-bit edge, where SQLite would silently turn the value into a float."""
    by = _signed_int(by)
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO cog_kv (guild_id, user_id, namespace, key, value) VALUES (?,?,?,?,?) "
                "ON CONFLICT(guild_id, user_id, namespace, key) DO UPDATE SET "
                f"value = MAX(-{MAX_COINS}, MIN(value + ?, {MAX_COINS}))",
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


def kv_top(guild_id: int, namespace: str, key: str, limit: int = 10) -> list[tuple[int, int]]:
    """Top users by numeric value for one (namespace, key) — [(user_id, value)]
    descending. Guild-scoped rows (user_id=0) are excluded; they're aggregates,
    not people. The cross-user leaderboard query cogs can't do themselves."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            rows = conn.execute(
                "SELECT user_id, CAST(value AS INTEGER) AS v FROM cog_kv "
                "WHERE guild_id=? AND namespace=? AND key=? AND user_id != 0 "
                "ORDER BY v DESC LIMIT ?",
                (guild_id, namespace, key, limit),
            ).fetchall()
            return [(r[0], int(r[1])) for r in rows]
    except sqlite3.Error as e:
        logger.error(f"Database error in kv_top: {e}")
        return []


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
        with _tx("consume_item") as conn:
            row = conn.execute(
                "SELECT value FROM cog_kv WHERE guild_id=? AND user_id=? AND namespace=? AND key=?",
                (guild_id, user_id, _INV_NS, item),
            ).fetchone()
            have = row[0] if row else 0
            if have < qty:
                raise _Abort(False)
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
        return True
    except _Abort as a:
        return a.result
    except sqlite3.Error:
        return False


def item_qty(guild_id: int, user_id: int, item: str) -> int:
    """How many of `item` a player holds."""
    return int(kv_get(guild_id, user_id, _INV_NS, item, 0) or 0)


def get_inventory(guild_id: int, user_id: int) -> dict:
    """Returns {item: qty} for every item the player holds (qty > 0)."""
    return {k: v for k, v in kv_get_all(guild_id, user_id, _INV_NS).items() if v > 0}


# --- Player bank ------------------------------------------------------------
# A per-player vault built on cog_kv (namespace "bank", key "balance"). Coins
# deposited here leave the wallet, so PvP heists — which only ever see wallet
# `coins` — can't touch them. The flip side: banked coins can't be gambled
# (every game reads the wallet), and the bank sits INSIDE the casino, so when
# someone successfully robs the HOUSE they also crack the safe-deposit boxes
# and skim a rolled cut of every account (bank_raid). Hitting the boxes is its
# own rare heist outcome (1 in 1,000 boxes-only, 1 in 5,000 for vault AND
# boxes — odds live in cogs/heist.py). Bounded-drain policy, same as the house
# buckets: the skim is capped at BANK_RAID_MAX_PCT.
# Deposits/withdrawals move money 1:1 between wallet and bank — nothing is
# minted or destroyed, and no win/loss stats change.
# Accounts sit in the safe harbor alongside the house reserve, and like the
# reserve they earn interest: BANK_INTEREST_APR, compounded lazily on read
# (the interest itself is minted, same as reserve interest). The house earns
# HOUSE_INTEREST_APR (15%); depositors earn BANK_INTEREST_APR (10%) — the
# house always out-earns its customers.
_BANK_NS = "bank"
_BANK_KEY = "balance"
_BANK_TS_KEY = "interest_ts"
BANK_INTEREST_APR = 0.10
BANK_RAID_MIN_PCT = 0.0
BANK_RAID_MAX_PCT = 0.40


def _accrue_bank_interest(conn: sqlite3.Connection, guild_id: int, user_id: int) -> int:
    """Within an open BEGIN IMMEDIATE transaction, apply lazily-compounded
    interest to one bank account and return the post-accrual balance.

    Same APR math as _normalize_house, with one difference: the clock only
    advances when at least one whole coin has accrued. The reserve is huge so
    truncation there is noise, but a small player balance read frequently
    would round every sub-coin gain down to zero and never grow — so here a
    read that accrues less than a coin leaves the timestamp alone and the
    gain keeps compounding until it clears 1."""
    import time as _t
    now = _t.time()
    row = conn.execute(
        "SELECT value FROM cog_kv WHERE guild_id=? AND user_id=? AND namespace=? AND key=?",
        (guild_id, user_id, _BANK_NS, _BANK_KEY),
    ).fetchone()
    balance = coins_int(row[0] if row else 0)
    if balance <= 0:
        # Reset any stale clock so a later deposit can't back-accrue across
        # the empty period. UPDATE only — don't create rows for non-customers.
        conn.execute(
            "UPDATE cog_kv SET value=? WHERE guild_id=? AND user_id=? AND namespace=? AND key=?",
            (now, guild_id, user_id, _BANK_NS, _BANK_TS_KEY),
        )
        return balance
    ts_row = conn.execute(
        "SELECT value FROM cog_kv WHERE guild_id=? AND user_id=? AND namespace=? AND key=?",
        (guild_id, user_id, _BANK_NS, _BANK_TS_KEY),
    ).fetchone()
    last_ts = float(ts_row[0]) if ts_row and ts_row[0] else 0.0
    if last_ts <= 0 or now <= last_ts:
        # Balance predates interest (or clock skew): start the clock now.
        conn.execute(
            "INSERT INTO cog_kv (guild_id, user_id, namespace, key, value) VALUES (?,?,?,?,?) "
            "ON CONFLICT(guild_id, user_id, namespace, key) DO UPDATE SET value = excluded.value",
            (guild_id, user_id, _BANK_NS, _BANK_TS_KEY, now),
        )
        return balance
    elapsed_years = (now - last_ts) / _SECONDS_PER_YEAR
    grown = _grow(balance, BANK_INTEREST_APR, elapsed_years)
    if grown <= balance:
        return balance  # sub-coin gain: leave the clock running
    conn.execute(
        "UPDATE cog_kv SET value=? WHERE guild_id=? AND user_id=? AND namespace=? AND key=?",
        (grown, guild_id, user_id, _BANK_NS, _BANK_KEY),
    )
    conn.execute(
        "UPDATE cog_kv SET value=? WHERE guild_id=? AND user_id=? AND namespace=? AND key=?",
        (now, guild_id, user_id, _BANK_NS, _BANK_TS_KEY),
    )
    return grown


def bank_balance(guild_id: int, user_id: int) -> int:
    """Coins a player has parked in the bank (interest applied on read)."""
    try:
        with _tx("bank_balance") as conn:
            balance = _accrue_bank_interest(conn, guild_id, user_id)
        return balance
    except sqlite3.Error:
        return coins_int(kv_get(guild_id, user_id, _BANK_NS, _BANK_KEY, 0))


def bank_deposit(guild_id: int, user_id: int, amount: int) -> dict:
    """Atomically move coins from a player's wallet into their bank account.

    Returns:
      {"ok": True, "wallet": X, "bank": Y, "amount": moved}
      {"ok": False, "error": "invalid_amount"}
      {"ok": False, "error": "broke", "have": X, "need": amount}
      {"ok": False, "error": "capped"}   # account is already at MAX_COINS
      {"ok": False, "error": "db"}

    The deposit is trimmed to the account's remaining headroom under MAX_COINS
    so the ceiling can't eat coins on the way in.
    """
    amount = clamp_amount(amount)
    if amount <= 0:
        return {"ok": False, "error": "invalid_amount"}
    import time as _t
    try:
        with _tx("bank_deposit") as conn:
            banked = _accrue_bank_interest(conn, guild_id, user_id)
            conn.execute(
                "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, ?)",
                (guild_id, user_id, STARTING_COINS),
            )
            row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            have = coins_int(row[0] if row else 0)
            if have < amount:
                raise _Abort({"ok": False, "error": "broke", "have": have, "need": amount})
            amount = min(amount, headroom(banked))
            if amount <= 0:
                raise _Abort({"ok": False, "error": "capped", "have": banked})
            conn.execute(
                "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
                (amount, guild_id, user_id),
            )
            conn.execute(
                "INSERT INTO cog_kv (guild_id, user_id, namespace, key, value) VALUES (?,?,?,?,?) "
                f"ON CONFLICT(guild_id, user_id, namespace, key) DO UPDATE SET {_ADD_KV_VALUE}",
                (guild_id, user_id, _BANK_NS, _BANK_KEY, amount, amount),
            )
            # First deposit starts the interest clock (no-op if it's running —
            # _accrue_bank_interest already reset it when the account was empty).
            conn.execute(
                "INSERT INTO cog_kv (guild_id, user_id, namespace, key, value) VALUES (?,?,?,?,?) "
                "ON CONFLICT(guild_id, user_id, namespace, key) DO NOTHING",
                (guild_id, user_id, _BANK_NS, _BANK_TS_KEY, _t.time()),
            )
        return {"ok": True, "wallet": have - amount, "bank": banked + amount,
                "amount": amount}
    except _Abort as a:
        return a.result
    except sqlite3.Error:
        return {"ok": False, "error": "db"}


def bank_withdraw(guild_id: int, user_id: int, amount: int) -> dict:
    """Atomically move coins from a player's bank account back to their wallet.
    Same return shape as bank_deposit; "broke" means the BANK is short, and
    "capped" means the wallet is already at MAX_COINS."""
    amount = clamp_amount(amount)
    if amount <= 0:
        return {"ok": False, "error": "invalid_amount"}
    try:
        with _tx("bank_withdraw") as conn:
            banked = _accrue_bank_interest(conn, guild_id, user_id)
            if banked < amount:
                raise _Abort({"ok": False, "error": "broke", "have": banked, "need": amount})
            conn.execute(
                "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, ?)",
                (guild_id, user_id, STARTING_COINS),
            )
            have_row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            amount = min(amount, headroom(have_row[0] if have_row else 0))
            if amount <= 0:
                raise _Abort({"ok": False, "error": "capped", "have": banked})
            conn.execute(
                "UPDATE cog_kv SET value = value - ? "
                "WHERE guild_id=? AND user_id=? AND namespace=? AND key=?",
                (amount, guild_id, user_id, _BANK_NS, _BANK_KEY),
            )
            conn.execute(
                f"UPDATE wallets SET {_ADD_COINS} WHERE guild_id = ? AND user_id = ?",
                (amount, guild_id, user_id),
            )
            wallet_row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
        return {"ok": True, "wallet": coins_int(wallet_row[0] if wallet_row else amount),
                "bank": banked - amount, "amount": amount}
    except _Abort as a:
        return a.result
    except sqlite3.Error:
        return {"ok": False, "error": "db"}


def get_all_bank_balances(guild_id: int) -> list[tuple[int, int]]:
    """Every (user_id, balance) with coins in the bank, largest first.
    Applies each account's accrued interest as a side effect."""
    try:
        with _tx("get_all_bank_balances") as conn:
            rows = conn.execute(
                "SELECT user_id FROM cog_kv "
                "WHERE guild_id=? AND namespace=? AND key=? AND value > 0",
                (guild_id, _BANK_NS, _BANK_KEY),
            ).fetchall()
            balances = [(uid, _accrue_bank_interest(conn, guild_id, uid)) for (uid,) in rows]
        return sorted(balances, key=lambda b: b[1], reverse=True)
    except sqlite3.Error:
        return []


def bank_raid(guild_id: int, thief_id: int, pct: float) -> dict:
    """The house just got robbed — the safe-deposit boxes get cracked too.
    Atomically skim `pct` of EVERY player bank account (the thief's own and the
    memorial player's excepted) and credit the total to the thief's wallet.
    Pure player↔player transfer: no total_won/net_won bumps, nothing minted.

    `pct` is clamped to [0, BANK_RAID_MAX_PCT] — callers roll it within
    [BANK_RAID_MIN_PCT, BANK_RAID_MAX_PCT] (see cogs/heist.py).

    Returns {"total": coins_taken, "accounts": how_many_accounts_hit}.
    """
    pct = max(0.0, min(pct, BANK_RAID_MAX_PCT))
    if pct <= 0:
        return {"total": 0, "accounts": 0}
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT user_id, value FROM cog_kv "
                "WHERE guild_id=? AND namespace=? AND key=? AND value > 0",
                (guild_id, _BANK_NS, _BANK_KEY),
            ).fetchall()
            total = 0
            accounts = 0
            for uid, balance in rows:
                if uid == thief_id or is_memorial(uid):
                    continue
                # Interest accrues up to the moment the boxes crack — the raid
                # skims the fully-grown balance.
                balance = _accrue_bank_interest(conn, guild_id, uid)
                take = clamp_amount(balance * pct)
                if take <= 0:
                    continue
                conn.execute(
                    "UPDATE cog_kv SET value = value - ? "
                    "WHERE guild_id=? AND user_id=? AND namespace=? AND key=?",
                    (take, guild_id, uid, _BANK_NS, _BANK_KEY),
                )
                total += take
                accounts += 1
            if total > 0:
                conn.execute(
                    "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, ?)",
                    (guild_id, thief_id, STARTING_COINS),
                )
                conn.execute(
                    f"UPDATE wallets SET {_ADD_COINS} WHERE guild_id = ? AND user_id = ?",
                    (total, guild_id, thief_id),
                )
            conn.commit()
            return {"total": total, "accounts": accounts}
    except sqlite3.Error as e:
        logger.error(f"Database error in bank_raid: {e}")
        return {"total": 0, "accounts": 0}


def bank_seize_to_house(guild_id: int, user_id: int, amount: int) -> int:
    """Enforcement reaching into the vault: atomically move up to `amount` from
    a player's bank straight to the house on-hand. Used by tax enforcement so
    parking coins in the bank isn't a way to dodge a seizure. Returns the coins
    actually moved (0 if the account is empty)."""
    amount = clamp_amount(amount)
    if amount <= 0:
        return 0
    try:
        with _tx("bank_seize_to_house") as conn:
            banked = _accrue_bank_interest(conn, guild_id, user_id)
            take = min(amount, banked)
            if take <= 0:
                raise _Abort(0)
            conn.execute(
                "UPDATE cog_kv SET value = value - ? "
                "WHERE guild_id=? AND user_id=? AND namespace=? AND key=?",
                (take, guild_id, user_id, _BANK_NS, _BANK_KEY),
            )
            _ensure_house_wallet(conn, guild_id)
            conn.execute(
                f"UPDATE wallets SET {_ADD_COINS} WHERE guild_id = ? AND user_id = ?",
                (take, guild_id, get_house_id()),
            )
        return take
    except _Abort as a:
        return a.result
    except sqlite3.Error:
        return 0


def burn_purchase(guild_id: int, user_id: int, amount: int, namespace: str,
                  increments: list[tuple[str, int]]) -> dict:
    """Destroy `amount` coins from a wallet and bump cog_kv counters, atomically.

    The buy-a-sink primitive: coins go to the VOID (not the house — nothing is
    minted or transferred anywhere), and the counters that record the purchase
    move in the same transaction, so a player can never be charged without
    getting credited or vice versa. `increments` is [(key, delta), ...] in
    `namespace`, e.g. [("owned:gold_toilet", 1), ("total_burned", 12_000_000)].

    Deliberately generic — any future "spend coins to permanently record
    something" sink should use this rather than composing try_deduct + kv_incr
    and hoping the process doesn't die between them.

    Returns:
      {"ok": True, "spent": X, "balance": Y, "counters": {key: new_value}}
      {"ok": False, "error": "invalid_amount"}
      {"ok": False, "error": "broke", "have": X, "need": amount}
      {"ok": False, "error": "db"}
    """
    amount = clamp_amount(amount)
    if amount <= 0:
        return {"ok": False, "error": "invalid_amount"}
    try:
        with _tx("burn_purchase") as conn:
            conn.execute(
                "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, ?)",
                (guild_id, user_id, STARTING_COINS),
            )
            row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            have = coins_int(row[0] if row else 0)
            if have < amount:
                raise _Abort({"ok": False, "error": "broke", "have": have,
                              "need": amount})
            conn.execute(
                f"UPDATE wallets SET coins = coins - ?, {_ADD_TOTAL_LOST} "
                "WHERE guild_id = ? AND user_id = ?",
                (amount, amount, guild_id, user_id),
            )
            counters = {}
            for key, delta in increments:
                conn.execute(
                    "INSERT INTO cog_kv (guild_id, user_id, namespace, key, value) "
                    "VALUES (?,?,?,?,?) ON CONFLICT(guild_id, user_id, namespace, key) "
                    f"DO UPDATE SET value = MAX(-{MAX_COINS}, MIN(value + ?, {MAX_COINS}))",
                    (guild_id, user_id, namespace, key, _signed_int(delta),
                     _signed_int(delta)),
                )
                new_row = conn.execute(
                    "SELECT value FROM cog_kv WHERE guild_id=? AND user_id=? "
                    "AND namespace=? AND key=?",
                    (guild_id, user_id, namespace, key),
                ).fetchone()
                counters[key] = _signed_int(new_row[0] if new_row else delta)
        return {"ok": True, "spent": amount, "balance": have - amount,
                "counters": counters}
    except _Abort as a:
        return a.result
    except sqlite3.Error:
        return {"ok": False, "error": "db"}


# --- House profit sharing ---------------------------------------------------
# The Tier 7 splurge "Buy Into the House" (splurges.py) is the one purchase in
# the catalog that isn't cosmetic. A buyer becomes a SHAREHOLDER:
#
#   * They draw a dividend from house PROFIT. HOUSE_PROFIT_SHARE_PCT of every
#     new coin of profit the house makes is split among shareholders pro-rata
#     by shares held. Buy the only share and you take the whole 25%; when
#     somebody else buys in, you're diluted. That's what buying in means.
#   * They CANNOT PLAY. Every bet a shareholder tries to place is refused.
#     You're on the other side of the table now — that's the trade.
#
# Profit is measured against a HIGH-WATER MARK, exactly like a real
# profit-share: only growth above the best the house has ever done (after
# previous dividends) pays out. A losing streak pays nothing and must be
# earned back before dividends resume — there is no clawback and no dividend
# on a house that is merely recovering.
#
# That high-water rule is what makes this safe where a cut of TURNOVER was
# not: dividends can only ever come out of money the house actually made, so
# shareholders can never drive the house into a structural loss no matter how
# many shares exist or how heavily the tables are played.
#
# Dividends settle on a poll (cogs/dividends.py); nothing happens on the hot
# bet path beyond the shareholder bet-refusal check.
HOUSE_PROFIT_SHARE_PCT = 0.25

_SHARES_NS = "splurge"              # shares the splurge cog's namespace
# Deliberately the SAME cog_kv row the splurge catalog credits when someone
# buys the item ("owned:" + splurges.SHARES_KEY) rather than a parallel
# counter — one row means share count and inventory can never drift apart.
# A test pins the two module constants together.
SHARES_KEY = "owned:house_share"
_PROFIT_HWM_KEY = "profit_highwater"  # guild-scoped (user_id=0)


def house_shares(guild_id: int, user_id: int) -> int:
    """How many house shares this player holds."""
    try:
        return max(0, int(kv_get(guild_id, user_id, _SHARES_NS, SHARES_KEY, 0) or 0))
    except (TypeError, ValueError):
        return 0


def is_shareholder(guild_id: int, user_id: int) -> bool:
    """True if this player holds any house share (and so may not gamble)."""
    return house_shares(guild_id, user_id) > 0


def get_shareholders(guild_id: int) -> list[tuple[int, int]]:
    """Every (user_id, shares) holder in the guild, largest stake first."""
    rows = kv_top(guild_id, _SHARES_NS, SHARES_KEY, limit=1000)
    return [(uid, int(n)) for uid, n in rows if int(n) > 0]


def total_house_shares(guild_id: int) -> int:
    """Shares outstanding — the denominator every dividend is split by."""
    return sum(n for _, n in get_shareholders(guild_id))


def casino_ban_message(guild_id: int, user_id: int) -> str | None:
    """Standard "you're on the house's side of the table" gate, or None if the
    player is free to bet. Call it right next to jail_message at the top of any
    casino command — game_common.casino_prelude already does for every cog
    built on it, and transfer_to_house refuses shareholder bets as a hard
    backstop."""
    shares = house_shares(guild_id, user_id)
    if shares <= 0:
        return None
    total = total_house_shares(guild_id)
    pct = (shares / total * HOUSE_PROFIT_SHARE_PCT * 100) if total else 0
    return ("🏛️ **You own a piece of the house.** Shareholders don't gamble "
            "against their own casino — you don't get to play anymore.\n"
            f"You hold **{shares}** of **{total}** share(s), drawing "
            f"**{pct:.1f}%** of house profit instead. That was the deal.")


def _house_total(conn: sqlite3.Connection, guild_id: int) -> int:
    """On-hand + reserve, read inside an open transaction."""
    on_hand = conn.execute(
        "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
        (guild_id, get_house_id()),
    ).fetchone()
    reserve = conn.execute(
        "SELECT coins FROM house_reserve WHERE guild_id = ?", (guild_id,)
    ).fetchone()
    return coins_int(on_hand[0] if on_hand else 0) + coins_int(reserve[0] if reserve else 0)


def settle_house_dividends(guild_id: int) -> dict:
    """Pay shareholders their cut of any NEW house profit. Atomic; idempotent
    in the sense that calling it twice in a row pays nothing the second time.

    Profit is house funds (on-hand + reserve) above the high-water mark. We
    pay HOUSE_PROFIT_SHARE_PCT of that growth, pro-rata by shares, out of
    house on-hand, then set the mark to the post-dividend total so the same
    profit is never paid twice. A house below its mark pays nothing and the
    mark does not move.

    Returns {"paid": total, "profit": gain, "payouts": [(user_id, coins)],
             "shares": outstanding, "high_water": new_mark, "baseline": bool}.
    `baseline` is True on the first call after shares exist, when the mark is
    simply initialised — profit made before anyone bought in isn't theirs.
    """
    empty = {"paid": 0, "profit": 0, "payouts": [], "shares": 0,
             "high_water": 0, "baseline": False}
    holders = get_shareholders(guild_id)
    if not holders:
        return empty
    outstanding = sum(n for _, n in holders)
    try:
        with _tx("settle_house_dividends") as conn:
            _ensure_house_wallet(conn, guild_id)
            _normalize_house(conn, guild_id)
            total = _house_total(conn, guild_id)
            mark_row = conn.execute(
                "SELECT value FROM cog_kv WHERE guild_id=? AND user_id=0 "
                "AND namespace=? AND key=?",
                (guild_id, _SHARES_NS, _PROFIT_HWM_KEY),
            ).fetchone()

            def set_mark(value):
                conn.execute(
                    "INSERT INTO cog_kv (guild_id, user_id, namespace, key, value) "
                    "VALUES (?,0,?,?,?) ON CONFLICT(guild_id, user_id, namespace, key) "
                    "DO UPDATE SET value = excluded.value",
                    (guild_id, _SHARES_NS, _PROFIT_HWM_KEY, int(value)),
                )

            if mark_row is None or mark_row[0] is None:
                # First settle after the first buy-in: start the clock here so
                # profit the house made before anyone invested isn't paid out.
                set_mark(total)
                return {**empty, "shares": outstanding, "high_water": total,
                        "baseline": True}

            mark = coins_int(mark_row[0])
            gain = total - mark
            if gain <= 0:
                return {**empty, "shares": outstanding, "high_water": mark}

            pool = int(gain * HOUSE_PROFIT_SHARE_PCT)
            house_id = get_house_id()
            on_hand_row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, house_id),
            ).fetchone()
            pool = min(pool, coins_int(on_hand_row[0] if on_hand_row else 0))
            if pool <= 0:
                return {**empty, "shares": outstanding, "high_water": mark,
                        "profit": gain}

            payouts = []
            paid_total = 0
            for uid, shares in holders:
                cut = pool * shares // outstanding
                if cut <= 0:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) "
                    "VALUES (?, ?, 0)", (guild_id, uid),
                )
                holder_row = conn.execute(
                    "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                    (guild_id, uid),
                ).fetchone()
                cut = min(cut, headroom(holder_row[0] if holder_row else 0))
                if cut <= 0:
                    continue
                conn.execute(
                    "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
                    (cut, guild_id, house_id),
                )
                conn.execute(
                    f"UPDATE wallets SET {_ADD_COINS}, {_ADD_TOTAL_WON} "
                    "WHERE guild_id = ? AND user_id = ?",
                    (cut, cut, guild_id, uid),
                )
                payouts.append((uid, cut))
                paid_total += cut

            # Mark moves by what was ACTUALLY paid — integer division and
            # ceiling clamps can leave a few coins in the house, and those
            # stay profit rather than being silently forgiven.
            new_mark = total - paid_total
            set_mark(new_mark)
            return {"paid": paid_total, "profit": gain, "payouts": payouts,
                    "shares": outstanding, "high_water": new_mark,
                    "baseline": False}
    except _Abort as a:
        return a.result
    except sqlite3.Error:
        return empty


def get_wealth(guild_id: int, user_id: int) -> int:
    """Wallet + bank total for one player (applies accrued bank interest as a
    side effect). The basis for wealth-scaled punishments — heist bail and
    fines — so parking everything in the bank doesn't shrink a 25%-of-what-
    you-have penalty down to 25% of an empty wallet."""
    return get_coins(guild_id, user_id) + bank_balance(guild_id, user_id)


def fine_user_wealth(guild_id: int, user_id: int, amount: int) -> int:
    """A fine that reaches into the bank: destroy up to `amount` coins, wallet
    first, then the player's bank account (interest applied before the take).
    Same money-sink semantics as fine_user, just bank-aware — banking is not a
    way to dodge a heist fine. Atomic. Returns the coins actually collected."""
    if amount <= 0:
        return 0
    try:
        with _tx("fine_user_wealth") as conn:
            row = conn.execute(
                "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            wallet = row[0] if row else 0
            from_wallet = min(int(amount), max(0, wallet))
            if from_wallet > 0:
                conn.execute(
                    "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
                    (from_wallet, guild_id, user_id),
                )
            remaining = int(amount) - from_wallet
            from_bank = 0
            if remaining > 0:
                banked = _accrue_bank_interest(conn, guild_id, user_id)
                from_bank = min(remaining, banked)
                if from_bank > 0:
                    conn.execute(
                        "UPDATE cog_kv SET value = value - ? "
                        "WHERE guild_id=? AND user_id=? AND namespace=? AND key=?",
                        (from_bank, guild_id, user_id, _BANK_NS, _BANK_KEY),
                    )
        return from_wallet + from_bank
    except sqlite3.Error:
        return 0


def release_from_jail(guild_id: int, user_id: int) -> dict:
    """Try to clear a player's jail sentence — the Get Out of Jail Free card.

    Returns a dict:
      {"released": True}                 — was jailed, now sprung
      {"released": False, "blocked": True}   — jailed on a no_release sentence
                                               (repeat tax evasion); card no-op
      {"released": False, "blocked": False}  — wasn't actually jailed

    A blocked sentence is left fully intact so the caller can refund the card."""
    import time as _t
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT until_ts, no_release FROM jail WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            jailed = bool(row and row[0] > _t.time())
            if jailed and row[1]:
                conn.rollback()
                return {"released": False, "blocked": True}
            conn.execute(
                "DELETE FROM jail WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            conn.commit()
            return {"released": jailed, "blocked": False}
    except sqlite3.Error as e:
        logger.error(f"Database error in release_from_jail: {e}")
        return {"released": False, "blocked": False}


def adjust_jail_sentence(guild_id: int, user_id: int, delta_seconds: int) -> dict:
    """Atomically shift a jailed user's release deadline by delta_seconds
    (negative shortens, positive extends). If the new deadline lands at or
    before now, the sentence is cleared (released). Preserves the row's
    reason / bail_amount / channel_id — only until_ts changes.

    Returns {'ok': bool, 'released': bool, 'remaining': int}:
      - ok False       → the user wasn't actively jailed; nothing changed.
      - released True   → the shift dropped them to freedom (row deleted).
      - remaining       → seconds left after the change (0 if released).

    The memorial player is never jailed, so this is naturally a no-op for him.
    Used by /jailbreak to extend or shorten a sentence in one transaction
    rather than composing release_from_jail + jail_user non-atomically."""
    import time as _t
    now = _t.time()
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT until_ts FROM jail WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            if not row or row[0] <= now:
                conn.rollback()
                return {"ok": False, "released": False, "remaining": 0}
            new_until = row[0] + delta_seconds
            if new_until <= now:
                conn.execute(
                    "DELETE FROM jail WHERE guild_id = ? AND user_id = ?",
                    (guild_id, user_id),
                )
                conn.commit()
                return {"ok": True, "released": True, "remaining": 0}
            conn.execute(
                "UPDATE jail SET until_ts = ? WHERE guild_id = ? AND user_id = ?",
                (new_until, guild_id, user_id),
            )
            conn.commit()
            return {"ok": True, "released": False, "remaining": int(new_until - now)}
    except sqlite3.Error as e:
        logger.error(f"Database error in adjust_jail_sentence: {e}")
        return {"ok": False, "released": False, "remaining": 0}


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
    payments = [(uid, clamp_amount(amt)) for uid, amt in payments]
    if not payments or any(amt <= 0 for _, amt in payments):
        return {"ok": False, "error": "invalid_amount"}
    total = clamp_amount(sum(amt for _, amt in payments))
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
            sender_coins = coins_int(sender_row[0] if sender_row else 0)
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
                    f"UPDATE wallets SET {_ADD_COINS}, {_ADD_TOTAL_WON} "
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
    amount = clamp_amount(amount)
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                f"UPDATE wallets SET {_ADD_COINS}, {_ADD_TOTAL_WON} WHERE guild_id = ? AND user_id = ?",
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


def get_wealth_leaderboard(guild_id: int, limit: int = 10) -> list:
    """Top players by TOTAL wealth (wallet + bank). Excludes the house wallet.
    Accrues each account's bank interest first so banked figures match /bank.
    Returns (user_id, wealth, coins, banked, total_won, total_lost) rows.
    /richest ranks on this; the slots leaderboard and the rank-1 achievement
    stay on the wallet-only get_leaderboard on purpose.

    `wealth` is summed and sorted in PYTHON, not SQL. It's the one money
    expression in the schema with no saturating clamp around it — the credits
    survive an overflow because MIN()/MAX() absorb the promoted REAL, but a
    bare `w.coins + COALESCE(b.value, 0)` has nothing to absorb it and would
    hand /richest a float to print in scientific notation. Doing it here also
    means the ceiling is bounded only by single-value storage, not by
    2 * MAX_COINS."""
    try:
        with _tx("get_wealth_leaderboard") as conn:
            holders = conn.execute(
                "SELECT user_id FROM cog_kv "
                "WHERE guild_id=? AND namespace=? AND key=? AND value > 0",
                (guild_id, _BANK_NS, _BANK_KEY),
            ).fetchall()
            for (uid,) in holders:
                _accrue_bank_interest(conn, guild_id, uid)
            rows = conn.execute(
                "SELECT w.user_id, w.coins, COALESCE(b.value, 0), "
                "w.total_won, w.total_lost "
                "FROM wallets w LEFT JOIN cog_kv b "
                "ON b.guild_id = w.guild_id AND b.user_id = w.user_id "
                "AND b.namespace = ? AND b.key = ? "
                "WHERE w.guild_id = ? AND w.user_id != ?",
                (_BANK_NS, _BANK_KEY, guild_id, get_house_id()),
            ).fetchall()
            ranked = [
                (r[0], coins_int(r[1]) + coins_int(r[2]), coins_int(r[1]),
                 coins_int(r[2]), coins_int(r[3]), coins_int(r[4]))
                for r in rows
            ]
            ranked.sort(key=lambda row: row[1], reverse=True)
            return ranked[:limit]
    except sqlite3.Error as e:
        logger.error(f"Database error getting wealth leaderboard: {e}")
        return []


def get_all_wallets(guild_id: int) -> list:
    """Every (user_id, coins) in the guild EXCLUDING the house wallet. Used by
    the weekly wealth tax to assess every player. The memorial player is left
    in — the caller filters him out (he's exempt from tax)."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            rows = conn.execute(
                "SELECT user_id, coins FROM wallets WHERE guild_id = ? AND user_id != ?",
                (guild_id, get_house_id()),
            ).fetchall()
            return [(r[0], coins_int(r[1])) for r in rows]
    except sqlite3.Error as e:
        logger.error(f"Database error in get_all_wallets: {e}")
        return []


def get_all_winnings(guild_id: int) -> list:
    """Every (user_id, total_won) in the guild EXCLUDING the house wallet. This
    is the lifetime gross-winnings counter; the weekly tax snapshots it and taxes
    the per-period delta. The memorial player is left in — the caller filters
    him out (he's exempt from tax)."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            rows = conn.execute(
                "SELECT user_id, total_won FROM wallets WHERE guild_id = ? AND user_id != ?",
                (guild_id, get_house_id()),
            ).fetchall()
            return [(r[0], coins_int(r[1])) for r in rows]
    except sqlite3.Error as e:
        logger.error(f"Database error in get_all_winnings: {e}")
        return []


def get_winnings(guild_id: int, user_id: int) -> int:
    """Lifetime gross winnings (total_won) for one player. Used by the tax cog to
    roll a baseline forward after enforcement."""
    return int(get_wallet(guild_id, user_id).get("total_won", 0) or 0)


def get_all_net_winnings(guild_id: int) -> list:
    """Every (user_id, net_won) in the guild EXCLUDING the house wallet. net_won
    is lifetime NET gambling profit (payouts minus stakes); the weekly tax
    snapshots it and taxes the positive per-period delta. The memorial player is
    left in — the caller filters him out (he's exempt from tax)."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            rows = conn.execute(
                "SELECT user_id, net_won FROM wallets WHERE guild_id = ? AND user_id != ?",
                (guild_id, get_house_id()),
            ).fetchall()
            return [(r[0], _signed_int(r[1])) for r in rows]
    except sqlite3.Error as e:
        logger.error(f"Database error in get_all_net_winnings: {e}")
        return []


def get_total_economy(guild_id: int) -> int:
    """Sum of all coins across the guild — every player wallet, the house on-hand,
    the house safe-harbor reserve, AND every player bank account. Reserve and
    banked coins are real money even though they aren't heistable, so they count
    toward total circulation."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            wallets_total = _sum_money(
                conn, "SELECT coins FROM wallets WHERE guild_id = ?", (guild_id,))
            reserve_row = conn.execute(
                "SELECT coins FROM house_reserve WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()
            reserve_total = (reserve_row[0] if reserve_row else 0) or 0
            bank_total = _sum_money(
                conn,
                "SELECT value FROM cog_kv WHERE guild_id = ? AND namespace = ? AND key = ?",
                (guild_id, _BANK_NS, _BANK_KEY))
            # Summed in Python: the guild-wide total legitimately exceeds any
            # single wallet's ceiling, and must not be clamped to it.
            return wallets_total + int(reserve_total) + bank_total
    except sqlite3.Error as e:
        logger.error(f"Database error reading total economy: {e}")
        return 0


def get_server_stats(guild_id: int) -> dict:
    """Get aggregate economy stats for a server. Excludes the house (bot) wallet."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            # Money columns are summed in Python (see _sum_money) so a rich
            # server can't overflow the aggregate; spins/jackpots are small
            # counters and stay in SQL.
            rows = conn.execute(
                "SELECT coins, total_won, total_lost, spins, jackpots "
                "FROM wallets WHERE guild_id = ? AND user_id != ?",
                (guild_id, get_house_id())
            ).fetchall()
            banked = _sum_money(
                conn,
                "SELECT value FROM cog_kv WHERE guild_id = ? AND namespace = ? AND key = ?",
                (guild_id, _BANK_NS, _BANK_KEY))
            return {
                "players": len(rows),
                "total_coins": sum(coins_int(r[0]) for r in rows),
                "total_banked": banked,
                "total_won": sum(coins_int(r[1]) for r in rows),
                "total_lost": sum(coins_int(r[2]) for r in rows),
                "total_spins": sum(int(r[3] or 0) for r in rows),
                "total_jackpots": sum(int(r[4] or 0) for r in rows),
            }
    except sqlite3.Error as e:
        logger.error(f"Database error getting server stats: {e}")
        return {"players": 0, "total_coins": 0, "total_banked": 0, "total_won": 0, "total_lost": 0, "total_spins": 0, "total_jackpots": 0}


def get_pot(guild_id: int) -> int:
    """On-hand house coins — the heistable / payout-funded bucket.
    For the full breakdown (on-hand + safe-harbor reserve) call get_house_state."""
    return get_house_state(guild_id)["on_hand"]


def jail_user(guild_id: int, user_id: int, duration_seconds: int, reason: str = "",
              bail_amount: int = 0, channel_id: int = 0, no_release: bool = False):
    """Lock a user out of casino activities for `duration_seconds` from now.
    If already jailed longer, keep the later deadline.
    `bail_amount` and `channel_id` are stored so /bail and the release-message
    loop can find them later. `no_release=True` marks the sentence as one no
    Get Out of Jail Free card can spring (used by repeat tax-evasion jail).

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
                "(guild_id, user_id, until_ts, reason, bail_amount, channel_id, jailed_at, no_release) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (guild_id, user_id, until, reason, int(bail_amount), int(channel_id),
                 now, 1 if no_release else 0),
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
                "SELECT until_ts, reason, bail_amount, channel_id, jailed_at, no_release "
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
                "no_release": bool(row[5]),
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
                f"UPDATE wallets SET {_ADD_COINS} WHERE guild_id = ? AND user_id = ?",
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
                f"UPDATE wallets SET {_ADD_COINS} WHERE guild_id = ? AND user_id = ?",
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
                f"UPDATE wallets SET {_ADD_COINS} WHERE guild_id = ? AND user_id = ?",
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



# --- Admin: hard-reset the economy ----------------------------------------

# Tables wiped by clear_economy(); `game_stats` is deliberately omitted so
# leaderboards (play counts / win counts) survive a reset. Edit this list if
# the caller wants a different blast radius.
_CLEAR_ECONOMY_TABLES = (
    "wallets",
    "jail",
    "cog_kv",          # inventory, any future feature state
    "house_reserve",
    "bounty_log",
    "loot_cooldowns",
)

# cog_kv namespaces that SURVIVE a wipe. These hold permanent, already-earned
# records whose unlock conditions are computed from tables the wipe PRESERVES
# (`game_stats`). Clearing the ledger while the stats that earned it survive
# means every achievement instantly re-qualifies on the next command — a
# channel flood of re-announcements and a re-payment of every reward. Anything
# keyed off preserved state belongs here.
_CLEAR_ECONOMY_KEEP_NAMESPACES = (
    "achievements",
)

_KEEP_NS_CLAUSE = (
    " AND namespace NOT IN (%s)" % ",".join("?" for _ in _CLEAR_ECONOMY_KEEP_NAMESPACES)
    if _CLEAR_ECONOMY_KEEP_NAMESPACES else ""
)


def delete_wallet(guild_id: int, user_id: int) -> dict:
    """Hard-reset ONE player in a guild: deletes their wallet, jail sentence,
    cog_kv state (inventory, tax baseline/bills, any feature flags), loot
    cooldowns, and bounty-log history (as placer or target). PRESERVES their
    game_stats so leaderboards/play counts survive — same policy as
    clear_economy — and, for the same reason, the cog_kv namespaces listed in
    _CLEAR_ECONOMY_KEEP_NAMESPACES (achievements: they were earned off stats
    that survive, so wiping them re-awards the lot on the next command). The
    house pot/reserve is untouched (guild-level, not theirs).

    After this, the next wallet read re-creates them fresh with STARTING_COINS.
    All deletions run in a single transaction. Returns {table: rows_deleted}.

    There is no undo — callers should require human approval before invoking.
    """
    counts: dict[str, int] = {}
    # (table, where-clause, params) — per-user scope.
    deletions = [
        ("wallets", "guild_id = ? AND user_id = ?", (guild_id, user_id)),
        ("jail", "guild_id = ? AND user_id = ?", (guild_id, user_id)),
        ("cog_kv", "guild_id = ? AND user_id = ?" + _KEEP_NS_CLAUSE,
         (guild_id, user_id) + _CLEAR_ECONOMY_KEEP_NAMESPACES),
        ("loot_cooldowns", "guild_id = ? AND user_id = ?", (guild_id, user_id)),
        ("bounty_log",
         "guild_id = ? AND (placer_user_id = ? OR target_user_id = ?)",
         (guild_id, user_id, user_id)),
    ]
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            for tbl, where, params in deletions:
                try:
                    cur = conn.execute(f"DELETE FROM {tbl} WHERE {where}", params)
                    counts[tbl] = cur.rowcount
                except sqlite3.OperationalError:
                    counts[tbl] = 0  # table absent on this DB — skip
            conn.commit()
            return counts
    except sqlite3.Error as e:
        logger.error(f"Database error in delete_wallet: {e}")
        return {}


def clear_economy(guild_id: int) -> dict:
    """Hard-reset the economy for one guild. Wipes wallets, the house pot
    (on-hand + reserve), all jail sentences, the cog_kv store (inventory and
    any cog-owned state), the bounty rate-limit log, and loot cooldowns.
    PRESERVES `game_stats` so leaderboards aren't erased, and the cog_kv
    namespaces in _CLEAR_ECONOMY_KEEP_NAMESPACES (achievement unlocks, which
    are earned off those same surviving stats).

    All deletions run in a single transaction — either every table clears or
    none do. Returns a dict {table_name: rows_deleted}.

    Callers should require human approval before invoking — there is no undo.
    """
    counts: dict[str, int] = {}
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("BEGIN IMMEDIATE")
            for tbl in _CLEAR_ECONOMY_TABLES:
                where, params = "guild_id = ?", (guild_id,)
                if tbl == "cog_kv":
                    where += _KEEP_NS_CLAUSE
                    params += _CLEAR_ECONOMY_KEEP_NAMESPACES
                try:
                    cur = conn.execute(f"DELETE FROM {tbl} WHERE {where}", params)
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
