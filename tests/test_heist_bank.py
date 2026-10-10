"""The opt-in bank-robbery mode of /heist (`!heist @victim bank`).

The money movement lives in economy.bank_heist (covered elsewhere); what this
file pins is the cog-side economics, factored into pure module-level helpers in
heist.py so they can be exercised without a Discord client:

  - the up-front cover charge is 10% of the thief's wealth,
  - a successful job can never skim more than BANK_HEIST_MAX_PCT of a vault,
  - and the refusal gate turns away a memorial or shielded victim (and an empty
    vault) before any coins move.
"""
import pytest

pytest.importorskip("discord")

import heist  # noqa: E402


# ---- the cover charge: 10% of the thief's wealth ----------------------------

@pytest.mark.parametrize("wealth", [0, 1, 9, 10, 11, 99, 100, 999,
                                    1_000, 100_000, 1_000_000, 123_456_789])
def test_cover_charge_is_ten_percent_of_wealth(wealth):
    assert heist.bank_heist_cost(wealth) == wealth // 10


def test_cover_charge_constant_is_ten_percent():
    assert heist.BANK_HEIST_COST_PCT == 0.10
    # The helper is pinned to the constant, not a hard-coded //10.
    assert heist.bank_heist_cost(5_000_000) == int(5_000_000 * heist.BANK_HEIST_COST_PCT)


def test_cover_charge_is_monotonic():
    """Richer thieves always pay at least as much to try."""
    prev = -1
    for wealth in (0, 1_000, 50_000, 1_000_000, 1_000_000_000):
        cost = heist.bank_heist_cost(wealth)
        assert cost >= prev
        prev = cost


# ---- the steal band: never empties a vault ----------------------------------

def test_success_pct_never_exceeds_the_cap():
    lo, hi = heist.bank_heist_steal_bounds()
    assert lo == 0.0
    assert hi == heist.BANK_HEIST_MAX_PCT
    assert hi <= 0.25


def test_expected_take_per_attempt_stays_modest():
    """The vault band max (0.25) is deliberately richer than the wallet steal —
    the vault job is opt-in, costs 10% up front, and only lands BANK_HEIST_SUCCESS
    of the time. Across a launched attempt the expected fraction skimmed is small,
    so one attempt can't gut a vault on average."""
    lo, hi = heist.bank_heist_steal_bounds()
    expected_fraction = heist.BANK_HEIST_SUCCESS * (lo + hi) / 2
    assert expected_fraction <= heist.STEAL_MAX_PCT


# ---- knobs are sane ---------------------------------------------------------

def test_knobs_are_sane():
    assert 0 < heist.BANK_HEIST_COST_PCT < 1
    assert 0 < heist.BANK_HEIST_SUCCESS < 1, "there must be a fail branch"
    assert 0 < heist.BANK_HEIST_MAX_PCT <= 1
    assert heist.BANK_HEIST_MIN_BANK > 0
    assert heist.BANK_HEIST_JAIL_MIN_SECONDS <= heist.BANK_HEIST_JAIL_MAX_SECONDS
    assert heist.BANK_HEIST_BAIL_PCT > 0, "bail of 0 would mean nobody can post it"


# ---- the refusal gate -------------------------------------------------------

def test_gate_refuses_a_memorial_victim():
    reason = heist.bank_heist_gate(
        victim_memorial=True, victim_shielded=False, victim_bank=10_000_000)
    assert reason == "memorial"


def test_gate_refuses_a_shielded_victim():
    reason = heist.bank_heist_gate(
        victim_memorial=False, victim_shielded=True, victim_bank=10_000_000)
    assert reason == "shielded"


def test_memorial_takes_priority_over_a_shield():
    reason = heist.bank_heist_gate(
        victim_memorial=True, victim_shielded=True, victim_bank=0)
    assert reason == "memorial"


def test_gate_refuses_an_empty_vault():
    reason = heist.bank_heist_gate(
        victim_memorial=False, victim_shielded=False,
        victim_bank=heist.BANK_HEIST_MIN_BANK - 1)
    assert reason == "empty"


def test_gate_proceeds_when_the_vault_is_worth_cracking():
    reason = heist.bank_heist_gate(
        victim_memorial=False, victim_shielded=False,
        victim_bank=heist.BANK_HEIST_MIN_BANK)
    assert reason is None
