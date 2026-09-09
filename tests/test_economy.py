"""Economy invariants: money conservation, bank interest, reserve self-heal,
house drain caps. Runs against the scratch DB conftest points at — each test
uses its own guild id so state never bleeds between tests."""
import sqlite3
import time
from unittest import mock

import pytest

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


def test_refund_from_house_is_exact_undo():
    G, U = 9010, 1
    economy.add_coins(G, U, 50_000)
    economy.get_house_state(G)  # seed the reserve before measuring
    start_total = economy.get_total_economy(G)
    before = economy.get_wallet(G, U)
    res = economy.transfer_to_house(G, U, 10_000, is_bet=False)
    assert res["ok"]
    assert economy.refund_from_house(G, U, 10_000) == 10_000
    after = economy.get_wallet(G, U)
    assert after["coins"] == before["coins"]
    # A refund is not a win: no stat drift on the round trip.
    assert after["total_won"] == before["total_won"]
    assert economy.get_total_economy(G) == start_total


def test_wealth_leaderboard_counts_bank():
    G, S = 9009, economy.STARTING_COINS
    # user 1: 10k all in wallet; user 2: 12k total but mostly banked
    economy.add_coins(G, 1, 10_000)
    economy.add_coins(G, 2, 12_000)
    economy.bank_deposit(G, 2, 11_000)
    rows = economy.get_wealth_leaderboard(G)
    assert [(r[0], r[1]) for r in rows] == [(2, 12_000 + S), (1, 10_000 + S)]
    uid, wealth, coins, banked, won, lost = rows[0]
    assert (coins, banked) == (1_000 + S, 11_000)
    # wallet-only leaderboard still ranks by cash on hand
    wallet_rows = economy.get_leaderboard(G)
    assert wallet_rows[0][0] == 1


def test_bankrupting_payout_logs_event_and_drains_both_buckets():
    G, U = 9101, 1
    economy.get_house_state(G)  # first touch seeds the reserve
    economy.add_coins(G, U, 1_000)
    assert economy.transfer_to_house(G, U, 1_000)["ok"]
    state = economy.get_house_state(G)
    total_house = state["on_hand"] + state["reserve"]
    owed = total_house + 500_000
    paid = economy.casino_payout(G, U, owed)
    assert 0 < paid < owed  # everything the house had, but not what was owed
    events = economy.pop_bankruptcy_events(G)
    assert len(events) == 1
    assert events[0]["user_id"] == U
    assert events[0]["owed"] == owed
    assert events[0]["paid"] == paid
    assert economy.pop_bankruptcy_events(G) == []  # pop clears the list
    state = economy.get_house_state(G)
    assert state["on_hand"] == 0 and state["reserve"] == 0


def test_fully_covered_payout_logs_no_event():
    G, U = 9102, 1
    economy.get_house_state(G)
    economy.add_coins(G, U, 1_000)
    assert economy.transfer_to_house(G, U, 500)["ok"]
    assert economy.casino_payout(G, U, 500) == 500
    assert economy.pop_bankruptcy_events(G) == []


def test_cover_house_shortfall_taxes_banks_evenly():
    G, W, A, B = 9103, 1, 2, 3
    economy.add_coins(G, A, 100_000)
    economy.bank_deposit(G, A, 100_000)
    economy.add_coins(G, B, 300_000)
    economy.bank_deposit(G, B, 300_000)
    economy.add_coins(G, W, 10_000)
    economy.bank_deposit(G, W, 10_000)  # winner's own bank must be untouched
    wallet_before = economy.get_coins(G, W)
    res = economy.cover_house_shortfall(G, W, 200_000)
    assert res["pct"] == 0.5
    assert res["seized"] == 200_000
    assert res["accounts"] == 2
    assert res["paid"] == 200_000
    assert res["still_short"] == 0
    assert economy.bank_balance(G, A) == 50_000
    assert economy.bank_balance(G, B) == 150_000
    assert economy.bank_balance(G, W) == 10_000
    assert economy.get_coins(G, W) == wallet_before + 200_000


def test_cover_house_shortfall_empties_banks_when_debt_is_bigger():
    G, W, A = 9104, 1, 2
    economy.add_coins(G, A, 50_000)
    economy.bank_deposit(G, A, 50_000)
    res = economy.cover_house_shortfall(G, W, 1_000_000)
    assert res["pct"] == 1.0
    assert res["seized"] == 50_000
    assert res["paid"] == 50_000
    assert res["still_short"] == 950_000
    assert economy.bank_balance(G, A) == 0


