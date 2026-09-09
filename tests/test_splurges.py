"""The Splurge catalog: data invariants, tier gating, and price escalation."""
import pytest

import economy
import splurges


# --- catalog data ----------------------------------------------------------

def test_price_cap_matches_economy():
    # splurges.py duplicates the ceiling to stay pure — keep them equal.
    assert splurges.MAX_PRICE == economy.MAX_COINS


def test_every_entry_is_well_formed():
    for key, entry in splurges.SPLURGES.items():
        assert key == key.lower() and " " not in key, f"bad key: {key}"
        for field in ("name", "emoji", "tier", "price", "blurb", "flavor"):
            assert entry.get(field), f"{key} missing {field}"
        assert entry["tier"] in splurges.TIERS, f"{key} has an unknown tier"
        assert 0 < entry["price"] <= splurges.MAX_PRICE, f"{key} price out of range"
        assert isinstance(entry["price"], int)


def test_names_and_keys_are_unique():
    names = [e["name"].lower() for e in splurges.SPLURGES.values()]
    assert len(names) == len(set(names))


def test_catalog_is_actually_big():
    # "An entire catalog" — every tier stocked, not a token entry or two.
    assert len(splurges.SPLURGES) >= 50
    for tier in splurges.TIERS:
        assert len(splurges.by_tier(tier)) >= 5, f"tier {tier} is thin"


def test_prices_climb_with_tier():
    # The cheapest thing in a tier must cost more than the priciest thing in
    # the tier below, so the catalog escalates as wealth does.
    tiers = sorted(splurges.TIERS)
    for lower, higher in zip(tiers, tiers[1:]):
        assert (splurges.by_tier(higher)[0][1]["price"]
                > splurges.by_tier(lower)[-1][1]["price"])


def test_tier_requirements_ascend_and_fit_under_the_ceiling():
    reqs = [splurges.tier_requirement(t) for t in sorted(splurges.TIERS)]
    assert reqs == sorted(reqs)
    assert reqs[0] == 0                      # tier 1 is open to everyone
    assert reqs[-1] < economy.MAX_COINS      # the top tier is reachable


# --- tier gating -----------------------------------------------------------

def test_unlocked_tiers_track_wealth():
    assert splurges.unlocked_tiers(0) == [1]
    assert splurges.unlocked_tiers(economy.MAX_COINS) == sorted(splurges.TIERS)
    mid = splurges.tier_requirement(3)
    assert splurges.unlocked_tiers(mid) == [1, 2, 3]
    assert splurges.unlocked_tiers(mid - 1) == [1, 2]


def test_next_tier_points_at_the_next_locked_one():
    assert splurges.next_tier(0) == 2
    assert splurges.next_tier(economy.MAX_COINS) is None


# --- price escalation ------------------------------------------------------

def test_repeat_purchases_get_more_expensive():
    key = "gold_toilet"
    base = splurges.SPLURGES[key]["price"]
    assert splurges.price_for(key, 0) == base
    prices = [splurges.price_for(key, n) for n in range(6)]
    assert prices == sorted(prices)
    assert len(set(prices)) == len(prices)   # strictly climbing, no plateau
    assert prices[-1] > base * 5


def test_escalated_price_never_exceeds_the_ceiling():
    for key in splurges.SPLURGES:
        assert splurges.price_for(key, 500) <= economy.MAX_COINS


def test_negative_owned_is_treated_as_none():
    key = "gold_toilet"
    assert splurges.price_for(key, -3) == splurges.SPLURGES[key]["price"]


# --- lookup ----------------------------------------------------------------

@pytest.mark.parametrize("text,want", [
    ("gold_toilet", "gold_toilet"),
    ("Solid Gold Toilet", "gold_toilet"),
    ("GOLD_TOILET", "gold_toilet"),
    ("taxidermied", "taxidermy_raccoon"),
])
def test_resolve_finds_the_right_splurge(text, want):
    assert splurges.resolve(text) == want


@pytest.mark.parametrize("text", ["", None, "nonsense-item", "the"])
def test_resolve_refuses_unknown_or_ambiguous(text):
    # "the" matches many names — better to ask than to guess wrong and burn
    # coins on the wrong thing.
    assert splurges.resolve(text) is None


# --- ranks -----------------------------------------------------------------

def test_burn_ranks_ascend():
    thresholds = [t for t, _, _ in splurges.BURN_RANKS]
    assert thresholds == sorted(thresholds)
    assert thresholds[0] == 0
    assert splurges.burn_rank(0)[0] == "Tightwad"
    assert splurges.burn_rank(economy.MAX_COINS)[0] == splurges.BURN_RANKS[-1][1]


