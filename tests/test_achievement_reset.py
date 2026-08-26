"""A wipe must not resurrect achievements.

clear_economy / delete_wallet PRESERVE `game_stats` on purpose, and almost every
achievement condition is computed from those stats. Wiping the unlock ledger in
cog_kv while the stats survive means the whole catalog instantly re-qualifies on
the next command — a channel flood of re-announcements and a second payment of
every reward. These pin the ledger as wipe-proof.
"""
import economy

GUILD = 990_001
USER = 990_002
NS = "achievements"


def _seed(guild, user):
    economy.get_wallet(guild, user)          # create the wallet
    economy.record_game(guild, user, "blackjack", True)
    economy.kv_set(guild, user, NS, "card_shark", 1234)
    economy.kv_set(guild, user, "bank", "balance", 500)


def test_clear_economy_keeps_achievements_but_wipes_other_kv():
    _seed(GUILD, USER)
    economy.clear_economy(GUILD)
    assert economy.kv_get(GUILD, USER, NS, "card_shark") == 1234
    assert economy.kv_get(GUILD, USER, "bank", "balance") is None
    # The stats that earned it survive too — that's why the ledger must.
    assert economy.get_game_stats(GUILD, USER)["blackjack"]["plays"] == 1


def test_delete_wallet_keeps_achievements_but_wipes_other_kv():
    g, u = GUILD + 1, USER + 1
    _seed(g, u)
    economy.delete_wallet(g, u)
    assert economy.kv_get(g, u, NS, "card_shark") == 1234
    assert economy.kv_get(g, u, "bank", "balance") is None
    assert economy.get_game_stats(g, u)["blackjack"]["plays"] == 1


def test_kept_namespaces_are_scoped_to_the_guild():
    """A wipe of one guild leaves another guild's kv alone (and vice versa)."""
    g1, g2, u = GUILD + 2, GUILD + 3, USER + 2
    _seed(g1, u)
    _seed(g2, u)
    economy.clear_economy(g1)
    assert economy.kv_get(g2, u, "bank", "balance") == 500
    assert economy.kv_get(g2, u, NS, "card_shark") == 1234


def test_keep_list_and_clause_agree():
    assert "achievements" in economy._CLEAR_ECONOMY_KEEP_NAMESPACES
    assert economy._KEEP_NS_CLAUSE.count("?") == len(economy._CLEAR_ECONOMY_KEEP_NAMESPACES)


def test_fresh_player_earns_nothing():
    """A brand-new player at zero state must satisfy NO achievement condition —
    otherwise every reset hands out a starter pack. `rank` is 0 for them: the
    cog only calls it #1 when they are strictly ahead of second place."""
    # `cogs/` shadows the repo root on sys.path, so load the catalog by path.
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "achievement_catalog", Path(__file__).resolve().parents[1] / "achievements.py")
    catalog = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(catalog)
    ACHIEVEMENTS = catalog.ACHIEVEMENTS
    ctx = {
        "balance": economy.STARTING_COINS, "total_won": 0, "total_lost": 0,
        "spins": 0, "jackpots": 0, "games": {}, "total_plays": 0,
        "total_wins": 0, "distinct_games": 0, "items_owned": 0, "rank": 0,
    }
    earned = [aid for aid, a in ACHIEVEMENTS.items() if a["cond"](ctx)]
    assert earned == [], f"a fresh wallet already qualifies for: {earned}"
