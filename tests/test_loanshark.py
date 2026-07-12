"""Loanshark escalation math: stage timing and juice compounding/cap."""
import pytest

pytest.importorskip("discord")

from loanshark import (  # noqa: E402
    stage_for, apply_juice,
    VIG_PCT, JUICE_PCT, MAX_OWED_MULT, MAX_LOAN, MIN_LOAN,
    STAGE_GAP_SECONDS, FINAL_STAGE, TERM_SECONDS,
)

DUE = 1_000_000.0
GAP = STAGE_GAP_SECONDS


# ---- stage_for ---------------------------------------------------------------

@pytest.mark.parametrize("now,expected", [
    (DUE - TERM_SECONDS, 0),      # just borrowed
    (DUE - 1, 0),                 # a second before the deadline
    (DUE, 1),                     # deadline hits -> the phone call
    (DUE + GAP - 1, 1),
    (DUE + GAP, 2),               # the goons
    (DUE + 2 * GAP, 3),           # the beating
    (DUE + 3 * GAP, 4),           # the harsh stuff
    (DUE + 50 * GAP, FINAL_STAGE),  # never past the final stage
])
def test_stage_progression(now, expected):
    assert stage_for(now, DUE) == expected


# ---- apply_juice ---------------------------------------------------------------

def test_juice_compounds_per_stage():
    import math
    owed = 130_000
    once = apply_juice(owed, 100_000, 1)
    assert once == math.ceil(owed * (1 + JUICE_PCT))
    assert apply_juice(owed, 100_000, 2) > once


def test_juice_zero_stages_is_identity():
    assert apply_juice(130_000, 100_000, 0) == 130_000


def test_juice_caps_at_max_owed_mult():
    principal = 100_000
    cap = int(principal * MAX_OWED_MULT)
    owed = int(principal * (1 + VIG_PCT))
    # Even absurdly many missed stages can't push past the cap.
    assert apply_juice(owed, principal, 100) == cap


def test_full_ladder_stays_capped():
    """A loan that rides every stage to the end owes at most MAX_OWED_MULT x."""
    principal = MAX_LOAN
    owed = int(principal * (1 + VIG_PCT))
    for stage in range(1, FINAL_STAGE + 1):
        owed = apply_juice(owed, principal, 1)
        assert owed <= principal * MAX_OWED_MULT
    # And the ladder does actually grow the debt before the cap bites.
    assert owed > int(principal * (1 + VIG_PCT))


def test_loan_bounds_sane():
    assert 0 < MIN_LOAN < MAX_LOAN
    assert 0 < VIG_PCT < 1
    assert MAX_OWED_MULT > 1 + VIG_PCT
