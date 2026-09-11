"""The crew safe-deposit-box job: economy.bank_box_disburse and the cog's
approach table.

This is the SECOND player-vs-player path into a bank account (the ransom job
is the first), so the tests pin the property that makes that acceptable: at
every crew size, every approach's expected take is below the wallet job's,
and every band sits under economy.CREW_BOX_MAX_PCT. The bank stays the safer
place to keep coins.
"""
import pytest

import economy

GUILD = 780_001
OWNER = 780_002
A, B, C = 780_003, 780_004, 780_005


def _fresh(guild, user, wallet=0, banked=0):
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


# ---- economy.bank_box_disburse ----------------------------------------------

def test_drains_the_bank_only_and_splits_across_the_crew():
    g = GUILD
    _fresh(g, OWNER, wallet=100_000, banked=1_000_000)
    for u in (A, B, C):
        _fresh(g, u, wallet=0)
    res = economy.bank_box_disburse(g, OWNER, [(A, 200_000), (B, 150_000), (C, 150_000)])
    assert res["ok"]
    assert res["total"] == 500_000
    assert dict(res["paid"]) == {A: 200_000, B: 150_000, C: 150_000}
    assert economy.bank_balance(g, OWNER) == 500_000
    assert economy.get_coins(g, OWNER) == 100_000, "a box job never touches the wallet"
    assert economy.get_coins(g, A) == 200_000
    assert economy.get_coins(g, B) == 150_000
    assert economy.get_coins(g, C) == 150_000


def test_no_wallet_fallthrough_when_the_box_is_short():
    """Unlike the ransom, coins withdrawn before the drill lands are simply
    not in the box — the job reports 'short' and moves nothing."""
    g = GUILD + 1
    _fresh(g, OWNER, wallet=5_000_000, banked=100_000)
    _fresh(g, A, wallet=0)
    res = economy.bank_box_disburse(g, OWNER, [(A, 200_000)])
    assert res == {"ok": False, "error": "short", "have": 100_000}
    assert economy.bank_balance(g, OWNER) == 100_000
    assert economy.get_coins(g, OWNER) == 5_000_000
    assert economy.get_coins(g, A) == 0


def test_is_theft_not_winnings():
    g = GUILD + 2
    _fresh(g, OWNER, banked=1_000_000)
    _fresh(g, A, wallet=0)
    before = economy.get_wallet(g, A)
    assert economy.bank_box_disburse(g, OWNER, [(A, 300_000)])["ok"]
    after = economy.get_wallet(g, A)
    assert after["total_won"] == before["total_won"]
    assert economy.get_total_economy(g) == economy.get_total_economy(g)  # sanity: callable


def test_conserves_money():
    g = GUILD + 3
    _fresh(g, OWNER, wallet=50_000, banked=2_000_000)
    _fresh(g, A, wallet=10)
    _fresh(g, B, wallet=20)
    total_before = economy.get_total_economy(g)
    assert economy.bank_box_disburse(g, OWNER, [(A, 700_000), (B, 300_000)])["ok"]
    assert economy.get_total_economy(g) == total_before


def test_rejects_bad_input_and_the_memorial_player():
    g = GUILD + 4
    _fresh(g, OWNER, banked=1_000_000)
    assert economy.bank_box_disburse(g, OWNER, [])["error"] == "invalid_amount"
    assert economy.bank_box_disburse(g, OWNER, [(A, 0)])["error"] == "invalid_amount"
    assert economy.bank_box_disburse(g, economy.MEMORIAL_USER_ID, [(A, 10)])["error"] == "memorial"
    assert economy.bank_box_disburse(g, OWNER, [(economy.MEMORIAL_USER_ID, 10)])["error"] == "memorial"
    assert economy.bank_balance(g, OWNER) == 1_000_000


def test_trims_to_the_recipients_headroom_before_debiting():
    g = GUILD + 5
    _fresh(g, OWNER, banked=1_000_000)
    _fresh(g, A, wallet=0)
    economy.add_coins(g, A, economy.MAX_COINS - 100)
    _fresh(g, B, wallet=0)
    res = economy.bank_box_disburse(g, OWNER, [(A, 500_000), (B, 500_000)])
    assert res["ok"]
    assert dict(res["paid"]) == {A: 100, B: 500_000}
    assert res["total"] == 500_100
    assert economy.bank_balance(g, OWNER) == 1_000_000 - 500_100, "the owner only loses what was delivered"
    assert economy.get_coins(g, A) == economy.MAX_COINS


# ---- the cog's approach table --------------------------------------------------

pytest.importorskip("discord")

import crewheist as ch  # noqa: E402


def _wallet_ev(n):
    lo, hi = ch._steal_pct_bounds(n)
    return ch._success_rate(n) * (lo + hi) / 2


def _box_ev(approach, n):
    lo, hi = ch._box_take_bounds(approach)
    return ch._box_success_rate(approach, n) * (lo + hi) / 2


@pytest.mark.parametrize("approach", list(ch.BOX_APPROACHES))
@pytest.mark.parametrize("n", range(ch.CREW_MIN_CREW, ch.CREW_MAX_CREW + 1))
def test_bank_stays_safer_than_the_wallet(approach, n):
    """Expected fraction stolen per launched job must be lower for a box than
    for the equivalent wallet job at the same crew size."""
    assert _box_ev(approach, n) < _wallet_ev(n)


@pytest.mark.parametrize("approach", list(ch.BOX_APPROACHES))
def test_bands_sit_under_the_economy_ceiling(approach):
    lo, hi = ch.BOX_APPROACHES[approach]["take"]
    assert 0 < lo < hi <= economy.CREW_BOX_MAX_PCT
    assert hi <= ch.STEAL_CAP_PCT


