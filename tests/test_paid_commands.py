"""/roast and /yourmother cost a flat fee paid INTO the house pot. The
memorial refusal is free, a broke player is charged nothing and roasted for
being poor instead, and a delivered line carries the receipt."""
import pytest

import economy
import taunts
import yomama

pytest.importorskip("discord")
pytest.importorskip("PIL")  # cogs/yourmother.py pulls in the portrait renderer

from game_common import charge_fee, fee_trailer  # noqa: E402
import roast  # noqa: E402
import yourmother  # noqa: E402

GUILD = 800_001
USER = 800_002


def _with(guild, user, coins):
    economy.delete_wallet(guild, user)
    economy.get_wallet(guild, user)
    have = economy.get_coins(guild, user)
    if have:
        economy.try_deduct(guild, user, have)
    if coins:
        economy.add_coins(guild, user, coins)


def test_charge_fee_goes_into_the_house_pot():
    _with(GUILD, USER, 250_000)
    house_before = economy.get_house_state(GUILD)   # seeds the house wallet first
    total_before = economy.get_total_economy(GUILD)
    assert charge_fee(GUILD, USER, 100_000, "A roast") is None
    assert economy.get_coins(GUILD, USER) == 150_000
    house_after = economy.get_house_state(GUILD)
    assert house_after["on_hand"] + house_after["reserve"] == \
        house_before["on_hand"] + house_before["reserve"] + 100_000, "house revenue, not a burn"
    assert economy.get_total_economy(GUILD) == total_before, "nothing destroyed"


def test_charge_fee_roasts_the_broke_without_charging():
    _with(GUILD + 1, USER, 99_999)
    msg = charge_fee(GUILD + 1, USER, 100_000, "A roast")
    assert msg and "100,000" in msg and "99,999" in msg
    assert any(line in msg for line in taunts._load("broke")), "the bot roasts them for being poor"
    assert economy.get_coins(GUILD + 1, USER) == 99_999


def test_both_fees_are_100k():
    assert roast.ROAST_FEE == 100_000
    assert yourmother.YOURMOTHER_FEE == 100_000


class _User:
    def __init__(self, uid):
        self.id = uid
        self.mention = f"<@{uid}>"
        self.display_name = f"user{uid}"


def test_roast_charges_only_when_delivered():
    g = GUILD + 2
    _with(g, USER, 150_000)
    cog = roast.Roast(bot=None)
    # Memorial target: the refusal line, nothing charged.
    out = cog._generate_roast(g, USER, economy.MEMORIAL_USER_ID, "<@m>")
    assert out in roast.MEMORIAL_RESPONSES
    assert economy.get_coins(g, USER) == 150_000
    # A real roast: charged, receipt attached.
    out = cog._generate_roast(g, USER, USER + 1, "<@t>")
    assert out.endswith(fee_trailer(roast.ROAST_FEE))
    assert economy.get_coins(g, USER) == 50_000
    # Now broke: refusal, unchanged balance.
    out = cog._generate_roast(g, USER, USER + 1, "<@t>")
    assert any(line in out for line in taunts._load("broke"))
    assert economy.get_coins(g, USER) == 50_000


def test_yourmother_charges_only_when_delivered():
    g = GUILD + 3
    _with(g, USER, 150_000)
    cog = yourmother.YourMother(bot=None)
    out = cog._joke_for(g, USER, _User(economy.MEMORIAL_USER_ID), None)
    assert isinstance(out, str) and out in yourmother.MEMORIAL_RESPONSES
    assert economy.get_coins(g, USER) == 150_000
    out = cog._joke_for(g, USER, _User(USER + 1), None)
    # (chat text, caption text, art flavor, receipt) — flavor steers the portrait.
    assert isinstance(out, tuple) and len(out) == 4
    assert out[2] in yomama.CATEGORIES
    assert out[3] == fee_trailer(yourmother.YOURMOTHER_FEE)
    assert economy.get_coins(g, USER) == 50_000
    out = cog._joke_for(g, USER, _User(USER + 1), None)
    assert isinstance(out, str) and any(line in out for line in taunts._load("broke"))
    assert economy.get_coins(g, USER) == 50_000
