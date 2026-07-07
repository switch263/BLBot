"""Test bootstrap: point economy.py at a scratch database BEFORE anything
imports it, and put the repo root + cogs/ on sys.path the way bot.py does.

The env var is force-set, never inherited: the suite writes junk guilds and
overwrites house state, so if it ever ran against an inherited BOT_DATA_DIR
(e.g. inside the deployed container, where it points at the live volume) it
would pollute the production economy.db."""
import os
import sys
import tempfile
from pathlib import Path

_scratch = tempfile.mkdtemp(prefix="blbot-tests-")
os.environ["BOT_DATA_DIR"] = _scratch

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(ROOT / "cogs")):
    if p not in sys.path:
        sys.path.insert(0, p)