@pytest.mark.parametrize("approach", list(ch.BOX_APPROACHES))
def test_approach_shape(approach):
    a = ch.BOX_APPROACHES[approach]
    for n in range(ch.CREW_MIN_CREW, ch.CREW_MAX_CREW + 1):
        assert 0 < ch._box_success_rate(approach, n) < 1
    assert ch._box_success_rate(approach, ch.CREW_MAX_CREW) >= ch._box_success_rate(approach, ch.CREW_MIN_CREW), \
        "more crew never means worse odds"
    assert 0 <= a["escape"] < 1
    assert 0 < a["jail"][0] <= a["jail"][1]
    assert 0 <= a["fine_pct"] < 1
    for table in (ch.BOX_BUILDUP, ch.BOX_SUCCESS_MESSAGES, ch.BOX_FAIL_MESSAGES,
                  ch.BOX_ESCAPE_LINES, ch.BOX_CAUGHT_LINES):
        assert table[approach], "every approach has its own flavor"


def test_odds_beat_the_vault_because_the_take_is_one_account():
    for approach in ch.BOX_APPROACHES:
        for n in range(ch.CREW_MIN_CREW, ch.CREW_MAX_CREW + 1):
            assert ch._box_success_rate(approach, n) > ch._house_success_rate(n)


def test_min_bank_guarantees_recruits_profit_on_any_win():
    """Worst roll: the stingiest approach's lowest take, split across a full
    crew, must still cover a recruit's seat."""
    worst_lo = min(ch._box_take_bounds(a)[0] for a in ch.BOX_APPROACHES)
    per_head = int(ch.BOX_MIN_BANK * worst_lo) // ch.CREW_MAX_CREW
    assert per_head >= ch.CREW_BUYIN
    assert ch.BOX_MIN_BANK >= ch.MIN_VICTIM_COINS, "a box is never a softer floor than a wallet"


def test_flavor_templates_format():
    fmt = dict(starter="@ring", account="mark", crew_size=3, box=123)
    for approach in ch.BOX_APPROACHES:
        for line in ch.BOX_BUILDUP[approach] + ch.BOX_FAIL_MESSAGES[approach]:
            line.format(**fmt)
        for line in ch.BOX_SUCCESS_MESSAGES[approach]:
            line.format(amount=1_234_567, pct=12, **fmt)
        for line in ch.BOX_ESCAPE_LINES[approach] + ch.BOX_CAUGHT_LINES[approach]:
            line.format(member="@m")


@pytest.mark.parametrize("text,expected", [
    (None, ch.DEFAULT_APPROACH),
    ("", ch.DEFAULT_APPROACH),
    ("cyber", "cyber"),
    ("CYBERWARFARE", "cyber"),
    ("phys", "physical"),
    ("Social Engineering", "social"),
    ("inside job", "inside"),
    ("teleport", None),
])
def test_resolve_approach(text, expected):
    assert ch.resolve_approach(text) == expected


def test_slash_choice_names_fit_discords_limit():
    for choice in ch.CrewHeist.crewheist_slash._params["approach"].choices:
        assert len(choice.name) <= 100


# ---- economy.bank_raid_split: the crew's full sweep -------------------------

def test_bank_raid_split_spares_the_crew_and_splits_evenly():
    g = GUILD + 10
    crew = [A, B, C]
    for u in crew:
        _fresh(g, u, wallet=0, banked=1_000_000)   # crew accounts must be spared
    v1, v2 = OWNER, OWNER + 100
    _fresh(g, v1, banked=1_000_000)
    _fresh(g, v2, banked=500_000)
    _fresh(g, economy.MEMORIAL_USER_ID, banked=1_000_000)
    total_before = economy.get_total_economy(g)
    res = economy.bank_raid_split(g, crew, 0.10)
    assert res["accounts"] == 2
    assert res["total"] == 150_000
    # even split, remainder to the ringleader (first id)
    assert dict(res["paid"]) == {A: 50_000, B: 50_000, C: 50_000}
    for u in crew:
        assert economy.bank_balance(g, u) == 1_000_000
        assert economy.get_coins(g, u) == 50_000
    assert economy.bank_balance(g, v1) == 900_000
    assert economy.bank_balance(g, v2) == 450_000
    assert economy.bank_balance(g, economy.MEMORIAL_USER_ID) == 1_000_000
    assert economy.get_total_economy(g) == total_before, "theft moves money, never mints it"


def test_bank_raid_split_remainder_goes_to_the_ringleader():
    g = GUILD + 11
    _fresh(g, A, wallet=0)
    _fresh(g, B, wallet=0)
    _fresh(g, OWNER, banked=1_000_001)
    res = economy.bank_raid_split(g, [A, B], 0.10)   # 100,000 -> 50,000 each, 0 remainder
    assert dict(res["paid"]) == {A: 50_000, B: 50_000}
    _fresh(g, OWNER, banked=1_000_010)
    res = economy.bank_raid_split(g, [A, B], 0.10)   # 100,001 -> 50,001 / 50,000
    assert dict(res["paid"]) == {A: 50_001, B: 50_000}


def test_bank_raid_split_is_clamped_to_the_raid_ceiling():
    g = GUILD + 12
    _fresh(g, A, wallet=0)
    _fresh(g, OWNER, banked=1_000_000)
    res = economy.bank_raid_split(g, [A], 0.99)
    assert res["total"] == int(1_000_000 * economy.BANK_RAID_MAX_PCT)
    assert economy.bank_raid_split(g, [A], 0.0) == {"total": 0, "accounts": 0, "paid": []}
    assert economy.bank_raid_split(g, [], 0.1) == {"total": 0, "accounts": 0, "paid": []}
