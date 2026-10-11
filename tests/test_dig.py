"""Loot Dig — pin the escalating payout schedule and the slot cooldown gate.
Imports the cog (which imports discord), so it skips where deps are absent."""
from datetime import date

import pytest

pytest.importorskip("discord")

from dig import (  # noqa: E402
    PAYOUT_CUMULATIVE,
    DIG_CAP,
    NUM_LOOT,
    NUM_JUJU,
    GRID_SIZE,
    KV_NAMESPACE,
    _slot_key,
)


def test_board_composition():
    assert NUM_JUJU == 1
    assert NUM_LOOT == 15
    assert NUM_JUJU + NUM_LOOT == GRID_SIZE == 16


def test_cumulative_full_clear_hits_the_cap_exactly():
    assert PAYOUT_CUMULATIVE[0] == 0
    assert PAYOUT_CUMULATIVE[NUM_LOOT] == DIG_CAP == 5_000_000_000
    assert len(PAYOUT_CUMULATIVE) == NUM_LOOT + 1


def test_payouts_are_strictly_increasing_and_escalating():
    incs = [PAYOUT_CUMULATIVE[n] - PAYOUT_CUMULATIVE[n - 1] for n in range(1, NUM_LOOT + 1)]
    # The bank only ever grows.
    assert all(a < b for a, b in zip(PAYOUT_CUMULATIVE, PAYOUT_CUMULATIVE[1:]))
    # Each tile pays strictly more than the previous (escalating curve).
    assert all(a < b for a, b in zip(incs, incs[1:]))
    # Early tiny, late huge.
    assert incs[0] < 50_000_000
    assert incs[-1] > 500_000_000


def test_cooldown_gate_predicate(monkeypatch):
    import dig
    import economy

    today = date.today().isoformat()
    store = {}
    monkeypatch.setattr(economy, "kv_get",
                        lambda g, u, ns, k, default=None: store.get((g, u, ns, k), default))
    monkeypatch.setattr(economy, "kv_set",
                        lambda g, u, ns, k, v: store.__setitem__((g, u, ns, k), v))

    cog = dig.LootDig.__new__(dig.LootDig)
    # Fresh slot -> allowed.
    assert cog._cooldown_refusal(1, 2) is None
    # Stamp it -> refused this slot.
    cog._stamp(1, 2)
    assert store[(1, 2, KV_NAMESPACE, _slot_key())] == today
    assert cog._cooldown_refusal(1, 2) is not None
