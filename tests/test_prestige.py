"""The prestige system + the bank-only PvP heist (economy.py).

Prestige is a voluntary fortune reset: zero the wallet AND bank in exchange for
a permanent, stacking boost to wins/loot and a per-level surcharge on bets/bail.
These tests pin the ladder shape, the integer multiplier/surcharge math, the
auto-applied win boost, the all-or-nothing buy, and bank_heist's bank->wallet
transfer with headroom trimming.
"""
import economy

GUILD = 880_001
USER = 880_002
OTHER = 880_003
VICTIM = 880_004
THIEF = 880_005


def _fresh(guild, user, wallet=0, banked=0):
    """Put a player at an exact wallet/bank split, prestige level 0."""
    economy.delete_wallet(guild, user)
    economy.get_wallet(guild, user)
    economy.kv_delete(guild, user, "bank", "balance")
    economy.kv_delete(guild, user, "bank", "interest_ts")
    economy.kv_delete(guild, user, "prestige", "level")
    have = economy.get_coins(guild, user)
    if have:
        economy.try_deduct(guild, user, have)
    if wallet + banked:
        economy.add_coins(guild, user, wallet + banked)
    if banked:
        assert economy.bank_deposit(guild, user, banked)["ok"]


def _set_level(guild, user, level):
    economy.kv_set(guild, user, "prestige", "level", level)


# ---- the ladder --------------------------------------------------------------

def test_ladder_digit_counts():
    digits = economy.PRESTIGE_THRESH_DIGITS
    assert digits[0] == 10
    assert digits[-1] == 290
    assert all(digits[i] < digits[i + 1] for i in range(len(digits) - 1)), \
        "digit counts must be strictly increasing"
    assert economy.PRESTIGE_MAX_LEVEL == len(digits) - 1


def test_threshold_is_monotonic_and_capped_at_max():
    mx = economy.PRESTIGE_MAX_LEVEL
    thresholds = [economy.prestige_threshold(lvl) for lvl in range(mx)]
    assert all(t is not None for t in thresholds)
    assert all(thresholds[i] < thresholds[i + 1] for i in range(len(thresholds) - 1))
    # Each threshold is a number with exactly PRESTIGE_THRESH_DIGITS[lvl] digits.
    for lvl in range(mx):
        assert len(str(thresholds[lvl])) == economy.PRESTIGE_THRESH_DIGITS[lvl]
    # You can't buy once you're at (or past) the top.
    assert economy.prestige_threshold(mx) is None
    assert economy.prestige_threshold(mx + 5) is None
    assert economy.prestige_threshold(-1) is None


# ---- multiplier / surcharge math ---------------------------------------------

def test_win_and_loot_mult_are_one_plus_level():
    _fresh(GUILD, USER)
    assert economy.prestige_win_mult(GUILD, USER) == 1
    assert economy.prestige_loot_mult(GUILD, USER) == 1
    _set_level(GUILD, USER, 7)
    assert economy.prestige_win_mult(GUILD, USER) == 8
    assert economy.prestige_loot_mult(GUILD, USER) == 8


def test_surcharge_is_exact_integer_math():
    _fresh(GUILD, USER)
    # Level 0 leaves the amount untouched.
    assert economy.prestige_surcharge(GUILD, USER, 1_000_000) == 1_000_000
    # Level 4 -> amount * (4+4)//4 == amount * 2.
    _set_level(GUILD, USER, 4)
    assert economy.prestige_surcharge(GUILD, USER, 1_000_000) == 2_000_000
    # +25% per level, floored (integer only).
    _set_level(GUILD, USER, 1)
    assert economy.prestige_surcharge(GUILD, USER, 100) == 125
    _set_level(GUILD, USER, 1)
    assert economy.prestige_surcharge(GUILD, USER, 101) == 126  # 101*5//4 == 126
    assert isinstance(economy.prestige_surcharge(GUILD, USER, 101), int)


def test_item_drop_bonus_capped():
    _fresh(GUILD, USER)
    assert economy.prestige_item_drop_bonus(GUILD, USER, 0.10) == 0.10
    _set_level(GUILD, USER, 3)
    assert abs(economy.prestige_item_drop_bonus(GUILD, USER, 0.10) - 0.25) < 1e-9
    _set_level(GUILD, USER, 100)
    assert economy.prestige_item_drop_bonus(GUILD, USER, 0.10) == 0.85


