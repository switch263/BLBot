"""Shared preamble for game cogs — the standard opening moves, once.

Every bet-driven cog used to hand-roll the same ~35 lines: detect slash vs
prefix, build a reply() adapter, guard guild-only, check jail, parse the bet,
validate it against MAX_BET, collect it via transfer_to_house, and surface the
broke/error replies. That block drifted between cogs (different messages,
missing checks, no `10k` parsing in older ones). This module is that block,
with a name.

Usage in a cog:

    from game_common import casino_prelude

    async def _start(self, ctx_or_interaction, bet):
        start = await casino_prelude(ctx_or_interaction, bet,
                                     zero_msg="You gotta risk something, coward.")
        if start is None:
            return  # an error reply was already sent
        game = MyGame(start.guild.id, start.user.id, start.user.display_name, start.bet)
        await start.reply(self._render(game), view=MyView(self, game))

Pass `collect=False` for games that don't take the stake up front (lobby
games, PvP escrow) — the bet is parsed and validated but not moved. Pass
`bet=None` for commands with no stake at all (you get guild/jail/reply only).

Because the bet parses with `available=` (wallet, capped at MAX_BET), players
can stake `all`, `half`, or `40%` in every converted game for free.

Pure glue — talks to economy.py, never to SQLite.
"""
import discord

from economy import MAX_BET, check_bet, get_coins, jail_message, transfer_to_house
from amount import parse_amount, amount_error


class GameStart:
    """What a successful prelude hands back: where, who, how much, and how
    to answer. `reply` works for both slash and prefix and returns the sent
    message (so games can edit it in place)."""

    __slots__ = ("guild", "user", "bet", "reply", "is_slash")

    def __init__(self, guild, user, bet, reply, is_slash):
        self.guild = guild
        self.user = user
        self.bet = bet
        self.reply = reply
        self.is_slash = is_slash


async def casino_prelude(
    ctx_or_interaction,
    bet=None,
    *,
    collect: bool = True,
    zero_msg: str = "Bet > 0.",
    no_guild_msg: str = "Server only.",
) -> GameStart | None:
    """Run the standard casino-command preamble. Returns a GameStart, or None
    after having already sent the appropriate error reply.

    Steps: guild guard -> jail gate -> parse bet (numbers, 10k/1.5m, and
    all/half/% against min(wallet, MAX_BET)) -> positive + MAX_BET check ->
    (optionally) collect the stake into the house with broke handling.
    """
    is_slash = isinstance(ctx_or_interaction, discord.Interaction)
    guild = ctx_or_interaction.guild
    user = ctx_or_interaction.user if is_slash else ctx_or_interaction.author

    async def reply(content=None, **kwargs):
        if not is_slash:
            kwargs.pop("ephemeral", None)  # prefix messages can't be ephemeral
            return await ctx_or_interaction.send(content, **kwargs)
        if ctx_or_interaction.response.is_done():
            return await ctx_or_interaction.followup.send(content, **kwargs)
        await ctx_or_interaction.response.send_message(content, **kwargs)
        return await ctx_or_interaction.original_response()

    async def err(content):
        # Validation noise (bad amounts, broke, wrong context) is the player's
        # business, not the channel's — ephemeral on slash, plain on prefix.
        return await reply(content, ephemeral=True)

    if not guild:
        await err(no_guild_msg)
        return None

    # Jail stays PUBLIC on purpose: the shame is part of the sentence.
    jmsg = jail_message(guild.id, user.id)
    if jmsg:
        await reply(jmsg)
        return None

    if bet is None:
        return GameStart(guild, user, None, reply, is_slash)

    # Plain numbers parse without touching the DB; only the contextual forms
    # (all/half/%) need to know the wallet, so the balance read is lazy.
    amt = parse_amount(bet)
    if amt is None:
        stakeable = min(get_coins(guild.id, user.id), MAX_BET)
        amt = parse_amount(bet, available=stakeable)
    if amt is None:
        await err(amount_error(bet, contextual=True))
        return None
    bet = amt

    if bet <= 0:
        await err(zero_msg)
        return None
    check_err = check_bet(bet)
    if check_err:
        await err(check_err)
        return None

    if collect:
        res = transfer_to_house(guild.id, user.id, bet)
        if not res.get("ok"):
            if res.get("error") == "broke":
                await err(f"Too broke. Balance: **{res.get('have', 0):,}**")
            else:
                await err("Bet failed. Try again.")
            return None

    return GameStart(guild, user, bet, reply, is_slash)
