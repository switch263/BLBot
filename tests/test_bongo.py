"""Bongo (Kitty Plays the Bongo) — pin the payout math and the once-per-day
gate. Imports the cog module (which imports discord), so it skips cleanly
where the bot's deps aren't installed."""
from fractions import Fraction

import pytest

pytest.importorskip("discord")

from bongo import (  # noqa: E402
    tile_mult,
    kitty_mult,
    _day_gate_refusal,
    SMALL_MULT,
    BONGO_MULT,
    BIG_MULT,
    KITTY_MULT,
    KITTY_FIRST_MULT,
    NUM_ENDERS,
    NUM_KITTY,
    NUM_BONGO,
    NUM_BIG,
    NUM_SMALL,
    GRID_SIZE,
)


def test_board_composition_sums_to_grid():
    assert NUM_ENDERS + NUM_KITTY + NUM_BONGO + NUM_BIG + NUM_SMALL == GRID_SIZE
    # Exactly the layout the design calls for.
    assert (NUM_ENDERS, NUM_KITTY, NUM_BONGO, NUM_BIG, NUM_SMALL) == (2, 1, 3, 4, 6)


def test_tile_multipliers():
    assert tile_mult("small") == SMALL_MULT == Fraction(3, 2)
    assert tile_mult("bongo") == BONGO_MULT == 25
    assert tile_mult("big") == BIG_MULT == 100


def test_multiplicative_stacking_is_exact_and_overflow_safe():
    # A big bet times a huge compounded multiplier must stay an exact int.
    bet = 10 ** 200
    mult = SMALL_MULT * BIG_MULT * BIG_MULT  # 1.5 * 100 * 100 = 15000
    assert mult == Fraction(15000)
    assert int(bet * mult) == 15000 * bet  # no float, no overflow


def test_kitty_first_tap_is_flat_1000x():
    # On the very first tile the running total is x1; kitty pays a flat 1000x.
    assert kitty_mult(Fraction(1), first_tile=True) == KITTY_FIRST_MULT == 1000


def test_kitty_otherwise_caps_running_total_times_25():
    running = SMALL_MULT * BIG_MULT  # 150
    assert kitty_mult(running, first_tile=False) == running * KITTY_MULT == 3750


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
