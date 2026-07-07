"""Game-math invariants for the cogs with real math in them. These import the
cog modules (which import discord), so they skip cleanly in an environment
without the bot's dependencies installed."""
import math

import pytest

pytest.importorskip("discord")

from raccoonden import current_multiplier, DEN_MAX_MULT, GRID_SIZE, MIN_RACCOONS, MAX_RACCOONS, HOUSE_EDGE  # noqa: E402
from vault import DIFFICULTIES, MAX_ATTEMPTS, score, VaultGame  # noqa: E402


def test_den_multiplier_is_ev_fair_below_cap():
    for r in range(MIN_RACCOONS, MAX_RACCOONS + 1):
        safe = GRID_SIZE - r
        for picks in range(1, safe + 1):
            p = 1.0
            for i in range(picks):
                p *= (safe - i) / (GRID_SIZE - i)
            m = current_multiplier(picks, r)
            assert math.isclose(m, min(HOUSE_EDGE / p, DEN_MAX_MULT), rel_tol=1e-9)
            if m < DEN_MAX_MULT * 0.999:
                assert math.isclose(p * m, HOUSE_EDGE, rel_tol=1e-9)


def test_den_multiplier_slides_with_raccoon_count():
    for picks in (1, 2, 3, 4):
        mults = [current_multiplier(picks, r) for r in range(MIN_RACCOONS, MAX_RACCOONS + 1)]
        assert mults == sorted(mults) and mults[0] < mults[-1]


def test_vault_score_is_repeat_aware():
    assert score([1, 2, 3, 4], [1, 2, 3, 4]) == (4, 0, 0)
    assert score([4, 3, 2, 1], [1, 2, 3, 4]) == (0, 4, 0)
    assert score([5, 5, 5, 5], [1, 2, 3, 4]) == (0, 0, 4)
    assert score([1, 1, 2], [1, 2, 2]) == (2, 0, 1)
    assert score([2, 2, 1], [1, 2, 2]) == (1, 2, 0)


def test_vault_difficulty_configs():
    for name, cfg in DIFFICULTIES.items():
        assert set(cfg["payouts"]) == set(range(1, MAX_ATTEMPTS + 1)), name
        if not cfg["repeats"]:
            assert len(cfg["digits"]) >= cfg["code_length"], name
        g = VaultGame(1, 2, "t", 100, cfg)
        assert len(g.code) == cfg["code_length"]
        fb, solved = g.feedback_for(list(g.code))
        assert solved
