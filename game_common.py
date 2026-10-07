"""Shared preamble for game cogs — the standard opening moves, once.

Every bet-driven cog used to hand-roll the same ~35 lines: detect slash vs
prefix, build a reply() adapter, guard guild-only, check jail, parse the bet,
validate it, collect it via transfer_to_house, and surface the
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
Pass `gate=fn` for a per-game refusal that must run BEFORE any coins move —
a cooldown, a one-game-at-a-time lock: `fn(guild_id, user_id)` returns the
refusal text, or None to let the player through.

Because the bet parses with `available=` (the wallet), players can stake
`all`, `half`, or `40%` in every converted game for free.

Pure glue — talks to economy.py, never to SQLite.
"""
import discord

from economy import (casino_ban_message, check_bet, get_coins, jail_message,
                     refund_from_house, transfer_to_house)
from amount import parse_amount, amount_error
from taunts import broke_taunt


def charge_fee(guild_id: int, user_id: int, amount: int, label: str) -> str | None:
    """Collect a flat fee for a non-game command (/roast, /yourmother) INTO
    THE HOUSE POT — house revenue that fattens the on-hand bucket for heists
    and jackpots, not a burn. `is_bet=False`, so shareholders can pay it too.
    Atomic and balance-checked. Returns None once the fee is taken. A player
    who can't cover it is charged nothing and gets ROASTED for being poor
    instead — the returned text is a hand-written broke taunt (taunts.py)
    with the cost and their balance as the receipt, meant to be sent publicly
    in place of whatever they were trying to buy."""
    res = transfer_to_house(guild_id, user_id, amount, is_bet=False)
    if res.get("ok"):
        return None
    have = res.get("have", get_coins(guild_id, user_id))
    return (f"💸 {broke_taunt()}\n"
            f"-# {label} costs {amount:,} coins. You have {have:,}.")


def fee_trailer(amount: int) -> str:
    """The receipt line appended to a paid command's output."""
    return f"\n-# −{amount:,} coins. Worth it."


def parse_wallet_amount(text, guild_id: int, user_id: int) -> int | None:
    """parse_amount against a player's WALLET, so `all`, `half` and `50%`
    work. The one way any command that takes coins should read its amount —
    every coin input accepts the contextual forms, not just the prelude games.
    Plain numbers parse without touching the DB; only the contextual forms
    need the balance, so the wallet read is lazy. Pair it with
    `amount_error(text, contextual=True)` so the help text advertises them."""
    amt = parse_amount(text)
    if amt is None:
        amt = parse_amount(text, available=get_coins(guild_id, user_id))
    return amt


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
    gate=None,
) -> GameStart | None:
    """Run the standard casino-command preamble. Returns a GameStart, or None
    after having already sent the appropriate error reply.

    Steps: guild guard -> jail gate -> shareholder gate -> the game's own
    `gate(guild_id, user_id)` if given -> parse bet (numbers, 10k/1.5m, and
    all/half/% against the wallet) -> positive check ->
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

    # House shareholders don't gamble against their own casino. Also public —
    # the whole point of buying in was for everyone to know.
    ban = casino_ban_message(guild.id, user.id)
    if ban:
        await reply(ban)
        return None

    # The game's own refusal (a cooldown, say) — after the public gates, before
    # a single coin moves, so a refused player is never charged.
    if gate is not None:
        gate_msg = gate(guild.id, user.id)
        if gate_msg:
            await err(gate_msg)
            return None

    if bet is None:
        return GameStart(guild, user, None, reply, is_slash)

    amt = parse_wallet_amount(bet, guild.id, user.id)
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
            elif res.get("error") == "shareholder":
                # Backstop — the gate above should already have caught this.
                await err(casino_ban_message(guild.id, user.id)
                          or "You own a piece of the house.")
            else:
                await err("Bet failed. Try again.")
            return None

    return GameStart(guild, user, bet, reply, is_slash)


# ---- abandoned stakes --------------------------------------------------------

# How long a game holding a collected stake waits on a silent player before it
# hands the stake back. discord.py resets a view's timeout on every click, so
# this is idle time, not total game time.
STAKE_TIMEOUT = 5 * 60


def refund_stake(guild_id: int, user_id: int, bet: int) -> str:
    """Hand an abandoned game's stake back out of the house and return the
    line announcing it. A refund, not a win: refund_from_house bumps no
    winnings stats, and callers record no game for it."""
    refunded = refund_from_house(guild_id, user_id, bet)
    mins = STAKE_TIMEOUT // 60
    if refunded >= bet:
        return f"⏰ **Timed out** — no move in {mins} minutes. Your **{bet:,}** stake was refunded."
    return (f"⏰ **Timed out** — no move in {mins} minutes. Refunded **{refunded:,}** "
            f"of your **{bet:,}** stake — the house is tapped out.")


class StakeView(discord.ui.View):
    """A view sitting on a stake that's already in the house. If the player
    goes quiet for STAKE_TIMEOUT it settles the game instead of letting the
    view die with the coins in it — by default a full refund.

    Subclasses claim the game with `settle()` before paying anything (it
    returns False if a double-click or the timeout got there first), set
    `self.message` to the sent message so the timeout can edit it, and
    override `on_abandon()` when an idle game should cash out progress rather
    than refund. Views that track "over" on their game object override
    `is_settled()`."""

    def __init__(self, guild_id: int, user_id: int, bet: int, *,
                 timeout: float = STAKE_TIMEOUT):
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.user_id = user_id
        self.bet = bet
        self.settled = False
        self.message: discord.Message | None = None

    def is_settled(self) -> bool:
        return self.settled

    def settle(self) -> bool:
        if self.is_settled():
            return False
        self.settled = True
        return True

    async def on_abandon(self) -> str:
        """Settle an idle game; return the message's new content."""
        note = refund_stake(self.guild_id, self.user_id, self.bet)
        original = self.message.content if self.message else ""
        return f"{original}\n\n{note}" if original else note

    async def on_timeout(self):
        if not self.settle():
            return
        content = await self.on_abandon()
        for child in self.children:
            child.disabled = True
        if self.message is None:
            return
        try:
            await self.message.edit(content=content, view=self)
        except discord.HTTPException:
            pass