def test_mint_house_bailout_pays_winner_and_counts_as_winnings():
    G, U = 9105, 1
    before = economy.get_wallet(G, U)
    assert economy.mint_house_bailout(G, U, 750_000) == 750_000
    after = economy.get_wallet(G, U)
    assert after["coins"] == before["coins"] + 750_000
    assert after["total_won"] == before["total_won"] + 750_000
    assert economy.mint_house_bailout(G, U, 0) == 0
    assert economy.mint_house_bailout(G, U, -5) == 0


def test_get_wealth_counts_wallet_and_bank():
    G, U = 9106, 1
    economy.add_coins(G, U, 10_000)
    wallet_only = economy.get_wealth(G, U)
    assert wallet_only == economy.get_coins(G, U)
    economy.bank_deposit(G, U, 8_000)
    assert economy.get_wealth(G, U) == wallet_only  # moving money doesn't change wealth


def test_fine_user_wealth_falls_through_to_bank():
    G, U = 9107, 1
    economy.add_coins(G, U, 20_000)
    economy.bank_deposit(G, U, 15_000)
    wallet = economy.get_coins(G, U)  # 5_000 + STARTING_COINS
    # Fine bigger than the wallet: wallet emptied, remainder from the bank.
    fine = wallet + 4_000
    assert economy.fine_user_wealth(G, U, fine) == fine
    assert economy.get_coins(G, U) == 0
    assert economy.bank_balance(G, U) == 11_000
    # Fine bigger than everything: collects what exists, never goes negative.
    assert economy.fine_user_wealth(G, U, 1_000_000) == 11_000
    assert economy.get_coins(G, U) == 0
    assert economy.bank_balance(G, U) == 0
    assert economy.fine_user_wealth(G, U, 0) == 0


# --- The coin ceiling -------------------------------------------------------
# SQLite silently promotes an overflowed INTEGER expression to REAL, which is
# how wallets turned into 9.2e+18 floats. These pin down that no money value
# can climb there again, and that the repair migration heals a DB that already
# did.

def _raw_money(table, column, **where):
    """Read a money cell straight from SQLite, with its storage type."""
    clause = " AND ".join(f"{k} = ?" for k in where)
    with sqlite3.connect(economy.DB_FILE) as conn:
        return conn.execute(
            f"SELECT {column}, typeof({column}) FROM {table} WHERE {clause}",
            tuple(where.values()),
        ).fetchone()


def test_credits_saturate_at_the_guard_instead_of_overflowing():
    G, U = 9201, 1
    economy.add_coins(G, U, economy.MAX_COINS)
    for _ in range(5):
        economy.add_coins(G, U, economy.MAX_COINS)
        economy.award_coins(G, U, economy.MAX_COINS)
        economy.update_wallet(G, U, economy.MAX_COINS)
    value, storage_type = _raw_money("wallets", "coins", guild_id=G, user_id=U)
    assert storage_type == "text"  # digits, never a promoted REAL
    assert economy._to_int(value) == economy.MAX_COINS
    assert economy.get_wallet(G, U)["total_won"] == economy.MAX_COINS


def test_payout_leaves_coins_in_house_when_winner_is_capped():
    G, U = 9202, 1
    economy.get_house_state(G)
    economy.add_coins(G, U, economy.MAX_COINS)  # winner is at the ceiling
    economy.add_coins(G, 2, 500_000)
    assert economy.transfer_to_house(G, 2, 500_000)["ok"]
    on_hand_before = economy.get_house_state(G)["on_hand"]
    assert economy.casino_payout(G, U, 400_000) == 0  # no room, nothing paid
    assert economy.get_house_state(G)["on_hand"] == on_hand_before  # house kept it
    assert economy.get_coins(G, U) == economy.MAX_COINS
    # ...and the ceiling is not mistaken for the house being broke.
    assert economy.pop_bankruptcy_events(G) == []


def test_transfer_trims_to_receiver_headroom_without_burning_coins():
    G, A, B = 9203, 1, 2
    economy.add_coins(G, A, 10_000)
    # Leave B exactly 4,000 short of the ceiling (the wallet opens at
    # STARTING_COINS, so subtract that too).
    economy.add_coins(G, B, economy.MAX_COINS - 4_000 - economy.STARTING_COINS)
    start_total = economy.get_total_economy(G)
    res = economy.transfer_coins(G, A, B, 10_000)
    assert res["ok"] and res["amount"] == 4_000  # only what fit moved
    assert economy.get_coins(G, B) == economy.MAX_COINS
    assert economy.get_total_economy(G) == start_total  # remainder stayed with A
    # A receiver with no headroom at all refuses rather than eating the coins.
    assert economy.transfer_coins(G, A, B, 1_000) == {
        "ok": False, "error": "capped", "have": economy.MAX_COINS}


