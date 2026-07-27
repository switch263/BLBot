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


def test_credits_saturate_instead_of_overflowing():
    G, U = 9201, 1
    economy.add_coins(G, U, economy.MAX_COINS)
    for _ in range(5):
        economy.add_coins(G, U, economy.MAX_COINS)
        economy.award_coins(G, U, economy.MAX_COINS)
        economy.update_wallet(G, U, economy.MAX_COINS)
    value, storage_type = _raw_money("wallets", "coins", guild_id=G, user_id=U)
    assert storage_type == "integer"  # never promoted to REAL
    assert value == economy.MAX_COINS
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
    assert storage_type == "integer" and value == economy.MAX_COINS


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
    with sqlite3.connect(economy.DB_FILE) as conn:
        conn.execute(
            "UPDATE wallets SET coins = ?, total_won = ?, net_won = ? "
            "WHERE guild_id = ? AND user_id = ?",
            (overflowed, overflowed, -overflowed, G, U))
        conn.execute(
            "INSERT OR REPLACE INTO cog_kv (guild_id, user_id, namespace, key, value) "
            "VALUES (?,?,?,?,?)", (G, U, "bank", "balance", overflowed))
        conn.commit()
        assert _raw_money("wallets", "coins", guild_id=G, user_id=U)[1] == "real"
        economy._repair_overflowed_money(conn)
        conn.commit()
    value, storage_type = _raw_money("wallets", "coins", guild_id=G, user_id=U)
    assert storage_type == "integer" and value == economy.MAX_COINS
    wallet = economy.get_wallet(G, U)
    assert wallet["coins"] == economy.MAX_COINS
    assert wallet["total_won"] == economy.MAX_COINS
    assert economy.bank_balance(G, U) == economy.MAX_COINS
    net = _raw_money("wallets", "net_won", guild_id=G, user_id=U)
    assert net == (-economy.MAX_COINS, "integer")


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
    assert economy.get_coins(G, U) == economy.MAX_COINS


def test_check_bet_rejects_stakes_above_the_ceiling():
    assert economy.check_bet(economy.MAX_COINS) is None
    assert economy.check_bet(economy.MAX_COINS + 1) is not None
    assert economy.check_bet(0) is not None


def test_ceiling_leaves_room_for_guild_wide_sums():
    # get_total_economy sums every wallet; the ceiling must sit far enough
    # below 64 bits that a whole guild's worth of maxed wallets still fits.
    assert economy.MAX_COINS * 1_000 < economy._SQLITE_MAX_INT


def test_repair_handles_null_and_text_money():
    G, U = 9207, 1
    economy.get_wallet(G, U)
    with sqlite3.connect(economy.DB_FILE) as conn:
        conn.execute("UPDATE wallets SET coins = NULL, total_won = 'junk' "
                     "WHERE guild_id = ? AND user_id = ?", (G, U))
        conn.commit()
        economy._repair_overflowed_money(conn)
        conn.commit()
    assert _raw_money("wallets", "coins", guild_id=G, user_id=U) == (0, "integer")
    assert _raw_money("wallets", "total_won", guild_id=G, user_id=U) == (0, "integer")


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
