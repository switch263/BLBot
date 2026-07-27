"""Hand-written taunts for players who broke something by being too rich.

Pure data + a picker, like items.py — no Discord, no DB. Lives at the repo
root so both the watcher cog (cogs/coincap.py) and the commands that refuse a
move on the spot (gift, bank) insult with the same voice.

The lines are deliberately hand-curated, never generated: they're crude about
the player's greed, hoarding, and general uselessness, and they stay off
families entirely. Add new ones to data_files/coincap_taunts.txt, one per
line; blank lines and `#` comments are ignored.
"""

import os
import random

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data_files")
_TAUNT_FILE = os.path.join(_DATA_DIR, "coincap_taunts.txt")

# Last-resort line if the data file is missing or empty — the caller should
# always get something quotable rather than an empty string.
_FALLBACK = "You hoarded so hard you broke the counter. Nobody is impressed."

_taunts: list[str] | None = None


def _load() -> list[str]:
    global _taunts
    if _taunts is not None:
        return _taunts
    lines = []
    try:
        with open(_TAUNT_FILE, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if line and not line.startswith("#"):
                    lines.append(line)
    except OSError:
        pass
    _taunts = lines or [_FALLBACK]
    return _taunts


def ceiling_taunt() -> str:
    """One random taunt for a player the MAX_COINS ceiling just bit."""
    return random.choice(_load())