def test_bank_deposit_and_interest_cannot_overflow():
    G, U = 9204, 1
    economy.add_coins(G, U, economy.MAX_COINS)
    economy.bank_deposit(G, U, economy.MAX_COINS)
    assert economy.bank_balance(G, U) == economy.MAX_COINS
    # Backdate the clock a century: compounding must clamp, not explode.
    with sqlite3.connect(economy.DB_FILE) as conn:
        conn.execute(
            "UPDATE cog_kv SET value=? WHERE guild_id=? AND namespace='bank' AND key='interest_ts'",
            (time.time() - 100 * economy._SECONDS_PER_YEAR, G))
        conn.commit()
    assert economy.bank_balance(G, U) == economy.MAX_COINS
    value, storage_type = _raw_money(
        "cog_kv", "value", guild_id=G, user_id=U, namespace="bank", key="balance")
    assert storage_type == "text" and economy._to_int(value) == economy.MAX_COINS


def test_grow_survives_absurd_elapsed_time():
    # A zeroed/corrupt timestamp asks for (1.15 ** a_billion) — inf as a float,
    # and int(inf) raises. Elapsed time clamps first, so the result stays a
    # sane, finite int instead of pinning the balance at the ceiling.
    grown = economy._grow(1_000, 0.15, 10**9)
    assert grown == int(1_000 * 1.15 ** economy._MAX_INTEREST_YEARS)
    assert 1_000 < grown < economy.MAX_COINS
    # A big balance compounding for a long time still clamps at the ceiling.
    assert economy._grow(economy.MAX_COINS, 0.15, 10**9) == economy.MAX_COINS
    assert economy._grow(1_000, 0.15, 0) == 1_000
    assert economy._grow(0, 0.15, 5) == 0


def test_repair_migration_heals_overflowed_money():
    G, U = 9205, 1
    economy.get_wallet(G, U)
    overflowed = 9.223372036854776e18  # what SQLite leaves behind on overflow
    healed = int(overflowed)           # 2**63 — the digits the float meant
    with economy._connect() as conn:
        conn.execute(
            "UPDATE wallets SET coins = ?, total_won = ?, net_won = ? "
            "WHERE guild_id = ? AND user_id = ?",
            (overflowed, overflowed, -overflowed, G, U))
        conn.execute(
            "INSERT OR REPLACE INTO cog_kv (guild_id, user_id, namespace, key, value) "
            "VALUES (?,?,?,?,?)", (G, U, "bank", "balance", overflowed))
        conn.commit()
        # A float written straight into a TEXT money column lands as SQLite's
        # text rendering of it (15 or 17 significant digits depending on the
        # SQLite build); the untyped cog_kv cell keeps the REAL itself.
        raw = _raw_money("wallets", "coins", guild_id=G, user_id=U)
        assert raw[1] == "text" and "e+" in raw[0]
        rendered = economy._to_int(raw[0])   # what those digits actually say
        assert _raw_money("cog_kv", "value", guild_id=G, user_id=U,
                          namespace="bank", key="balance")[1] == "real"
        economy._repair_overflowed_money(conn)
        conn.commit()
    value, storage_type = _raw_money("wallets", "coins", guild_id=G, user_id=U)
    assert storage_type == "text" and value.isdigit()
    assert int(value) == rendered                 # exact for what was stored
    assert abs(int(value) - healed) <= healed // 10**13   # within the rendering's precision
    wallet = economy.get_wallet(G, U)
    assert wallet["coins"] == int(value)
    assert wallet["total_won"] == int(value)
    assert economy.bank_balance(G, U) == healed   # exact: it was still a REAL
    net = _raw_money("wallets", "net_won", guild_id=G, user_id=U)
    assert net[1] == "text" and net[0] == "-" + value