def test_next_rank_stops_at_the_top():
    assert splurges.next_rank(0)[1] == splurges.BURN_RANKS[1][1]
    assert splurges.next_rank(economy.MAX_COINS) is None


# --- the spend primitive ---------------------------------------------------

def test_burn_purchase_destroys_coins_and_records_atomically():
    G, U = 9401, 1
    economy.add_coins(G, U, 1_000_000)
    economy.get_house_state(G)          # seed the house before measuring
    before_total = economy.get_total_economy(G)
    before_wallet = economy.get_coins(G, U)

    res = economy.burn_purchase(G, U, 250_000, "splurge",
                                [("owned:gold_toilet", 1), ("total_burned", 250_000)])
    assert res["ok"]
    assert res["spent"] == 250_000
    assert res["balance"] == before_wallet - 250_000
    assert res["counters"] == {"owned:gold_toilet": 1, "total_burned": 250_000}
    assert economy.get_coins(G, U) == before_wallet - 250_000
    # A true sink: the coins left the economy entirely, not moved to the house.
    assert economy.get_total_economy(G) == before_total - 250_000
    assert economy.kv_get(G, U, "splurge", "total_burned") == 250_000


def test_burn_purchase_counters_accumulate():
    G, U = 9402, 1
    economy.add_coins(G, U, 1_000_000)
    for _ in range(3):
        economy.burn_purchase(G, U, 1_000, "splurge",
                              [("owned:scratchers", 1), ("total_burned", 1_000)])
    assert economy.kv_get(G, U, "splurge", "owned:scratchers") == 3
    assert economy.kv_get(G, U, "splurge", "total_burned") == 3_000


def test_burn_purchase_charges_nothing_when_broke():
    G, U = 9403, 1
    economy.add_coins(G, U, 500)
    before = economy.get_coins(G, U)
    res = economy.burn_purchase(G, U, 10_000_000, "splurge",
                                [("owned:yacht", 1), ("total_burned", 10_000_000)])
    assert not res["ok"] and res["error"] == "broke"
    assert res["have"] == before
    # Nothing charged AND nothing credited — the whole thing rolled back.
    assert economy.get_coins(G, U) == before
    assert economy.kv_get(G, U, "splurge", "owned:yacht") is None
    assert economy.kv_get(G, U, "splurge", "total_burned") is None


@pytest.mark.parametrize("amount", [0, -1])
def test_burn_purchase_rejects_nonpositive(amount):
    res = economy.burn_purchase(9404, 1, amount, "splurge", [("total_burned", 1)])
    assert not res["ok"] and res["error"] == "invalid_amount"


def test_burn_purchase_respects_the_coin_ceiling():
    G, U = 9405, 1
    economy.add_coins(G, U, economy.MAX_COINS)
    res = economy.burn_purchase(G, U, economy.MAX_COINS, "splurge",
                                [("total_burned", economy.MAX_COINS)])
    assert res["ok"] and res["balance"] == 0
    assert res["counters"]["total_burned"] == economy.MAX_COINS


# --- House profit sharing ---------------------------------------------------
# "Buy Into the House" is the one splurge with a mechanical effect: shareholders
# split HOUSE_PROFIT_SHARE_PCT of house PROFIT and may never gamble again.

def _buy_shares(guild_id, user_id, qty=1):
    """Buy house shares the way cogs/splurge.py does."""
    return economy.burn_purchase(
        guild_id, user_id, 1_000 * qty, "splurge",
        [(economy.SHARES_KEY, qty), ("total_burned", 1_000 * qty)])


def _house_profit(guild_id, amount):
    """Hand the house `amount` of pure profit, from outside the guild's players."""
    economy.add_coins(guild_id, 999, amount)
    economy.transfer_to_house(guild_id, 999, amount, is_bet=False)


def test_share_key_matches_the_catalog_entry():
    # economy credits the SAME cog_kv row the catalog does, so a share count
    # and the trophy inventory can never drift apart.
    assert economy.SHARES_KEY == "owned:" + splurges.SHARES_KEY
    assert splurges.SHARES_KEY in splurges.SPLURGES


def test_shares_are_repeatable_not_unique():
    # You buy INTO profit sharing — more shares, bigger slice. Not a one-off deed.
    assert not splurges.is_unique(splurges.SHARES_KEY)


def test_no_shareholders_by_default():
    G = 9601
    assert economy.get_shareholders(G) == []
    assert economy.total_house_shares(G) == 0
    assert economy.casino_ban_message(G, 1) is None
    assert not economy.is_shareholder(G, 1)


