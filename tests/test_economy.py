"""Economy invariants: money conservation, bank interest, reserve self-heal,
house drain caps. Runs against the scratch DB conftest points at — each test
uses its own guild id so state never bleeds between tests."""
import sqlite3
import time
from unittest import mock

import economy


def test_transfer_and_payout_conserve_money():
    G, U = 9001, 1
    economy.add_coins(G, U, 10_000)
    economy.get_house_state(G)  # first touch seeds the reserve — measure after
    start_total = economy.get_total_economy(G)
    res = economy.transfer_to_house(G, U, 5_000)
    assert res["ok"]
    paid = economy.casino_payout(G, U, 2_500)
    assert paid == 2_500
    assert economy.get_total_economy(G) == start_total


def test_transfer_rejects_broke():
    G, U = 9002, 1
    economy.get_wallet(G, U)  # starts at STARTING_COINS
    res = economy.transfer_to_house(G, U, 10**9)
    assert not res["ok"] and res["error"] == "broke"


def test_bank_deposit_withdraw_roundtrip():
    G, U = 9003, 1
    economy.add_coins(G, U, 10_000)
    before = economy.get_coins(G, U)
    assert economy.bank_deposit(G, U, 4_000)["ok"]
    assert economy.bank_balance(G, U) == 4_000
    assert economy.bank_withdraw(G, U, 4_000)["ok"]
    assert economy.get_coins(G, U) == before
    assert not economy.bank_withdraw(G, U, 1)["ok"]  # empty account


def test_bank_interest_one_year():
    G, U = 9004, 1
    economy.add_coins(G, U, 1_000)
    economy.bank_deposit(G, U, 500)
    now = time.time()
    with sqlite3.connect(economy.DB_FILE) as conn:
        conn.execute(
            "UPDATE cog_kv SET value=? WHERE guild_id=? AND namespace='bank' AND key='interest_ts'",
            (now - economy._SECONDS_PER_YEAR, G))
        conn.commit()
    assert economy.bank_balance(G, U) == int(500 * (1 + economy.BANK_INTEREST_APR))


def test_bank_interest_not_starved_by_frequent_reads():
    G, U = 9005, 1
    economy.add_coins(G, U, 1_000)
    economy.bank_deposit(G, U, 550)
    now = time.time()
    for hours in range(1, 24 * 30 + 1):  # 30 days of hourly reads
        with mock.patch("time.time", lambda h=hours: now + h * 3600):
            economy.bank_balance(G, U)
    with mock.patch("time.time", lambda: now + 24 * 30 * 3600):
        final = economy.bank_balance(G, U)
    expected = int(550 * ((1 + economy.BANK_INTEREST_APR) ** (30 / 365.25)))
    assert final == expected and final > 550


def test_bank_no_backaccrual_across_empty_period():
    G, U = 9006, 1
    economy.add_coins(G, U, 10_000)
    economy.bank_deposit(G, U, 1_000)
    economy.bank_withdraw(G, U, 1_000)
    later = time.time() + 100 * 24 * 3600
    with mock.patch("time.time", lambda: later):
        economy.bank_balance(G, U)
        economy.bank_deposit(G, U, 1_000)
    with mock.patch("time.time", lambda: later + 1):
        assert economy.bank_balance(G, U) == 1_000


def test_reserve_self_heals_from_on_hand():
    G = 9007
    H = economy.get_house_id()
    economy.get_house_state(G)  # seed
    with sqlite3.connect(economy.DB_FILE) as conn:
        # Bind the amount — underscore digit separators in raw SQL need
        # SQLite >= 3.46, which CI's Ubuntu runner doesn't have.
        conn.execute("UPDATE house_reserve SET coins=?, last_interest_ts=? WHERE guild_id=?",
                     (10_000_000, time.time(), G))
        conn.execute("INSERT OR REPLACE INTO wallets (guild_id, user_id, coins) VALUES (?,?,?)",
                     (G, H, 500_000_000))
        conn.commit()
    st = economy.get_house_state(G)
    assert st["reserve"] == economy.HOUSE_STARTING_COINS
    assert st["on_hand"] + st["reserve"] == 510_000_000  # transfer, not minting


def test_drain_caps_are_sane():
    assert 0 <= economy.HOUSE_HEIST_MIN_PCT <= economy.HOUSE_HEIST_MAX_PCT < 1
    assert 0 <= economy.GREEN_JACKPOT_MIN_PCT <= economy.GREEN_JACKPOT_MAX_PCT < 1
    assert 0 <= economy.BANK_RAID_MIN_PCT <= economy.BANK_RAID_MAX_PCT < 1
    assert economy.BANK_INTEREST_APR < economy.HOUSE_INTEREST_APR  # house out-earns depositors


def test_wealth_tax_knobs():
    assert 0 < economy.WEALTH_TAX_PCT < 0.1
    assert 1 <= economy.WEALTH_TAX_DAY <= 28  # must exist in every month
    assert economy.WEALTH_TAX_THRESHOLD > 0


def test_kv_top_leaderboard():
    G = 9008
    for uid, n in ((1, 5), (2, 12), (3, 7)):
        economy.kv_incr(G, uid, "cmdstats", "__total__", n)
    economy.kv_incr(G, 0, "cmdstats", "__total__", 99)  # guild aggregate row
    top = economy.kv_top(G, "cmdstats", "__total__", limit=2)
    assert top == [(2, 12), (3, 7)]  # user 0 excluded, sorted desc, limited
