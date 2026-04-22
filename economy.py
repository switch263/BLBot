"""Shared economy database utilities. All economy cogs import from here."""

import sqlite3
import os
import logging
from config import DATA_DIR

logger = logging.getLogger(__name__)

DB_FILE = os.path.join(DATA_DIR, "economy.db")
STARTING_COINS = 100


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
                    PRIMARY KEY (guild_id, user_id)
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS loot_cooldowns (
                    guild_id INTEGER,
                    user_id INTEGER,
                    last_loot TEXT DEFAULT '',
                    PRIMARY KEY (guild_id, user_id)
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
            ]:
                try:
                    conn.execute(f"ALTER TABLE wallets ADD COLUMN {col} {decl}")
                except sqlite3.OperationalError:
                    pass
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error initializing economy: {e}")


_EMPTY_WALLET = {
    "coins": 0, "total_won": 0, "total_lost": 0, "spins": 0, "jackpots": 0,
    "roulette_plays": 0, "roulette_wins": 0,
    "rr_plays": 0, "rr_wins": 0,
    "heists_attempted": 0, "heists_succeeded": 0,
}


def get_wallet(guild_id: int, user_id: int) -> dict:
    """Get or create a wallet. Returns dict with all stat fields."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, ?)",
                (guild_id, user_id, STARTING_COINS)
            )
            conn.commit()
            cursor = conn.execute(
                "SELECT coins, total_won, total_lost, spins, jackpots, "
                "roulette_plays, roulette_wins, rr_plays, rr_wins, "
                "heists_attempted, heists_succeeded "
                "FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            )
            row = cursor.fetchone()
            return {
                "coins": row[0], "total_won": row[1], "total_lost": row[2],
                "spins": row[3], "jackpots": row[4],
                "roulette_plays": row[5], "roulette_wins": row[6],
                "rr_plays": row[7], "rr_wins": row[8],
                "heists_attempted": row[9], "heists_succeeded": row[10],
            }
    except sqlite3.Error as e:
        logger.error(f"Database error getting wallet: {e}")
        return dict(_EMPTY_WALLET)


def get_coins(guild_id: int, user_id: int) -> int:
    """Get coin balance for a user, creating wallet if needed."""
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


def transfer_coins(guild_id: int, from_id: int, to_id: int, amount: int) -> tuple[int, int]:
    """Transfer coins between users. Returns (sender_balance, receiver_balance)."""
    get_wallet(guild_id, to_id)  # ensure receiver exists
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                "UPDATE wallets SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
                (amount, guild_id, from_id)
            )
            conn.execute(
                "UPDATE wallets SET coins = coins + ? WHERE guild_id = ? AND user_id = ?",
                (amount, guild_id, to_id)
            )
            conn.commit()
            c1 = conn.execute("SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?", (guild_id, from_id)).fetchone()[0]
            c2 = conn.execute("SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?", (guild_id, to_id)).fetchone()[0]
            return c1, c2
    except sqlite3.Error as e:
        logger.error(f"Database error transferring coins: {e}")
        return 0, 0


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
    """Get top players by coins."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.execute(
                "SELECT user_id, coins, total_won, total_lost, spins, jackpots FROM wallets WHERE guild_id = ? ORDER BY coins DESC LIMIT ?",
                (guild_id, limit)
            )
            return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Database error getting leaderboard: {e}")
        return []


def get_server_stats(guild_id: int) -> dict:
    """Get aggregate economy stats for a server."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*), SUM(coins), SUM(total_won), SUM(total_lost), SUM(spins), SUM(jackpots) FROM wallets WHERE guild_id = ?",
                (guild_id,)
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


def record_roulette(guild_id: int, user_id: int, won: bool):
    """Record a casino roulette play and win (if applicable)."""
    get_wallet(guild_id, user_id)
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                "UPDATE wallets SET roulette_plays = roulette_plays + 1, "
                "roulette_wins = roulette_wins + ? WHERE guild_id = ? AND user_id = ?",
                (1 if won else 0, guild_id, user_id)
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error recording roulette play: {e}")


def record_rr(guild_id: int, user_id: int, won: bool):
    """Record a Russian Roulette play and win (if applicable)."""
    get_wallet(guild_id, user_id)
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                "UPDATE wallets SET rr_plays = rr_plays + 1, "
                "rr_wins = rr_wins + ? WHERE guild_id = ? AND user_id = ?",
                (1 if won else 0, guild_id, user_id)
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error recording Russian Roulette play: {e}")


def record_heist(guild_id: int, user_id: int, succeeded: bool):
    """Record a heist attempt and success (if applicable)."""
    get_wallet(guild_id, user_id)
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                "UPDATE wallets SET heists_attempted = heists_attempted + 1, "
                "heists_succeeded = heists_succeeded + ? WHERE guild_id = ? AND user_id = ?",
                (1 if succeeded else 0, guild_id, user_id)
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error recording heist: {e}")


# Initialize DB on import
_init_db()
