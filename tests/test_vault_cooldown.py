"""The vault's time lock: one crack per player per VAULT_COOLDOWN, any
difficulty, persisted in cog_kv, and enforced by the prelude's `gate` hook
BEFORE the bet is collected."""
import asyncio

import pytest

import economy

pytest.importorskip("discord")

import vault  # noqa: E402
from game_common import casino_prelude  # noqa: E402

GUILD = 790_001
USER = 790_002


def _reset(guild, user):
    economy.delete_wallet(guild, user)
    economy.get_wallet(guild, user)


def test_lock_opens_after_the_cooldown():
    _reset(GUILD, USER)
    assert vault.cooldown_remaining(GUILD, USER, now=1_000.0) == 0
    vault.stamp_cooldown(GUILD, USER, now=1_000.0)
    assert vault.cooldown_remaining(GUILD, USER, now=1_000.0) == vault.VAULT_COOLDOWN
    assert vault.cooldown_remaining(GUILD, USER, now=1_000.0 + vault.VAULT_COOLDOWN - 1) == 1
    assert vault.cooldown_remaining(GUILD, USER, now=1_000.0 + vault.VAULT_COOLDOWN) == 0


def test_lock_survives_a_wallet_read_and_is_per_player():
    _reset(GUILD + 1, USER)
    _reset(GUILD + 1, USER + 1)
    vault.stamp_cooldown(GUILD + 1, USER, now=5_000.0)
    assert vault.cooldown_remaining(GUILD + 1, USER, now=5_000.0) > 0
    assert vault.cooldown_remaining(GUILD + 1, USER + 1, now=5_000.0) == 0
    assert vault.cooldown_remaining(GUILD + 2, USER, now=5_000.0) == 0


def test_gate_message_only_while_locked(monkeypatch):
    _reset(GUILD + 3, USER)
    assert vault._cooldown_gate(GUILD + 3, USER) is None
    vault.stamp_cooldown(GUILD + 3, USER)
    msg = vault._cooldown_gate(GUILD + 3, USER)
    assert msg and "Time lock" in msg


class _FakeCtx:
    """Just enough of a prefix ctx for casino_prelude: a guild, an author,
    and a send() that records what was said."""
    def __init__(self, guild_id, user_id):
        self.guild = type("G", (), {"id": guild_id})()
        self.author = type("U", (), {"id": user_id, "display_name": "u"})()
        self.sent = []

    async def send(self, content=None, **kwargs):
        self.sent.append(content)
        return None


def test_prelude_gate_refuses_before_any_coins_move():
    g, u = GUILD + 4, USER
    _reset(g, u)
    economy.add_coins(g, u, 10_000)
    before = economy.get_coins(g, u)
    house_before = economy.get_coins(g, economy.get_house_id())
    vault.stamp_cooldown(g, u)
    ctx = _FakeCtx(g, u)
    start = asyncio.run(casino_prelude(ctx, "5000", gate=vault._cooldown_gate))
    assert start is None
    assert ctx.sent and "Time lock" in ctx.sent[0]
    assert economy.get_coins(g, u) == before, "a refused player is never charged"
    assert economy.get_coins(g, economy.get_house_id()) == house_before


def test_prelude_lets_an_unlocked_player_through_and_collects():
    g, u = GUILD + 5, USER
    _reset(g, u)
    economy.add_coins(g, u, 10_000)
    before = economy.get_coins(g, u)
    ctx = _FakeCtx(g, u)
    start = asyncio.run(casino_prelude(ctx, "5000", gate=vault._cooldown_gate))
    assert start is not None and start.bet == 5_000
    assert economy.get_coins(g, u) == before - 5_000
