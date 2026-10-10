"""Bongo (Kitty Plays the Bongo) — pin the payout math and the once-per-day
gate. Imports the cog module (which imports discord), so it skips cleanly
where the bot's deps aren't installed."""
import pytest

pytest.importorskip("discord")

from bongo import (  # noqa: E402
    current_multiplier,
    _day_gate_refusal,
    SAFE_BUMP,
    BONGO_MULT,
    FIRST_SHOT_MULT,
    NUM_BUST_CATS,
    NUM_BONGO,
    GRID_SIZE,
)


def test_current_multiplier_math():
    assert current_multiplier(0) == 1.0
    assert current_multiplier(1) == 1.0 + SAFE_BUMP
    assert current_multiplier(5) == 1.0 + SAFE_BUMP * 5
    # Climbs by exactly SAFE_BUMP per clean tap.
    for paws in range(0, GRID_SIZE):
        assert current_multiplier(paws + 1) - current_multiplier(paws) == pytest.approx(SAFE_BUMP)


def test_tuning_pays_better_than_bigfoot():
    # The whole point: way juicier than the woods.
    assert SAFE_BUMP == 1.0
    assert BONGO_MULT == 25.0
    assert FIRST_SHOT_MULT == 250.0
    assert NUM_BUST_CATS == 2
    assert NUM_BONGO == 1


def test_board_composition_leaves_room_to_play():
    # Scared cats + the solo + at least one safe tap.
    assert NUM_BUST_CATS + NUM_BONGO < GRID_SIZE


def test_day_gate_refuses_when_played_today():
    assert _day_gate_refusal("2026-10-10", "2026-10-10") is not None


def test_day_gate_allows_on_a_new_day():
    assert _day_gate_refusal("2026-10-09", "2026-10-10") is None


def test_day_gate_allows_when_never_played():
    assert _day_gate_refusal(None, "2026-10-10") is None


def test_cog_day_gate_wires_kv_and_today(monkeypatch):
    """The cog's gate reads kv_get/today_str and runs them through the pure
    predicate: a stored last_day equal to today refuses, otherwise None."""
    import bongo

    today = "2026-10-10"
    monkeypatch.setattr(bongo.economy, "today_str", lambda: today)

    store = {}

    def fake_kv_get(guild_id, user_id, ns, key, default=None):
        return store.get((guild_id, user_id, ns, key), default)

    monkeypatch.setattr(bongo.economy, "kv_get", fake_kv_get)

    cog = bongo.BongoKitty.__new__(bongo.BongoKitty)

    # Never played -> allowed.
    assert cog._day_gate(1, 2) is None

    # Played today -> refused.
    store[(1, 2, bongo.KV_NAMESPACE, bongo.KV_LAST_DAY)] = today
    assert cog._day_gate(1, 2) is not None

    # Played yesterday -> allowed again.
    store[(1, 2, bongo.KV_NAMESPACE, bongo.KV_LAST_DAY)] = "2026-10-09"
    assert cog._day_gate(1, 2) is None