def test_reads_never_hand_a_cog_a_float():
    G, U = 9206, 1
    economy.get_wallet(G, U)
    with sqlite3.connect(economy.DB_FILE) as conn:
        conn.execute("UPDATE wallets SET coins = ? WHERE guild_id = ? AND user_id = ?",
                     (9.223372036854776e18, G, U))
        conn.commit()
    # Repair hasn't run for this row; the read path still must not leak a float.
    assert isinstance(economy.get_coins(G, U), int)
    assert isinstance(economy.get_wallet(G, U)["coins"], int)
    # SQLite builds render the float into the TEXT column at 15 or 17
    # significant digits, so compare within that precision, not exactly.
    assert abs(economy.get_coins(G, U) - 2**63) <= 2**63 // 10**13


def test_check_bet_rejects_stakes_above_the_ceiling():
    assert economy.check_bet(economy.MAX_COINS) is None
    assert economy.check_bet(economy.MAX_COINS + 1) is not None
    assert economy.check_bet(0) is not None


def test_guard_is_far_past_int64_but_under_float_max():
    # Money is arbitrary precision now; MAX_COINS is a sanity guard, not the
    # storage limit. int64 is where values switch to text. The guard must stay
    # below float max with room for a payout multiplier: cogs still compute
    # int(bet * mult), and that raises OverflowError past ~1.8e308.
    assert economy._SQLITE_MAX_INT == 2**63 - 1
    assert economy.MAX_COINS == 10**300 - 1
    assert economy.MAX_COINS > economy._SQLITE_MAX_INT ** 5
    assert float(economy.MAX_COINS) * 1_000 < float("inf")
    assert int(float(economy.MAX_COINS) * 100) > economy.MAX_COINS  # 100x a maxed bet still fits


def test_a_maxed_value_actually_round_trips_through_sqlite():
    # The guard is worthless if the guard value itself can't be stored.
    G, U = 9270, 1
    economy.add_coins(G, U, economy.MAX_COINS)
    assert economy.get_coins(G, U) == economy.MAX_COINS
    value, kind = _raw_money("wallets", "coins", guild_id=G, user_id=U)
    assert kind == "text" and value == str(economy.MAX_COINS)


def test_money_functions_do_exact_arithmetic_past_int64():
    # The money_* SQL functions run in Python, so a sum that would overflow
    # a 64-bit SQLite integer comes back as exact digits, not a REAL.
    with economy._connect() as conn:
        big = economy._SQLITE_MAX_INT
        raw = conn.execute("SELECT typeof(? + ?)", (big, big)).fetchone()[0]
        assert raw == "real"          # what bare SQL arithmetic would do
        value, kind = conn.execute(
            "SELECT money_add(?, ?), typeof(money_add(?, ?))",
            (big, big, big, big)).fetchone()
        assert kind == "text" and int(value) == 2 * big
        # Small results stay integers so untyped cog_kv counters keep their type.
        assert conn.execute("SELECT typeof(money_add(1, 2))").fetchone()[0] == "integer"
        assert conn.execute("SELECT money_cmp(?, ?)", (10**30, 10**29)).fetchone()[0] == 1
        assert conn.execute("SELECT money_cmp('9', '10')").fetchone()[0] == -1
        assert conn.execute("SELECT money_sub_floor(5, 9)").fetchone()[0] == 0


def test_guild_totals_survive_many_maxed_wallets():
    # Guild-wide totals are summed in Python, so they are NOT bounded by 64
    # bits — 50 maxed wallets sum to 5e19, well past what SQL SUM() could hold.
    G = 9250
    for uid in range(1, 51):
        economy.add_coins(G, uid, economy.MAX_COINS)
    total = economy.get_total_economy(G)
    assert total > economy._SQLITE_MAX_INT
    assert total >= 50 * economy.MAX_COINS
    stats = economy.get_server_stats(G)
    assert stats["total_coins"] >= 50 * economy.MAX_COINS
    assert stats["players"] == 50


def test_repair_handles_null_and_text_money():
    G, U = 9207, 1
    economy.get_wallet(G, U)
    with economy._connect() as conn:
        conn.execute("UPDATE wallets SET coins = NULL, total_won = 'junk' "
                     "WHERE guild_id = ? AND user_id = ?", (G, U))
        conn.commit()
        economy._repair_overflowed_money(conn)
        conn.commit()
    assert _raw_money("wallets", "coins", guild_id=G, user_id=U) == ("0", "text")
    assert _raw_money("wallets", "total_won", guild_id=G, user_id=U) == ("0", "text")


# --- Ceiling strikes --------------------------------------------------------
# A payout the ceiling refused. economy.py logs it; cogs/coincap.py drains the
# queue and blames the player publicly.

