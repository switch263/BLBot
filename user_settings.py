"""
user_settings.py — a tiny registry for per-user saved preferences.

Goal: stop every cog from minting its own `/foo-save` slash command. Instead a
single `cogs/settings.py` exposes `/set`, `/get`, `/unset`, and each cog
*registers* the settings it cares about here. The settings cog routes by key.

This module is pure data + thin wrappers over economy's cog_kv store — it never
opens its own SQLite connection (see CLAUDE.md). Values are stored globally
per-user (guild_id=0), so a saved preference follows a player across every
server and DM. economy.py knows nothing about what these keys mean.

A cog registers at setup() time:

    import user_settings
    user_settings.register(
        key="location",
        label="Weather location",
        description="Default city/zip for /weather",
        validate=lambda v: v.strip() or _raise("Give a real location."),
    )

and reads the saved value when it needs it:

    where = user_settings.get_value(user_id, "location")
"""

from dataclasses import dataclass
from typing import Callable, Optional
import logging

import economy

logger = logging.getLogger(__name__)

# All settings live under one namespace, keyed globally per user.
_NAMESPACE = "user_settings"
_GLOBAL_GUILD = 0


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    description: str
    # Optional normalizer/validator: takes the raw string, returns the value to
    # store, or raises ValueError(message) to reject it. Defaults to a trim.
    validate: Optional[Callable[[str], str]] = None


# key -> Setting. Populated by cogs at load time.
_REGISTRY: dict[str, Setting] = {}


def register(key: str, label: str, description: str,
             validate: Optional[Callable[[str], str]] = None) -> None:
    """Register a setting key. Idempotent — re-registering overwrites, so a cog
    reload doesn't duplicate or error."""
    key = key.lower().strip()
    if key in _REGISTRY:
        logger.debug("user_settings: re-registering key %r", key)
    _REGISTRY[key] = Setting(key=key, label=label, description=description,
                             validate=validate)


def get_setting(key: str) -> Optional[Setting]:
    return _REGISTRY.get(key.lower().strip())


def all_settings() -> list[Setting]:
    return sorted(_REGISTRY.values(), key=lambda s: s.key)


def normalize(setting: Setting, raw: str) -> str:
    """Run the setting's validator (or a default trim). Raises ValueError with a
    user-facing message if the value is rejected."""
    if setting.validate is not None:
        return setting.validate(raw)
    value = raw.strip()
    if not value:
        raise ValueError("Value can't be empty.")
    return value


# --- storage (thin wrappers over economy.cog_kv) -------------------------------

def get_value(user_id: int, key: str, default=None):
    return economy.kv_get(_GLOBAL_GUILD, user_id, _NAMESPACE, key, default)


def set_value(user_id: int, key: str, value) -> None:
    economy.kv_set(_GLOBAL_GUILD, user_id, _NAMESPACE, key, value)


def clear_value(user_id: int, key: str) -> None:
    economy.kv_delete(_GLOBAL_GUILD, user_id, _NAMESPACE, key)


def all_for_user(user_id: int) -> dict:
    """Every saved {key: value} for this user (only registered keys are kept)."""
    return economy.kv_get_all(_GLOBAL_GUILD, user_id, _NAMESPACE)