def test_buying_in_makes_you_a_shareholder():
    G, U = 9602, 1
    economy.add_coins(G, U, 100_000)
    assert _buy_shares(G, U)["ok"]
    assert economy.house_shares(G, U) == 1
    assert economy.is_shareholder(G, U)
    assert economy.get_shareholders(G) == [(U, 1)]
    assert economy.casino_ban_message(G, U) is not None
    assert economy.casino_ban_message(G, 2) is None    # nobody else is barred


def test_shareholder_cannot_bet_but_can_still_pay_dues():
    G, U = 9603, 1
    economy.add_coins(G, U, 100_000)
    assert _buy_shares(G, U)["ok"]
    res = economy.transfer_to_house(G, U, 5_000)
    assert not res["ok"] and res["error"] == "shareholder"
    # Tax, bail and fees (is_bet=False) still go through.
    assert economy.transfer_to_house(G, U, 5_000, is_bet=False)["ok"]


def test_bets_are_not_skimmed_anymore():
    # The whole point of profit sharing over a turnover cut: a stake reaches
    # the house intact, so the house edge is untouched.
    G, PLAYER, HOLDER = 9604, 2, 1
    economy.add_coins(G, HOLDER, 100_000)
    economy.add_coins(G, PLAYER, 1_000_000)
    economy.get_house_state(G)
    assert _buy_shares(G, HOLDER)["ok"]
    holder_before = economy.get_coins(G, HOLDER)
    house_before = economy.get_house_state(G)
    res = economy.transfer_to_house(G, PLAYER, 100_000)
    assert res["ok"]
    house_after = economy.get_house_state(G)
    assert (house_after["on_hand"] + house_after["reserve"]
            == house_before["on_hand"] + house_before["reserve"] + 100_000)
    assert economy.get_coins(G, HOLDER) == holder_before   # paid later, not now


def test_first_settle_only_sets_the_baseline():
    G, U = 9605, 1
    economy.add_coins(G, U, 100_000)
    economy.get_house_state(G)
    _house_profit(G, 5_000_000)          # profit made BEFORE anyone bought in
    assert _buy_shares(G, U)["ok"]
    before = economy.get_coins(G, U)
    res = economy.settle_house_dividends(G)
    assert res["baseline"] and res["paid"] == 0
    # Profit that predates the investment isn't theirs.
    assert economy.get_coins(G, U) == before


def test_dividend_pays_a_cut_of_new_profit_only():
    G, U = 9606, 1
    economy.add_coins(G, U, 100_000)
    economy.get_house_state(G)
    assert _buy_shares(G, U)["ok"]
    economy.settle_house_dividends(G)                    # set the baseline
    before = economy.get_coins(G, U)

    _house_profit(G, 10_000_000)
    res = economy.settle_house_dividends(G)
    expected = int(10_000_000 * economy.HOUSE_PROFIT_SHARE_PCT)
    assert res["profit"] == 10_000_000
    assert res["paid"] == expected
    assert economy.get_coins(G, U) == before + expected

    # Settling again immediately pays nothing — the same profit isn't paid twice.
    assert economy.settle_house_dividends(G)["paid"] == 0
    assert economy.get_coins(G, U) == before + expected


def test_dividend_splits_pro_rata_and_dilutes():
    G, A, B = 9607, 1, 2
    economy.add_coins(G, A, 100_000)
    economy.add_coins(G, B, 100_000)
    economy.get_house_state(G)
    assert _buy_shares(G, A, qty=3)["ok"]
    assert _buy_shares(G, B, qty=1)["ok"]
    economy.settle_house_dividends(G)
    a_before, b_before = economy.get_coins(G, A), economy.get_coins(G, B)

    _house_profit(G, 8_000_000)
    res = economy.settle_house_dividends(G)
    pool = int(8_000_000 * economy.HOUSE_PROFIT_SHARE_PCT)
    assert res["shares"] == 4
    # A holds 3 of 4 shares, B holds 1 — three times the slice.
    assert economy.get_coins(G, A) - a_before == pool * 3 // 4
    assert economy.get_coins(G, B) - b_before == pool * 1 // 4


def test_losing_house_pays_nothing_and_keeps_its_mark():
    G, U, PLAYER = 9608, 1, 2
    economy.add_coins(G, U, 100_000)
    economy.get_house_state(G)
    assert _buy_shares(G, U)["ok"]
    economy.settle_house_dividends(G)
    mark = economy.settle_house_dividends(G)["high_water"]
    before = economy.get_coins(G, U)

    economy.casino_payout(G, PLAYER, 20_000_000)     # the house takes a beating
    res = economy.settle_house_dividends(G)
    assert res["paid"] == 0
    assert economy.get_coins(G, U) == before          # no dividend, no clawback
    assert res["high_water"] == mark                  # mark holds; must earn back


