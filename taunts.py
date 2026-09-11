"""Hand-written taunts, loaded from data_files — no Discord, no DB.

Pure data + pickers, like items.py. Lives at the repo root so the watcher cog
(cogs/coincap.py), the commands that refuse a move on the spot (gift, bank)
and the paid commands that roast a broke player (game_common.charge_fee) all
insult with the same voice.

Two pools:
  ceiling_taunt() — coincap_taunts.txt: players who broke the MAX_COINS
                    ceiling by hoarding.
  broke_taunt()   — broke_taunts.txt: players too poor to pay a command fee.

Every line is deliberately hand-curated, never generated: crude about the
player's greed, poverty and general uselessness, and off families entirely.
Add new ones to the data file, one per line; blank lines and `#` comments are
ignored.
"""

import os
import random

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data_files")

# pool name -> (data file, last-resort line if the file is missing or empty —
# the caller should always get something quotable, never an empty string)
_POOLS = {
    "ceiling": (os.path.join(_DATA_DIR, "coincap_taunts.txt"),
                "You hoarded so hard you broke the counter. Nobody is impressed."),
    "broke": (os.path.join(_DATA_DIR, "broke_taunts.txt"),
              "You can't afford the joke, so you are the joke."),
}

# Kept for tests and callers that only ever knew the ceiling pool.
_TAUNT_FILE, _FALLBACK = _POOLS["ceiling"]

_cache: dict[str, list[str]] = {}


def _load(pool: str = "ceiling") -> list[str]:
    if pool in _cache:
        return _cache[pool]
    path, fallback = _POOLS[pool]
    lines = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if line and not line.startswith("#"):
                    lines.append(line)
    except OSError:
        pass
    _cache[pool] = lines or [fallback]
    return _cache[pool]


def ceiling_taunt() -> str:
    """One random taunt for a player the MAX_COINS ceiling just bit."""
    return random.choice(_load("ceiling"))


def broke_taunt() -> str:
    """One random taunt for a player too poor to pay a command's fee."""
    return random.choice(_load("broke"))
