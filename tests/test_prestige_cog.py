"""The prestige roll is a pure function so its distribution and clamping can be
pinned without a Discord client. A setback wipes to level 0 and banks nothing;
a normal roll gains 1-6 levels, clamped to the max, and banks exactly the
rolled gain."""
import random

import pytest

import economy

pytest.importorskip("discord")

import prestige  # noqa: E402
from prestige import roll_prestige  # noqa: E402


@pytest.fixture(autouse=True)
def _ensure_max(monkeypatch):
    # economy.PRESTIGE_MAX_LEVEL is owned by another module; pin a known value
    # so clamping is deterministic regardless of the deployed constant.
    monkeypatch.setattr(economy, "PRESTIGE_MAX_LEVEL", 100, raising=False)


class _SetbackRNG:
    """random() always rolls under the setback chance."""
    def random(self):
        return 0.0

    def choices(self, population, weights=None):  # pragma: no cover - never hit
        raise AssertionError("setback must not consult the gain table")


class _GainRNG:
    """random() never triggers the setback; choices returns a fixed gain."""
    def __init__(self, gain):
        self._gain = gain

    def random(self):
        return 0.99

    def choices(self, population, weights=None):
        assert self._gain in population
        return [self._gain]


def test_setback_zeroes_everything():
    new_level, lifetime_gain, is_setback = roll_prestige(42, _SetbackRNG())
    assert (new_level, lifetime_gain, is_setback) == (0, 0, True)


def test_setback_from_level_zero():
    # setback is independent of starting level
    assert roll_prestige(0, _SetbackRNG()) == (0, 0, True)


@pytest.mark.parametrize("gain", [1, 2, 3, 4, 5, 6])
def test_normal_gain_banks_exactly_the_rolled_gain(gain):
    level = 10
    new_level, lifetime_gain, is_setback = roll_prestige(level, _GainRNG(gain))
    assert not is_setback
    assert lifetime_gain == gain
    # Well below the max, so levels actually gained == the rolled gain.
    assert new_level - level == gain
    assert lifetime_gain == new_level - level


@pytest.mark.parametrize("gain", [1, 2, 3, 4, 5, 6])
def test_new_level_never_exceeds_max(gain):
    # Start right at the ceiling; a normal gain must clamp to the max.
    new_level, lifetime_gain, is_setback = roll_prestige(
        economy.PRESTIGE_MAX_LEVEL, _GainRNG(gain))
    assert not is_setback
    assert new_level == economy.PRESTIGE_MAX_LEVEL
    assert lifetime_gain == gain


def test_seeded_rng_is_deterministic_and_in_range():
    # Real random.Random, seeded: same seed -> same sequence, gains always 1..6.
    for seed in range(50):
        rng_a = random.Random(seed)
        rng_b = random.Random(seed)
        out_a = roll_prestige(5, rng_a)
        out_b = roll_prestige(5, rng_b)
        assert out_a == out_b
        new_level, lifetime_gain, is_setback = out_a
        if is_setback:
            assert (new_level, lifetime_gain) == (0, 0)
        else:
            assert 1 <= lifetime_gain <= 6
            assert new_level <= economy.PRESTIGE_MAX_LEVEL


def test_win_multiplier_and_surcharge():
    assert prestige.win_multiplier(0) == 1
    assert prestige.win_multiplier(3) == 4
    assert prestige.surcharge_factor(0) == 1
    assert prestige.surcharge_factor(4) == 2  # +100% at level 4
