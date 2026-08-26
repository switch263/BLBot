"""The ransom job: economy.ransom_collect and the heist-side odds/knobs.

The ransom is the ONE player-vs-player path that reaches a bank account, so the
collection helper carries the weight — bank-first ordering, the wallet
fallthrough that closes the "withdraw everything mid-standoff" dodge, ceiling
clamping, and the memorial guard.
"""
import pytest

import economy

GUILD = 770_001
THIEF = 770_002
VICTIM = 770_003


def _fresh(guild, user, wallet=0, banked=0):
    """Put a player at an exact wallet/bank split."""
    economy.delete_wallet(guild, user)
    economy.get_wallet(guild, user)
    economy.kv_delete(guild, user, "bank", "balance")
    economy.kv_delete(guild, user, "bank", "interest_ts")
    have = economy.get_coins(guild, user)
    if have:
        economy.try_deduct(guild, user, have)
    if wallet + banked:
        economy.add_coins(guild, user, wallet + banked)
    if banked:
        assert economy.bank_deposit(guild, user, banked)["ok"]


# ---- bank-first ordering -----------------------------------------------------

def test_takes_from_the_bank_first():
    g = GUILD
    _fresh(g, VICTIM, wallet=100_000, banked=500_000)
    _fresh(g, THIEF, wallet=0)
    res = economy.ransom_collect(g, VICTIM, THIEF, 200_000)
    assert res["ok"]
    assert res["amount"] == 200_000
    assert res["from_bank"] == 200_000
    assert res["from_wallet"] == 0, "the vault pays before the pockets do"
    assert economy.bank_balance(g, VICTIM) == 300_000
    assert economy.get_coins(g, VICTIM) == 100_000
    assert economy.get_coins(g, THIEF) == 200_000


def test_falls_through_to_the_wallet_when_the_vault_is_short():
    """Emptying the bank mid-standoff doesn't dodge the ransom — the coins just
    moved somewhere equally reachable."""
    g = GUILD + 1
    _fresh(g, VICTIM, wallet=400_000, banked=50_000)
    _fresh(g, THIEF, wallet=0)
    res = economy.ransom_collect(g, VICTIM, THIEF, 200_000)
    assert res["ok"]
    assert res["from_bank"] == 50_000
    assert res["from_wallet"] == 150_000
    assert res["amount"] == 200_000
    assert economy.bank_balance(g, VICTIM) == 0
    assert economy.get_coins(g, VICTIM) == 250_000


def test_takes_what_it_can_when_the_victim_is_nearly_broke():
    g = GUILD + 2
    _fresh(g, VICTIM, wallet=300, banked=200)
    _fresh(g, THIEF, wallet=0)
    res = economy.ransom_collect(g, VICTIM, THIEF, 10_000)
    assert res["ok"]
    assert res["amount"] == 500
    assert economy.get_coins(g, THIEF) == 500
    assert economy.bank_balance(g, VICTIM) == 0
    assert economy.get_coins(g, VICTIM) == 0


# ---- money conservation ------------------------------------------------------

def test_conserves_money_nothing_minted_or_burned():
    g = GUILD + 3
    _fresh(g, VICTIM, wallet=250_000, banked=750_000)
    _fresh(g, THIEF, wallet=1_000)
    before = economy.get_wealth(g, VICTIM) + economy.get_wealth(g, THIEF)
    res = economy.ransom_collect(g, VICTIM, THIEF, 400_000)
    assert res["ok"]
    after = economy.get_wealth(g, VICTIM) + economy.get_wealth(g, THIEF)
    assert after == before, "a ransom moves coins, it never creates them"


def test_no_total_won_bump():
    """A ransom is theft, not winnings — it must not inflate the brag stat or
    the net_won figure the weekly tax is computed from."""
    g = GUILD + 4
    _fresh(g, VICTIM, banked=500_000)
    _fresh(g, THIEF, wallet=0)
    before = economy.get_wallet(g, THIEF)
    economy.ransom_collect(g, VICTIM, THIEF, 100_000)
    after = economy.get_wallet(g, THIEF)
    assert after["total_won"] == before["total_won"]


# ---- guards ------------------------------------------------------------------

def test_rejects_nonpositive_amounts():
    for bad in (0, -1, -999):
        res = economy.ransom_collect(GUILD, VICTIM, THIEF, bad)
        assert not res["ok"] and res["error"] == "invalid_amount"


def test_memorial_is_never_ransomed_or_ransoming():
    g = GUILD + 5
    m = economy.MEMORIAL_USER_ID
    assert economy.ransom_collect(g, m, THIEF, 1_000)["error"] == "memorial"
    assert economy.ransom_collect(g, VICTIM, m, 1_000)["error"] == "memorial"


def test_empty_victim_reports_empty_and_moves_nothing():
    g = GUILD + 6
    _fresh(g, VICTIM, wallet=0, banked=0)
    _fresh(g, THIEF, wallet=5_000)
    res = economy.ransom_collect(g, VICTIM, THIEF, 50_000)
    assert not res["ok"] and res["error"] == "empty"
    assert economy.get_coins(g, THIEF) == 5_000


def test_clamps_to_the_thiefs_headroom_instead_of_burning_coins():
    """A thief at the ceiling can't receive — and the victim must keep every
    coin that couldn't move (the ceiling never destroys money mid-transfer)."""
    g = GUILD + 7
    _fresh(g, VICTIM, banked=1_000_000)
    _fresh(g, THIEF, wallet=0)
    economy.add_coins(g, THIEF, economy.MAX_COINS)
    res = economy.ransom_collect(g, VICTIM, THIEF, 500_000)
    assert not res["ok"] and res["error"] == "capped"
    assert economy.bank_balance(g, VICTIM) == 1_000_000, "victim keeps it all"


# ---- knobs -------------------------------------------------------------------

def test_ransom_band_is_sane_and_no_harsher_than_a_wallet_steal():
    pytest.importorskip("discord")
    import heist
    assert 0 < economy.RANSOM_MIN_PCT < economy.RANSOM_MAX_PCT <= 1
    # The bank must stay the safer place to keep coins.
    assert economy.RANSOM_MAX_PCT <= heist.STEAL_MAX_PCT
    assert economy.RANSOM_MAX_PCT <= economy.BANK_RAID_MAX_PCT


def test_heist_side_knobs():
    pytest.importorskip("discord")
    import heist
    assert 0 < heist.RANSOM_ODDS <= 0.05, "this is meant to be a rare event"
    assert 0 < heist.RANSOM_SUCCESS_RATE < 1, "there must be a fail branch"
    assert 0 < heist.RANSOM_PAYUP_DISCOUNT < 1, "settling early must be a discount"
    assert heist.RANSOM_TIMEOUT > 0
    assert heist.RANSOM_JAIL_MIN_SECONDS <= heist.RANSOM_JAIL_MAX_SECONDS
    assert heist.RANSOM_BAIL_PCT > 0, "bail of 0 would mean nobody can post it"


def test_paying_up_beats_the_bluff_on_expectation():
    """The discount has to actually be worth taking, or the button is a trap."""
    pytest.importorskip("discord")
    import heist
    demand = 1_000_000
    pay_now = demand * heist.RANSOM_PAYUP_DISCOUNT
    bluff_ev = demand * heist.RANSOM_SUCCESS_RATE
    assert pay_now < bluff_ev, "settling must cost less than riding the roll"