def test_capped_payout_logs_a_ceiling_strike():
    G, U = 9301, 1
    economy.get_house_state(G)
    economy.add_coins(G, U, economy.MAX_COINS)      # winner is at the ceiling
    economy.add_coins(G, 2, 900_000)
    assert economy.transfer_to_house(G, 2, 900_000)["ok"]
    assert economy.casino_payout(G, U, 400_000) == 0
    events = economy.pop_ceiling_events(G)
    assert len(events) == 1
    ev = events[0]
    assert ev["user_id"] == U
    assert ev["owed"] == 400_000 and ev["paid"] == 0 and ev["lost"] == 400_000
    assert ev["source"] == "payout"
    assert economy.pop_ceiling_events(G) == []       # pop clears the queue
    # A ceiling strike is NOT a bankruptcy — the house was flush.
    assert economy.pop_bankruptcy_events(G) == []


def test_partially_capped_payout_reports_only_the_lost_part():
    G, U = 9302, 1
    economy.get_house_state(G)
    economy.add_coins(G, U, economy.MAX_COINS - 1_000 - economy.STARTING_COINS)
    economy.add_coins(G, 2, 900_000)
    assert economy.transfer_to_house(G, 2, 900_000)["ok"]
    assert economy.casino_payout(G, U, 5_000) == 1_000  # only what fit
    ev = economy.pop_ceiling_events(G)[0]
    assert (ev["owed"], ev["paid"], ev["lost"]) == (5_000, 1_000, 4_000)


def test_uncapped_payout_logs_no_strike():
    G, U = 9303, 1
    economy.get_house_state(G)
    economy.add_coins(G, U, 10_000)
    assert economy.transfer_to_house(G, U, 5_000)["ok"]
    assert economy.casino_payout(G, U, 5_000) == 5_000
    assert economy.pop_ceiling_events(G) == []


def test_capped_bailout_survives_the_empty_mint():
    # mint_house_bailout mints nothing when the winner is maxed — but the
    # strike must still be committed, not rolled back with the empty write.
    G, U = 9304, 1
    economy.add_coins(G, U, economy.MAX_COINS)
    assert economy.mint_house_bailout(G, U, 250_000) == 0
    ev = economy.pop_ceiling_events(G)[0]
    assert ev["source"] == "bailout" and ev["lost"] == 250_000


def test_capped_refund_logs_a_strike():
    G, U = 9305, 1
    economy.get_house_state(G)
    economy.add_coins(G, 2, 800_000)
    assert economy.transfer_to_house(G, 2, 800_000, is_bet=False)["ok"]
    economy.add_coins(G, U, economy.MAX_COINS)
    assert economy.refund_from_house(G, U, 300_000) == 0
    ev = economy.pop_ceiling_events(G)[0]
    assert ev["source"] == "refund" and ev["lost"] == 300_000


def test_pending_event_queue_is_bounded():
    G, U = 9306, 1
    economy.add_coins(G, U, economy.MAX_COINS)
    for _ in range(economy._CEILING_MAX_PENDING + 5):
        economy.mint_house_bailout(G, U, 1_000)
    assert len(economy.pop_ceiling_events(G)) == economy._CEILING_MAX_PENDING


