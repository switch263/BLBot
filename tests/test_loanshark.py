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


# ---- collections: the goons scale with the debtor's wealth --------------------

from loanshark import (  # noqa: E402
    wealth_cut_pct, collection_demand, WEALTH_CUT_BRACKETS, STAGE_CUT_MULT,
)

OWED = 130_000


def test_bracket_table_is_well_formed():
    floors = [f for f, _ in WEALTH_CUT_BRACKETS]
    assert floors == sorted(floors, reverse=True), "brackets must be richest-first"
    assert floors[-1] == 0, "there must be a zero-wealth floor bracket"
    cuts = [c for _, c in WEALTH_CUT_BRACKETS]
    assert cuts == sorted(cuts, reverse=True), "richer must never mean a smaller cut"
    assert all(0 < c <= 1 for c in cuts)


def test_cut_pct_is_monotonic_in_wealth():
    seen = [wealth_cut_pct(w) for w in
            (0, 500_000, 5_000_000, 50_000_000, 500_000_000,
             5_000_000_000, 50_000_000_000, 5_000_000_000_000)]
    assert seen == sorted(seen)
    assert seen[0] < seen[-1], "a billionaire must lose a bigger fraction than a pauper"


def test_demand_is_never_below_the_tab():
    for wealth in (0, 1, OWED // 2, OWED, 10 * OWED, 10**12):
        for stage in (2, 3, 4):
            assert collection_demand(OWED, wealth, stage) >= OWED


def test_demand_never_exceeds_what_they_have_or_owe():
    """The only ceiling: a stage can't invent money. Demand is at most the
    debtor's whole wealth, unless the tab itself is bigger than their wealth."""
    for wealth in (0, 1_000, 10**9, 10**15):
        for stage in (2, 3, 4):
            assert collection_demand(OWED, wealth, stage) <= max(OWED, wealth)


def test_richer_debtor_pays_more_at_the_same_stage():
    poor = collection_demand(OWED, 200_000, 2)
    mid = collection_demand(OWED, 50_000_000, 2)
    rich = collection_demand(OWED, 5_000_000_000, 2)
    assert poor < mid < rich
    # and the rich guy loses far more than the tab he actually owed
    assert rich > 10 * OWED


def test_later_stages_hit_harder():
    wealth = 5_000_000_000
    s2 = collection_demand(OWED, wealth, 2)
    s3 = collection_demand(OWED, wealth, 3)
    s4 = collection_demand(OWED, wealth, 4)
    assert s2 < s3 < s4
    assert s4 == wealth, "the final stage sweeps everything"


def test_final_stage_takes_everything_even_from_a_small_tab():
    assert collection_demand(1_000, 10**12, FINAL_STAGE) == 10**12


def test_broke_debtor_demand_is_just_the_tab():
    assert collection_demand(OWED, 0, 2) == OWED
    assert collection_demand(OWED, 0, FINAL_STAGE) == OWED


def test_stage_one_is_words_only():
    """Stage 1 is the phone call — no seizure runs, and the multiplier says so."""
    assert STAGE_CUT_MULT[1] == 0.0
    assert collection_demand(OWED, 10**9, 1) == OWED
