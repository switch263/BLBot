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