def test_wealth_leaderboard_survives_maxed_wallets():
    # `wealth` used to be `w.coins + COALESCE(b.value, 0)` in SQL, with no
    # clamp to absorb an overflow — at a high ceiling that returns a float and
    # /richest prints scientific notation. It is summed in Python now.
    G = 9260
    economy.add_coins(G, 1, economy.MAX_COINS)
    economy.bank_deposit(G, 1, economy.MAX_COINS // 2)
    economy.add_coins(G, 2, economy.MAX_COINS // 4)
    rows = economy.get_wealth_leaderboard(G)
    assert rows[0][0] == 1
    for row in rows:
        for value in row:
            assert isinstance(value, int), f"non-int in leaderboard row: {row}"
    uid, wealth, coins, banked, _, _ = rows[0]
    assert wealth == coins + banked
    assert wealth > economy.MAX_COINS   # a real total above any single cap


# --- Past int64: money keeps growing ---------------------------------------
# Money columns are TEXT and every operation runs through Python ints, so a
# balance is not bounded by SQLite's 64-bit integer. These pin that.

BIG = 10**30  # comfortably past int64 (9.2e18)


def test_balances_grow_past_int64():
    G, U = 9401, 1
    for _ in range(3):
        economy.add_coins(G, U, economy._SQLITE_MAX_INT)
    want = 3 * economy._SQLITE_MAX_INT + economy.STARTING_COINS
    assert economy.get_coins(G, U) == want
    value, kind = _raw_money("wallets", "coins", guild_id=G, user_id=U)
    assert kind == "text" and value == str(want)
    assert economy.get_wallet(G, U)["total_won"] == 3 * economy._SQLITE_MAX_INT


def test_house_flow_conserves_money_past_int64():
    G, U = 9402, 1
    economy.add_coins(G, U, 3 * BIG)
    economy.get_house_state(G)
    start_total = economy.get_total_economy(G)
    assert economy.transfer_to_house(G, U, 2 * BIG)["ok"]
    assert economy.get_house_state(G)["on_hand"] >= 2 * BIG
    assert economy.casino_payout(G, U, 2 * BIG) == 2 * BIG
    assert economy.get_coins(G, U) == 3 * BIG + economy.STARTING_COINS
    assert economy.get_total_economy(G) == start_total
    # net_won is signed and also text-backed: stake down, payout back up.
    assert economy.get_all_net_winnings(G) == [(U, 0)] or \
        dict(economy.get_all_net_winnings(G))[U] == 0


def test_transfer_and_deduct_guards_compare_numerically():
    G, A, B = 9403, 1, 2
    economy.add_coins(G, A, BIG)
    have = economy.get_coins(G, A)
    # "10000...0" vs "9": a text comparison would call the bigger one smaller.
    assert not economy.try_deduct(G, A, have + 1)
    assert economy.try_deduct(G, A, have)
    assert economy.get_coins(G, A) == 0
    economy.add_coins(G, A, BIG)
    res = economy.transfer_coins(G, A, B, BIG - 1)
    assert res["ok"] and res["amount"] == BIG - 1
    assert economy.get_coins(G, B) == BIG - 1 + economy.STARTING_COINS
    assert economy.transfer_coins(G, A, B, BIG)["error"] == "broke"


def test_bank_and_interest_past_int64():
    # Time is frozen: at 10% APR a 1e30 account earns ~3e21 coins a SECOND,
    # so anything but a pinned clock makes exact equality meaningless.
    G, U = 9404, 1
    T = time.time()
    with mock.patch("time.time", lambda: T):
        economy.add_coins(G, U, BIG)
        assert economy.bank_deposit(G, U, BIG)["ok"]
        assert economy.bank_balance(G, U) == BIG
        with sqlite3.connect(economy.DB_FILE) as conn:
            conn.execute(
                "UPDATE cog_kv SET value=? WHERE guild_id=? AND namespace='bank' AND key='interest_ts'",
                (T - economy._SECONDS_PER_YEAR, G))
            conn.commit()
        # Decimal interest math: 10% of 1e30 is exact, not float-rounded.
        assert economy.bank_balance(G, U) == BIG * 11 // 10
        res = economy.bank_withdraw(G, U, BIG * 11 // 10)
        assert res["ok"] and res["amount"] == BIG * 11 // 10
        assert economy.get_coins(G, U) == BIG * 11 // 10 + economy.STARTING_COINS


def test_interest_reads_do_not_mint_on_huge_balances():
    # The old float growth factor carried 16 digits; on a 30-digit balance
    # its rounding error alone minted ~1e14 coins per read. Two reads a few
    # microseconds apart must now differ by real interest only.
    G, U = 9411, 1
    economy.add_coins(G, U, 10**40)
    assert economy.bank_deposit(G, U, 10**40)["ok"]
    a = economy.bank_balance(G, U)
    b = economy.bank_balance(G, U)
    # Real interest on 1e40 at 10% APR over ~1ms is ~3e28; a float-precision
    # error would be ~1e24 *on top* of that on every read, so bound it tightly.
    assert 0 <= b - a < 10**40 * 0.1 / economy._SECONDS_PER_YEAR * 1.0


def test_grow_never_converts_the_balance_to_a_float():
    huge = 10**80
    assert economy._grow(huge, 0.15, 1.0) == huge * 115 // 100
    near_max = 10**290
    assert economy._grow(near_max, 0.10, 1.0) == near_max * 11 // 10
    assert economy._grow(economy.MAX_COINS, 0.15, 10**9) == economy.MAX_COINS


def test_leaderboards_rank_big_values_numerically():
    G = 9405
    economy.add_coins(G, 1, 10**20)
    economy.add_coins(G, 2, 9 * 10**19)
    economy.add_coins(G, 3, 5)
    rows = economy.get_leaderboard(G, limit=10)
    assert [r[0] for r in rows] == [1, 2, 3]
    assert all(isinstance(v, int) for r in rows for v in r)
    economy.bank_deposit(G, 3, 5)
    economy.add_coins(G, 3, 10**21)
    wealth = economy.get_wealth_leaderboard(G, limit=10)
    assert [r[0] for r in wealth] == [3, 1, 2]
    assert economy.get_total_economy(G) >= 10**21 + 10**20 + 9 * 10**19


def test_kv_counters_pass_int64():
    G, U = 9406, 1
    economy.kv_incr(G, U, "t", "n", economy._SQLITE_MAX_INT)
    total = economy.kv_incr(G, U, "t", "n", economy._SQLITE_MAX_INT)
    assert economy._to_int(total) == 2 * economy._SQLITE_MAX_INT
    economy.kv_incr(G, 2, "t", "n", 7)
    economy.kv_incr(G, 3, "t", "n", 10**25)
    assert [uid for uid, _ in economy.kv_top(G, "t", "n")] == [3, U, 2]
    # Small counters stay SQLite integers — cogs that do arithmetic on
    # kv_get() results keep working.
    assert _raw_money("cog_kv", "value", guild_id=G, user_id=2, namespace="t", key="n") == (7, "integer")


def test_burn_purchase_and_splurge_counters_past_int64():
    G, U = 9407, 1
    economy.add_coins(G, U, BIG)
    res = economy.burn_purchase(G, U, BIG, "splurge", [("total_burned", BIG), ("owned:x", 1)])
    assert res["ok"] and res["counters"]["total_burned"] == BIG
    assert res["counters"]["owned:x"] == 1
    assert economy.get_coins(G, U) == economy.STARTING_COINS


def test_jail_bail_past_int64():
    G, J, P = 9408, 1, 2
    economy.jail_user(G, J, 3600, "test", bail_amount=BIG)
    assert economy.get_jail_info(G, J)["bail_amount"] == BIG
    assert economy.get_active_jails(G)[0]["bail_amount"] == BIG
    economy.add_coins(G, P, BIG - 1 - economy.STARTING_COINS)
    assert economy.pay_bail(G, J, P)["error"] == "broke"
    economy.add_coins(G, P, 1)
    res = economy.pay_bail(G, J, P)
    assert res["ok"] and res["amount"] == BIG
    assert economy.get_coins(G, P) == 0
    assert economy.get_house_state(G)["on_hand"] >= BIG


def test_bounty_and_fines_past_int64():
    G, A, B = 9409, 1, 2
    economy.add_coins(G, A, 2 * BIG)
    res = economy.place_jail_bounty(G, A, B, BIG, success=True, jail_seconds=60,
                                    channel_id=0)
    assert res["ok"] and res["success"]
    assert economy.get_coins(G, A) == BIG + economy.STARTING_COINS
    economy.fine_user(G, A, 3 * BIG)   # floors at zero, never negative
    assert economy.get_coins(G, A) == 0
    T = time.time()
    with mock.patch("time.time", lambda: T):   # no interest between steps
        economy.add_coins(G, A, BIG)
        economy.bank_deposit(G, A, BIG // 2)
        assert economy.fine_user_wealth(G, A, BIG) == BIG
        assert economy.get_wealth(G, A) == 0


def test_disburse_and_ransom_past_int64():
    G = 9410
    economy.add_coins(G, 1, 3 * BIG)
    res = economy.disburse(G, 1, [(2, BIG), (3, BIG)])
    assert res["ok"] and res["total"] == 2 * BIG
    assert economy.get_coins(G, 2) == BIG + economy.STARTING_COINS
    T = time.time()
    with mock.patch("time.time", lambda: T):   # no interest between steps
        economy.bank_deposit(G, 2, BIG)
        res = economy.ransom_collect(G, 2, 3, BIG + 50)
    assert res["ok"] and res["from_bank"] == BIG and res["from_wallet"] == 50


def _old_schema_db(path):
    """A pre-migration economy.db: INTEGER money columns, one overflowed
    wallet, an index on bounty_log, a duplicate-key insert that the PK must
    still reject after the rebuild."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE wallets (guild_id INTEGER, user_id INTEGER,
            coins INTEGER DEFAULT 100, total_won INTEGER DEFAULT 0,
            total_lost INTEGER DEFAULT 0, net_won INTEGER DEFAULT 0,
            spins INTEGER DEFAULT 0, jackpots INTEGER DEFAULT 0,
            last_daily TEXT DEFAULT '', PRIMARY KEY (guild_id, user_id));
        CREATE TABLE house_reserve (guild_id INTEGER PRIMARY KEY,
            coins INTEGER NOT NULL DEFAULT 0, last_interest_ts REAL NOT NULL DEFAULT 0);
        CREATE TABLE jail (guild_id INTEGER, user_id INTEGER, until_ts REAL NOT NULL,
            reason TEXT DEFAULT '', bail_amount INTEGER DEFAULT 0,
            channel_id INTEGER DEFAULT 0, jailed_at REAL DEFAULT 0,
            extended_seconds INTEGER DEFAULT 0, no_release INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id));
        CREATE TABLE bounty_log (guild_id INTEGER NOT NULL, placer_user_id INTEGER NOT NULL,
            target_user_id INTEGER NOT NULL, bet INTEGER NOT NULL, ts REAL NOT NULL);
        CREATE INDEX idx_bounty_log_guild_ts ON bounty_log (guild_id, ts);
        CREATE TABLE cog_kv (guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            namespace TEXT NOT NULL, key TEXT NOT NULL, value,
            PRIMARY KEY (guild_id, user_id, namespace, key));
        INSERT INTO wallets (guild_id, user_id, coins, total_won, net_won, spins)
            VALUES (1, 1, 12345, 500, -20, 3);
        INSERT INTO wallets (guild_id, user_id, coins) VALUES (1, 2, 9.223372036854776e18);
        INSERT INTO house_reserve VALUES (1, 100000000, 12.5);
        INSERT INTO jail VALUES (1, 1, 9e12, 'why', 777, 42, 0, 0, 0);
        INSERT INTO bounty_log VALUES (1, 1, 2, 55, 1.0);
        INSERT INTO cog_kv VALUES (1, 1, 'bank', 'balance', 9.223372036854776e18);
        INSERT INTO cog_kv VALUES (1, 1, 'bank', 'interest_ts', 1.5);
    """)
    conn.commit()
    conn.close()


def test_migration_rebuilds_integer_schema_as_text(tmp_path):
    path = str(tmp_path / "old.db")
    _old_schema_db(path)
    with mock.patch.object(economy, "DB_FILE", path):
        with economy._connect() as conn:
            economy._convert_money_columns_to_text(conn)
            economy._repair_overflowed_money(conn)
            conn.commit()
            # Idempotent: a second pass finds nothing to rebuild.
            economy._convert_money_columns_to_text(conn)
            conn.commit()
        with sqlite3.connect(path) as conn:
            for table, column, _neg in economy._MONEY_COLUMNS:
                info = {r[1]: r[2] for r in conn.execute(f"PRAGMA table_info({table})")}
                assert info[column].upper() == "TEXT", (table, column)
            # Non-money columns keep their types; defaults and PKs survive.
            info = {r[1]: r for r in conn.execute("PRAGMA table_info(wallets)")}
            assert info["spins"][2] == "INTEGER" and info["last_daily"][4] == "''"
            assert conn.execute("SELECT coins, total_won, net_won, spins FROM wallets "
                                "WHERE user_id = 1").fetchone() == ("12345", "500", "-20", 3)
            assert conn.execute("SELECT coins, typeof(coins) FROM wallets "
                                "WHERE user_id = 2").fetchone() == (str(2**63), "text")
            assert conn.execute("SELECT coins, last_interest_ts FROM house_reserve"
                                ).fetchone() == ("100000000", 12.5)
            assert conn.execute("SELECT bail_amount, channel_id FROM jail").fetchone() == ("777", 42)
            assert conn.execute("SELECT bet FROM bounty_log").fetchone() == ("55",)
            assert conn.execute("SELECT name FROM sqlite_master WHERE type='index' "
                                "AND name='idx_bounty_log_guild_ts'").fetchone()
            assert conn.execute("SELECT value, typeof(value) FROM cog_kv WHERE key='balance'"
                                ).fetchone() == (str(2**63), "text")
            assert conn.execute("SELECT value FROM cog_kv WHERE key='interest_ts'"
                                ).fetchone() == (1.5,)
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO wallets (guild_id, user_id) VALUES (1, 1)")
        # And the module's own helpers read the migrated rows correctly.
        assert economy.get_wallet(1, 1)["coins"] == 12345
        assert economy.get_coins(1, 2) == 2**63
        assert economy.get_jail_info(1, 1)["bail_amount"] == 777