def test_house_must_earn_back_a_loss_before_dividends_resume():
    G, U, PLAYER = 9609, 1, 2
    economy.add_coins(G, U, 100_000)
    economy.get_house_state(G)
    assert _buy_shares(G, U)["ok"]
    economy.settle_house_dividends(G)
    before = economy.get_coins(G, U)

    economy.casino_payout(G, PLAYER, 30_000_000)      # down 30m
    _house_profit(G, 10_000_000)                      # recover 10m — still under
    assert economy.settle_house_dividends(G)["paid"] == 0
    assert economy.get_coins(G, U) == before

    _house_profit(G, 25_000_000)                      # now genuinely ahead
    res = economy.settle_house_dividends(G)
    assert res["paid"] > 0
    # Only the amount ABOVE the old mark counts as profit, not the recovery.
    assert res["profit"] == 5_000_000
    assert economy.get_coins(G, U) == before + int(5_000_000 * economy.HOUSE_PROFIT_SHARE_PCT)


def test_settle_is_a_noop_without_shareholders():
    G = 9610
    economy.get_house_state(G)
    _house_profit(G, 10_000_000)
    assert economy.settle_house_dividends(G) == {
        "paid": 0, "profit": 0, "payouts": [], "shares": 0,
        "high_water": 0, "baseline": False}


def test_dividends_never_mint():
    G, U = 9611, 1
    economy.add_coins(G, U, 100_000)
    economy.get_house_state(G)
    assert _buy_shares(G, U)["ok"]
    economy.settle_house_dividends(G)
    _house_profit(G, 12_000_000)
    total_before = economy.get_total_economy(G)
    res = economy.settle_house_dividends(G)
    assert res["paid"] > 0
    # House -> shareholder is a transfer; the guild-wide total doesn't move.
    assert economy.get_total_economy(G) == total_before


# --- The ladder must stay sized against its anchor --------------------------
# The catalog went bottom-heavy once already: the coin ceiling was raised
# 9,200x and the top tier was left unlocking at 0.005% of it, so the richest
# players unlocked everything immediately and had nothing left to buy. The
# ceiling is a 1e300 guard now, so the ladder anchors to its own
# LADDER_TOP instead; these pin the shape to that anchor so it can't drift
# silently. When players actually live past LADDER_TOP, raise it AND add tiers.

def test_top_tier_unlocks_near_the_ladder_top():
    top = max(splurges.TIERS)
    req = splurges.tier_requirement(top)
    share = req / splurges.LADDER_TOP
    # Reachable, but genuinely late-game: somewhere in the last order of
    # magnitude of the wealth curve the catalog covers.
    assert 0.01 <= share <= 0.5, (
        f"top tier unlocks at {share:.4%} of LADDER_TOP — the ladder has drifted "
        f"out of sync with its anchor; rescale the tiers or LADDER_TOP.")


def test_priciest_splurge_is_a_real_fraction_of_the_ladder_top():
    top_price = max(e["price"] for e in splurges.SPLURGES.values())
    share = top_price / splurges.LADDER_TOP
    assert 0.1 <= share <= 1.0, (
        f"priciest splurge is {share:.4%} of LADDER_TOP — nothing in the catalog "
        f"meaningfully drains a player at the top of the ladder.")


def test_ladder_top_sits_far_below_the_guard():
    # The anchor is a design number, not the storage guard: the guard is
    # meant to be unreachable, the ladder is meant to be climbed.
    assert splurges.LADDER_TOP < economy.MAX_COINS // 10**50


def test_escalation_survives_absurd_ownership_counts():
    # 1.6 ** 5000 overflows a float; the price must clamp, not raise.
    assert splurges.price_for("gold_toilet", 5_000) == splurges.MAX_PRICE


def test_tiers_are_evenly_spaced_with_no_dead_zone():
    # No gap between consecutive unlocks bigger than 1000x: a gap larger than
    # that is a stretch of the wealth curve with nothing new to buy.
    reqs = [splurges.tier_requirement(t) for t in sorted(splurges.TIERS)][1:]
    for lower, higher in zip(reqs, reqs[1:]):
        assert higher <= lower * 1_000, (
            f"dead zone between {lower:,} and {higher:,} — {higher // lower}x "
            f"of wealth with no new tier")


def test_every_tier_is_fully_stocked():
    for tier in splurges.TIERS:
        assert len(splurges.by_tier(tier)) == 8, f"tier {tier} is not stocked"