# ---- casino_payout auto-applies the boost ------------------------------------

def test_prestiged_winner_is_paid_more():
    g = GUILD + 1
    _fresh(g, USER)       # level 0
    _fresh(g, OTHER)
    _set_level(g, OTHER, 3)  # win mult == 4
    plain = economy.casino_payout(g, USER, 10_000)
    boosted = economy.casino_payout(g, OTHER, 10_000)
    assert plain == 10_000
    assert boosted == 40_000, "a level-3 player's 10k win pays 4x"


# ---- prestige_buy ------------------------------------------------------------

def test_buy_zeroes_wallet_and_bank_and_records():
    g = GUILD + 2
    _fresh(g, USER, wallet=800, banked=400)   # wealth 1200
    before_lifetime = economy._to_int(
        economy.kv_get(g, USER, "prestige_lifetime", "levels", 0))
    res = economy.prestige_buy(g, USER, threshold=1_000, new_level=1, lifetime_gain=1)
    assert res["ok"]
    assert res["old_level"] == 0 and res["new_level"] == 1
    assert economy.get_coins(g, USER) == 0, "wallet wiped"
    assert economy.bank_balance(g, USER) == 0, "bank wiped"
    assert economy.prestige_level(g, USER) == 1
    after_lifetime = economy._to_int(
        economy.kv_get(g, USER, "prestige_lifetime", "levels", 0))
    assert after_lifetime == before_lifetime + 1


def test_buy_rejected_when_too_poor():
    g = GUILD + 3
    _fresh(g, USER, wallet=500, banked=100)   # wealth 600
    res = economy.prestige_buy(g, USER, threshold=1_000, new_level=1, lifetime_gain=1)
    assert not res["ok"] and res["error"] == "short"
    assert res["have"] == 600
    # Nothing moved — the fortune is intact and the level unchanged.
    assert economy.get_coins(g, USER) == 500
    assert economy.bank_balance(g, USER) == 100
    assert economy.prestige_level(g, USER) == 0


# ---- bank_heist --------------------------------------------------------------

def test_bank_heist_moves_bank_to_wallet_leaving_victim_wallet_alone():
    g = GUILD + 4
    _fresh(g, VICTIM, wallet=100_000, banked=500_000)
    _fresh(g, THIEF, wallet=0)
    res = economy.bank_heist(g, VICTIM, THIEF, 0.5)
    assert res["ok"]
    assert res["amount"] == 250_000
    assert res["victim_bank_after"] == 250_000
    assert economy.bank_balance(g, VICTIM) == 250_000
    assert economy.get_coins(g, VICTIM) == 100_000, "the wallet is never touched"
    assert economy.get_coins(g, THIEF) == 250_000


def test_bank_heist_trims_to_thief_headroom():
    g = GUILD + 5
    _fresh(g, VICTIM, banked=1_000_000)
    _fresh(g, THIEF, wallet=0)
    economy.add_coins(g, THIEF, economy.MAX_COINS)
    res = economy.bank_heist(g, VICTIM, THIEF, 0.5)
    assert not res["ok"] and res["error"] == "capped"
    assert economy.bank_balance(g, VICTIM) == 1_000_000, "victim keeps it all"


def test_bank_heist_empty_victim():
    g = GUILD + 6
    _fresh(g, VICTIM, wallet=5_000, banked=0)
    _fresh(g, THIEF, wallet=0)
    res = economy.bank_heist(g, VICTIM, THIEF, 0.5)
    assert not res["ok"] and res["error"] == "empty"
    assert economy.get_coins(g, THIEF) == 0


def test_bank_heist_conserves_money():
    g = GUILD + 7
    _fresh(g, VICTIM, wallet=50_000, banked=300_000)
    _fresh(g, THIEF, wallet=1_000)
    before = economy.get_wealth(g, VICTIM) + economy.get_wealth(g, THIEF)
    economy.bank_heist(g, VICTIM, THIEF, 0.3)
    after = economy.get_wealth(g, VICTIM) + economy.get_wealth(g, THIEF)
    assert after == before, "a heist moves coins, it never creates them"


def test_bank_heist_memorial_guarded():
    m = economy.MEMORIAL_USER_ID
    assert economy.bank_heist(GUILD, m, THIEF, 0.5)["error"] == "memorial"
    assert economy.bank_heist(GUILD, VICTIM, m, 0.5)["error"] == "memorial"
