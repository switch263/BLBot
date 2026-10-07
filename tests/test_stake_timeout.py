"""A game that times out holding a stake hands it back instead of keeping it:
game_common.StakeView refunds an idle game, a click claims the game exactly
once, and progress games cash out what the player already earned."""
import asyncio

import pytest

import economy

pytest.importorskip("discord")

import hotdog  # noqa: E402
import methgator  # noqa: E402
import vault  # noqa: E402
from game_common import STAKE_TIMEOUT, StakeView  # noqa: E402

GUILD = 810_001
USER = 810_002
BET = 1_000


def _staked(guild):
    """Fresh wallet with BET already collected into the house."""
    economy.delete_wallet(guild, USER)
    economy.get_wallet(guild, USER)
    economy.add_coins(guild, USER, 10 * BET)  # STARTING_COINS can't cover BET
    before = economy.get_coins(guild, USER)
    assert economy.transfer_to_house(guild, USER, BET)["ok"]
    return before


def _run(coro_fn):
    # discord.ui.View needs a running loop to construct.
    return asyncio.run(coro_fn())


def test_timeout_is_five_minutes():
    assert STAKE_TIMEOUT == 300

    async def go():
        return StakeView(GUILD, USER, BET).timeout
    assert _run(go) == STAKE_TIMEOUT


def test_idle_single_choice_game_refunds_the_stake():
    before = _staked(GUILD)

    async def go():
        view = methgator.MethGatorView(None, GUILD, USER, BET)
        await view.on_timeout()
        return view
    view = _run(go)
    assert economy.get_coins(GUILD, USER) == before
    assert all(child.disabled for child in view.children)
    # A refund isn't a game: nothing recorded.
    assert "methgator" not in economy.get_game_stats(GUILD, USER)


def test_timeout_after_a_click_moves_nothing():
    before = _staked(GUILD + 1)

    async def go():
        view = methgator.MethGatorView(None, GUILD + 1, USER, BET)
        assert view.settle()          # the player's click claims the game
        assert not view.settle()      # a double-click doesn't resolve twice
        await view.on_timeout()       # and the timeout doesn't refund it
    _run(go)
    assert economy.get_coins(GUILD + 1, USER) == before - BET


class _Cog:
    def _render(self, g, footer=None, final=False):
        return footer or ""


def test_idle_hotdog_with_progress_auto_taps_out():
    before = _staked(GUILD + 2)

    async def go():
        game = hotdog.HotDogGame(GUILD + 2, USER, "p", BET)
        game.eaten, game.multiplier = 2, 1.5
        view = hotdog.HotDogView(_Cog(), game)
        await view.on_timeout()
        return game
    game = _run(go)
    assert game.ended
    assert economy.get_coins(GUILD + 2, USER) == before - BET + int(BET * 1.5)


def test_idle_vault_refunds_only_before_the_first_guess():
    before = _staked(GUILD + 3)
    cfg = vault.DIFFICULTIES["normal"]

    async def untouched():
        await vault.VaultView(_Cog(), vault.VaultGame(GUILD + 3, USER, "p", BET, cfg)).on_timeout()
    _run(untouched)
    assert economy.get_coins(GUILD + 3, USER) == before

    assert economy.transfer_to_house(GUILD + 3, USER, BET)["ok"]

    async def mid_crack():
        game = vault.VaultGame(GUILD + 3, USER, "p", BET, cfg)
        game.attempts.append(([0, 1, 2, 3], "x"))
        await vault.VaultView(_Cog(), game).on_timeout()
    _run(mid_crack)
    assert economy.get_coins(GUILD + 3, USER) == before - BET
