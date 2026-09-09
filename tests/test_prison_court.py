"""Outcome-table invariants for the prison yard, jury trials, and Sal's jobs."""
import pytest

pytest.importorskip("discord")

import jurytrial  # noqa: E402
import loanshark  # noqa: E402
import prison  # noqa: E402


# ---- loanshark jobs -----------------------------------------------------------

def test_job_outcomes_well_formed():
    for weight, cut_min, cut_max, jail_seconds, flavor in loanshark.JOB_OUTCOMES:
        assert weight > 0
        assert cut_min <= cut_max
        # No single job can forgive more than half the debt or add more than half.
        assert -0.5 <= cut_min and cut_max <= 0.5
        assert jail_seconds >= 0
        if cut_min > 0:
            assert "{cut" in flavor, "debt-reducing outcomes must show the number"


def test_job_is_worth_doing_but_not_free_money():
    total = sum(w for w, *_ in loanshark.JOB_OUTCOMES)
    reducing = sum(w for w, lo, *_ in loanshark.JOB_OUTCOMES if lo > 0)
    assert 0.4 < reducing / total < 0.9


def test_job_cooldown_positive():
    assert loanshark.JOB_COOLDOWN_SECONDS >= 3600


# ---- prison yard -----------------------------------------------------------------

def test_labor_outcomes_well_formed():
    for weight, cigs, jail_delta, _flavor in prison.LABOR_OUTCOMES:
        assert weight > 0
        assert cigs >= 0            # labor never takes your smokes
        assert abs(jail_delta) <= 30 * 60


def test_gym_outcomes_well_formed():
    for weight, lo, hi, _flavor in prison.GYM_OUTCOMES:
        assert weight > 0
        assert lo <= hi
    # The gym must be net-positive (mostly shaves time) or nobody uses it.
    shaving = sum(w for w, lo, hi, _ in prison.GYM_OUTCOMES if hi < 0)
    total = sum(w for w, *_ in prison.GYM_OUTCOMES)
    assert shaving / total > 0.5


def test_dice_has_house_edge():
    lose = 1 - prison.DICE_WIN_PCT - prison.DICE_CHEAT_PCT
    assert prison.DICE_WIN_PCT < lose + prison.DICE_CHEAT_PCT
    assert 0 < prison.DICE_CHEAT_PCT < 0.2


def test_shiv_probabilities_sane():
    assert prison.SHIV_WIN_PCT + prison.SHIV_BUST_PCT < 1
    assert prison.SHIV_MIN_STAKE > 0
    assert prison.INMATE_NAMES  # someone has to get shanked


def _edge(outcomes, mult_index=1):
    total = sum(o[0] for o in outcomes)
    return sum(o[0] * o[mult_index] for o in outcomes) / total


def test_cards_pay_less_than_they_take():
    # Expected return per cig staked must be under 1 — The Accountant wins.
    ev = _edge(prison.CARDS_OUTCOMES)
    assert 0.75 < ev < 1.0, ev
    for weight, mult, flavor in prison.CARDS_OUTCOMES:
        assert weight > 0 and mult >= 0
        assert "{win}" in flavor if mult > 1 else "{stake}" in flavor
    assert prison.CARDS_MIN_STAKE >= 1


def test_smuggle_is_high_variance_with_a_house_edge():
    ev = _edge(prison.SMUGGLE_OUTCOMES)
    assert 0.8 < ev < 1.0, ev
    total = sum(o[0] for o in prison.SMUGGLE_OUTCOMES)
    for weight, mult, jail_delta, flavor in prison.SMUGGLE_OUTCOMES:
        assert weight > 0 and mult >= 0 and jail_delta >= 0   # a run never shaves time
        assert jail_delta <= 45 * 60
        if mult == 0:
            assert jail_delta > 0, "a bust always costs time"
    busts = sum(w for w, m, *_ in prison.SMUGGLE_OUTCOMES if m == 0)
    assert 0.25 < busts / total < 0.5
    assert prison.SMUGGLE_MIN_STAKE > 0 and prison.SMUGGLE_COOLDOWN_SECONDS >= 30 * 60


def test_tunnel_takes_several_digs_but_is_finishable():
    total = sum(o[0] for o in prison.TUNNEL_OUTCOMES)
    expected_gain = sum(w * (lo + hi) / 2 for w, lo, hi, reset, *_ in prison.TUNNEL_OUTCOMES
                        if not reset) / total
    resets = sum(w for w, lo, hi, reset, *_ in prison.TUNNEL_OUTCOMES if reset) / total
    # ~6-12 clean digs to 100%, with a real but not crushing chance of a reset.
    assert 8 <= expected_gain <= 18, expected_gain
    assert 0.1 <= resets <= 0.25, resets
    for weight, lo, hi, reset, jail_delta, cig_delta, flavor in prison.TUNNEL_OUTCOMES:
        assert weight > 0 and 0 <= lo <= hi
        assert jail_delta >= 0 and cig_delta <= 0
        if reset:
            assert lo == hi == 0 and jail_delta > 0
            assert "reset" in flavor.lower()
        if hi > 0:
            assert "{progress}" in flavor
    assert prison.TUNNEL_GOAL == 100
    assert prison.TUNNEL_COOLDOWN_SECONDS >= 10 * 60


def test_snitching_mostly_pays_but_can_burn_you():
    total = sum(o[0] for o in prison.SNITCH_OUTCOMES)
    shaving = sum(w for w, lo, hi, *_ in prison.SNITCH_OUTCOMES if hi < 0) / total
    burning = sum(w for w, lo, hi, *_ in prison.SNITCH_OUTCOMES if lo > 0) / total
    assert 0.5 <= shaving <= 0.7, shaving
    assert 0.1 <= burning <= 0.3, burning
    for weight, lo, hi, cig_pct, flavor in prison.SNITCH_OUTCOMES:
        assert weight > 0 and lo <= hi
        assert 0 <= cig_pct <= 0.5
        assert abs(lo) <= 60 * 60 and abs(hi) <= 60 * 60
        if lo != 0 or hi != 0:
            assert "{mins}" in flavor
        if cig_pct > 0:
            assert lo > 0, "losing cigs to the yard always comes with time added"
    assert prison.SNITCH_COOLDOWN_SECONDS >= 30 * 60


def test_every_prison_game_is_on_the_wallet():
    from slots import Slots  # noqa: F401 — imported for the display table
    import slots
    keys = {row[0] for row in slots.Slots._GAME_DISPLAY}
    for game in ("prisondice", "shivfight", "prisoncards", "smuggle", "tunnel", "snitch"):
        assert game in keys, game


def test_guard_rate_bounded():
    # Fencing cigs draws house money — keep the per-cig rate modest so labor
    # can't become a meaningful house drain.
    assert 0 < prison.GUARD_RATE <= 500
    assert prison.GUARD_MIN_CIGS >= 1


# ---- jury trials ------------------------------------------------------------------

def test_trial_constants_sane():
    assert jurytrial.MIN_JURORS >= 2
    assert jurytrial.TRIAL_FEE > 0
    assert 0 < jurytrial.GUILTY_EXTENSION_PCT <= 1
    assert jurytrial.VOTE_SECONDS >= 60


def test_jury_payout_bounded():
    # Worst-case civic-duty payout stays in the same ballpark as the fee the
    # defendant paid in — the court can't be farmed for house money.
    assert jurytrial.JUROR_FEE * jurytrial.MAX_PAID_JURORS <= jurytrial.TRIAL_FEE * 2
