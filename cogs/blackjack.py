import discord
from discord.ext import commands
from discord import app_commands
import random
import sys
import os
import logging
import asyncio
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from economy import get_coins, add_coins, deduct_coins

logger = logging.getLogger(__name__)

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]

LOBBY_SECONDS = 60
MAX_PLAYERS = 8
TURN_VIEW_TIMEOUT = 600  # 10 minutes for the whole play phase


def new_deck(num_decks: int = 1):
    deck = [(r, s) for _ in range(num_decks) for r in RANKS for s in SUITS]
    random.shuffle(deck)
    return deck


def card_value(rank: str) -> int:
    if rank in ("J", "Q", "K"):
        return 10
    if rank == "A":
        return 11
    return int(rank)


def hand_total(hand) -> int:
    total = sum(card_value(r) for r, _ in hand)
    aces = sum(1 for r, _ in hand if r == "A")
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


def is_blackjack(hand) -> bool:
    return len(hand) == 2 and hand_total(hand) == 21


def format_card(card) -> str:
    rank, suit = card
    return f"`{rank}{suit}`"


def format_hand(hand) -> str:
    return " ".join(format_card(c) for c in hand)


class PlayerState:
    def __init__(self, user_id: int, user_name: str, bet: int):
        self.user_id = user_id
        self.user_name = user_name
        self.bet = bet
        self.hands: list[list] = []
        self.hand_bets: list[int] = []
        self.current_hand_idx = 0
        self.done = False
        self.revealed = False
        self.result_text: str | None = None
        self.payout = 0  # coins added at settlement

    @property
    def current_hand(self):
        return self.hands[self.current_hand_idx]

    def can_split(self, balance: int) -> bool:
        if len(self.hands) > 1:
            return False
        h = self.current_hand
        if len(h) != 2:
            return False
        if card_value(h[0][0]) != card_value(h[1][0]):
            return False
        return balance >= self.bet

    def can_double(self, balance: int) -> bool:
        return len(self.current_hand) == 2 and balance >= self.hand_bets[self.current_hand_idx]


class Round:
    LOBBY = "lobby"
    PLAYING = "playing"
    DONE = "done"

    def __init__(self, guild_id: int, channel_id: int, host_id: int, buy_in: int):
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.host_id = host_id
        self.buy_in = buy_in
        self.players: list[PlayerState] = []
        self.deck: list | None = None
        self.dealer_hand: list = []
        self.current_player_idx = 0
        self.phase = Round.LOBBY
        self.lobby_deadline = 0.0
        self.message: discord.Message | None = None
        self.timer_task: asyncio.Task | None = None

    @property
    def current_player(self) -> PlayerState:
        return self.players[self.current_player_idx]

    def find_player(self, user_id: int) -> PlayerState | None:
        for p in self.players:
            if p.user_id == user_id:
                return p
        return None

    def deal(self):
        self.deck = new_deck(num_decks=max(2, len(self.players)))
        for p in self.players:
            p.hands = [[self.deck.pop(), self.deck.pop()]]
            p.hand_bets = [p.bet]
            p.current_hand_idx = 0
            p.done = False
        self.dealer_hand = [self.deck.pop(), self.deck.pop()]
        self.phase = Round.PLAYING

    def dealer_play(self):
        while hand_total(self.dealer_hand) < 17:
            self.dealer_hand.append(self.deck.pop())

    def advance_to_next_active_player(self) -> bool:
        """Advance current_player_idx to next not-done player. Returns True if found."""
        idx = self.current_player_idx + 1
        while idx < len(self.players):
            if not self.players[idx].done:
                self.current_player_idx = idx
                return True
            idx += 1
        return False

    def first_active_player(self) -> bool:
        for i, p in enumerate(self.players):
            if not p.done:
                self.current_player_idx = i
                return True
        return False


class LobbyView(discord.ui.View):
    def __init__(self, cog, round: Round):
        super().__init__(timeout=LOBBY_SECONDS + 10)
        self.cog = cog
        self.round = round

    @discord.ui.button(label="Join", style=discord.ButtonStyle.success, emoji="💰")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        r = self.round
        if r.phase != Round.LOBBY:
            await interaction.response.send_message("Round already started.", ephemeral=True)
            return
        if r.find_player(interaction.user.id):
            await interaction.response.send_message("You're already in.", ephemeral=True)
            return
        if len(r.players) >= MAX_PLAYERS:
            await interaction.response.send_message(f"Table's full ({MAX_PLAYERS} players).", ephemeral=True)
            return
        balance = get_coins(r.guild_id, interaction.user.id)
        if balance < r.buy_in:
            await interaction.response.send_message(
                f"Too broke for the buy-in of **{r.buy_in}**. Balance: **{balance}**", ephemeral=True)
            return
        deduct_coins(r.guild_id, interaction.user.id, r.buy_in)
        r.players.append(PlayerState(interaction.user.id, interaction.user.display_name, r.buy_in))
        await interaction.response.edit_message(content=self.cog._render_lobby(r), view=self)

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.secondary, emoji="🚪")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        r = self.round
        if r.phase != Round.LOBBY:
            await interaction.response.send_message("Round already started — you can't bail now.", ephemeral=True)
            return
        p = r.find_player(interaction.user.id)
        if not p:
            await interaction.response.send_message("You're not in this round.", ephemeral=True)
            return
        add_coins(r.guild_id, p.user_id, p.bet)
        r.players.remove(p)
        if interaction.user.id == r.host_id and r.players:
            r.host_id = r.players[0].user_id
        await interaction.response.edit_message(content=self.cog._render_lobby(r), view=self)

    @discord.ui.button(label="Deal Now", style=discord.ButtonStyle.primary, emoji="🃏")
    async def deal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        r = self.round
        if interaction.user.id != r.host_id:
            await interaction.response.send_message("Only the host can deal early.", ephemeral=True)
            return
        if r.phase != Round.LOBBY:
            await interaction.response.send_message("Round already started.", ephemeral=True)
            return
        if not r.players:
            await interaction.response.send_message("Nobody's bought in yet.", ephemeral=True)
            return
        await interaction.response.defer()
        if r.timer_task:
            r.timer_task.cancel()
        await self.cog._start_playing(r)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        r = self.round
        if interaction.user.id != r.host_id:
            await interaction.response.send_message("Only the host can cancel.", ephemeral=True)
            return
        if r.phase != Round.LOBBY:
            await interaction.response.send_message("Round already started.", ephemeral=True)
            return
        for p in r.players:
            add_coins(r.guild_id, p.user_id, p.bet)
        r.phase = Round.DONE
        if r.timer_task:
            r.timer_task.cancel()
        self.cog.rounds.pop(r.channel_id, None)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content="🛑 Blackjack round cancelled. Buy-ins refunded.",
            view=self,
        )


class PlayingView(discord.ui.View):
    def __init__(self, cog, round: Round):
        super().__init__(timeout=TURN_VIEW_TIMEOUT)
        self.cog = cog
        self.round = round
        self._refresh_buttons()

    def _refresh_buttons(self):
        r = self.round
        if r.phase != Round.PLAYING:
            for item in self.children:
                item.disabled = True
            return
        p = r.current_player
        balance = get_coins(r.guild_id, p.user_id)
        self.split_button.disabled = not p.can_split(balance)
        self.double_button.disabled = not p.can_double(balance)

    async def _not_your_turn(self, interaction: discord.Interaction) -> bool:
        r = self.round
        if r.phase != Round.PLAYING:
            await interaction.response.send_message("Round isn't active.", ephemeral=True)
            return True
        if interaction.user.id != r.current_player.user_id:
            await interaction.response.send_message(
                f"Not your turn — it's **{r.current_player.user_name}**'s turn.", ephemeral=True)
            return True
        return False

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary, emoji="🃏", row=0)
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._not_your_turn(interaction):
            return
        r = self.round
        p = r.current_player
        p.current_hand.append(r.deck.pop())
        await self.cog._after_action(interaction, self, auto_advance=hand_total(p.current_hand) >= 21)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary, emoji="✋", row=0)
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._not_your_turn(interaction):
            return
        await self.cog._after_action(interaction, self, auto_advance=True)

    @discord.ui.button(label="Double", style=discord.ButtonStyle.success, emoji="💸", row=0)
    async def double_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._not_your_turn(interaction):
            return
        r = self.round
        p = r.current_player
        bet = p.hand_bets[p.current_hand_idx]
        if get_coins(r.guild_id, p.user_id) < bet:
            await interaction.response.send_message(
                f"Can't double — not enough coins for **{bet}**.", ephemeral=True)
            return
        deduct_coins(r.guild_id, p.user_id, bet)
        p.hand_bets[p.current_hand_idx] *= 2
        p.current_hand.append(r.deck.pop())
        await self.cog._after_action(interaction, self, auto_advance=True)

    @discord.ui.button(label="Split", style=discord.ButtonStyle.success, emoji="✂️", row=0)
    async def split_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._not_your_turn(interaction):
            return
        r = self.round
        p = r.current_player
        if get_coins(r.guild_id, p.user_id) < p.bet:
            await interaction.response.send_message(
                f"Can't split — not enough coins for **{p.bet}**.", ephemeral=True)
            return
        deduct_coins(r.guild_id, p.user_id, p.bet)
        h = p.current_hand
        second_card = h.pop()
        h.append(r.deck.pop())
        second_hand = [second_card, r.deck.pop()]
        p.hands.append(second_hand)
        p.hand_bets.append(p.bet)
        await self.cog._after_action(interaction, self, auto_advance=hand_total(p.current_hand) >= 21)

    @discord.ui.button(label="Peek", style=discord.ButtonStyle.secondary, emoji="🔒", row=1)
    async def peek_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        r = self.round
        p = r.find_player(interaction.user.id)
        if not p:
            await interaction.response.send_message("You're not in this round.", ephemeral=True)
            return
        await interaction.response.send_message(
            self.cog._render_private(r, p), ephemeral=True)

    async def on_timeout(self):
        r = self.round
        if r.phase != Round.PLAYING:
            return
        # auto-stand whoever is up, finish round
        for p in r.players:
            p.done = True
        await self.cog._finish_round(r)


class Blackjack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.rounds: dict[int, Round] = {}  # channel_id -> Round

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Blackjack module has been loaded")

    # -------- Rendering --------

    def _render_lobby(self, r: Round) -> str:
        lines = [
            f"🃏 **Blackjack Round** — buy-in **{r.buy_in}** coins",
            f"Deal starts <t:{int(r.lobby_deadline)}:R>. Max {MAX_PLAYERS} players.",
        ]
        if r.players:
            player_lines = []
            for p in r.players:
                crown = " 👑" if p.user_id == r.host_id else ""
                player_lines.append(f"• {p.user_name}{crown}")
            lines.append("**Seated:**\n" + "\n".join(player_lines))
        else:
            lines.append("_No players yet._")
        lines.append("Click **Join** to buy in. Host can **Deal Now** or **Cancel**.")
        return "\n".join(lines)

    def _render_playing(self, r: Round, reveal_dealer: bool = False, header_note: str | None = None) -> str:
        lines = [f"🃏 **Blackjack** — buy-in **{r.buy_in}**"]
        if reveal_dealer:
            lines.append(f"**Dealer:** {format_hand(r.dealer_hand)} — total **{hand_total(r.dealer_hand)}**"
                         + (" **BUST**" if hand_total(r.dealer_hand) > 21 else ""))
        else:
            up = r.dealer_hand[0]
            lines.append(f"**Dealer shows:** {format_card(up)} `??` — showing **{card_value(up[0])}**")

        lines.append("")
        for i, p in enumerate(r.players):
            turn_marker = ""
            if r.phase == Round.PLAYING and i == r.current_player_idx and not p.done:
                turn_marker = " 👉"
            if len(p.hands) == 1:
                h = p.hands[0]
                total = hand_total(h)
                tag = ""
                if total > 21:
                    tag = " **BUST**"
                elif is_blackjack(h):
                    tag = " **BLACKJACK**"
                cards = format_hand(h) if p.revealed else f"{len(h)} cards"
                status = p.result_text if r.phase == Round.DONE and p.result_text else ""
                lines.append(f"**{p.user_name}**{turn_marker}: {cards} — total **{total}**{tag} _(bet {p.hand_bets[0]})_ {status}")
            else:
                lines.append(f"**{p.user_name}**{turn_marker}:")
                for hi, h in enumerate(p.hands):
                    hand_marker = ""
                    if r.phase == Round.PLAYING and i == r.current_player_idx and hi == p.current_hand_idx and not p.done:
                        hand_marker = " 👉"
                    total = hand_total(h)
                    tag = ""
                    if total > 21:
                        tag = " **BUST**"
                    elif is_blackjack(h):
                        tag = " **BLACKJACK**"
                    cards = format_hand(h) if p.revealed else f"{len(h)} cards"
                    lines.append(f"  Hand {hi+1}{hand_marker}: {cards} — total **{total}**{tag} _(bet {p.hand_bets[hi]})_")
                if r.phase == Round.DONE and p.result_text:
                    lines.append(f"  _{p.result_text}_")

        if header_note:
            lines.append("")
            lines.append(header_note)
        return "\n".join(lines)

    def _render_private(self, r: Round, p: PlayerState) -> str:
        lines = [f"🔒 **Your hand** (only you see this)"]
        for i, h in enumerate(p.hands):
            prefix = f"Hand {i+1}: " if len(p.hands) > 1 else ""
            marker = ""
            if r.phase == Round.PLAYING and r.current_player.user_id == p.user_id and i == p.current_hand_idx and not p.done:
                marker = " 👉"
            lines.append(f"{prefix}{format_hand(h)} — total **{hand_total(h)}**{marker}")
        return "\n".join(lines)

    # -------- Flow --------

    async def _start_round(self, ctx_or_interaction, bet: int):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild
        channel = ctx_or_interaction.channel
        user = ctx_or_interaction.user if is_slash else ctx_or_interaction.author

        async def reply(content, **kwargs):
            if is_slash:
                await ctx_or_interaction.response.send_message(content, **kwargs)
                return await ctx_or_interaction.original_response()
            return await ctx_or_interaction.send(content, **kwargs)

        if not guild:
            await reply("Can only play in a server.")
            return
        if bet <= 0:
            await reply("Buy-in needs to be greater than 0.")
            return
        if channel.id in self.rounds:
            await reply("A blackjack round is already running in this channel.")
            return
        balance = get_coins(guild.id, user.id)
        if balance < bet:
            await reply(f"You're too broke for the buy-in. Balance: **{balance}**")
            return

        deduct_coins(guild.id, user.id, bet)
        r = Round(guild.id, channel.id, user.id, bet)
        r.players.append(PlayerState(user.id, user.display_name, bet))
        r.lobby_deadline = time.time() + LOBBY_SECONDS
        self.rounds[channel.id] = r

        view = LobbyView(self, r)
        msg = await reply(self._render_lobby(r), view=view)
        r.message = msg
        r.timer_task = asyncio.create_task(self._lobby_timer(r))

    async def _lobby_timer(self, r: Round):
        try:
            delay = r.lobby_deadline - time.time()
            if delay > 0:
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        if r.phase == Round.LOBBY:
            await self._start_playing(r)

    async def _start_playing(self, r: Round):
        if not r.players:
            r.phase = Round.DONE
            self.rounds.pop(r.channel_id, None)
            if r.message:
                try:
                    await r.message.edit(content="🛑 Blackjack round cancelled — no players.", view=None)
                except discord.HTTPException:
                    pass
            return

        r.deal()

        for p in r.players:
            try:
                user = self.bot.get_user(p.user_id) or await self.bot.fetch_user(p.user_id)
                await user.send(self._render_private(r, p))
            except (discord.Forbidden, discord.HTTPException):
                pass

        dealer_bj = is_blackjack(r.dealer_hand)
        for p in r.players:
            if is_blackjack(p.hands[0]):
                p.done = True

        if dealer_bj:
            await self._finish_round(r)
            return

        if not r.first_active_player():
            await self._finish_round(r)
            return

        view = PlayingView(self, r)
        try:
            await r.message.edit(content=self._render_playing(r), view=view)
        except discord.HTTPException as e:
            logger.error(f"Failed to edit blackjack round message: {e}")

    async def _after_action(self, interaction: discord.Interaction, view: PlayingView, auto_advance: bool):
        r = view.round
        p = r.current_player
        p.revealed = True

        if auto_advance:
            if p.current_hand_idx < len(p.hands) - 1:
                p.current_hand_idx += 1
                # auto-advance through 21 hands too
                while p.current_hand_idx < len(p.hands) - 1 and hand_total(p.current_hand) >= 21:
                    p.current_hand_idx += 1
                if hand_total(p.current_hand) >= 21:
                    p.done = True
            else:
                p.done = True

        if p.done:
            if not r.advance_to_next_active_player():
                view._refresh_buttons()
                for item in view.children:
                    item.disabled = True
                await interaction.response.edit_message(content=self._render_playing(r), view=view)
                await self._finish_round(r, interaction=interaction)
                return

        view._refresh_buttons()
        await interaction.response.edit_message(content=self._render_playing(r), view=view)
        # Private update for whoever's turn it is now
        next_p = r.current_player
        if next_p.user_id == interaction.user.id:
            await interaction.followup.send(self._render_private(r, next_p), ephemeral=True)

    async def _finish_round(self, r: Round, interaction: discord.Interaction | None = None):
        r.phase = Round.DONE
        for p in r.players:
            p.revealed = True

        if any(any(hand_total(h) <= 21 for h in p.hands) for p in r.players):
            r.dealer_play()

        dealer_total = hand_total(r.dealer_hand)
        dealer_bust = dealer_total > 21
        dealer_bj = is_blackjack(r.dealer_hand)

        for p in r.players:
            results = []
            payout = 0
            for i, h in enumerate(p.hands):
                ptotal = hand_total(h)
                bet = p.hand_bets[i]
                if is_blackjack(h) and len(p.hands) == 1 and not dealer_bj:
                    # natural blackjack — 3:2
                    pay = int(bet * 2.5)
                    payout += pay
                    results.append(f"🎉 blackjack ({ptotal}) → +{pay - bet}")
                elif dealer_bj and not is_blackjack(h):
                    results.append(f"💀 dealer blackjack — lose {bet}")
                elif dealer_bj and is_blackjack(h):
                    payout += bet
                    results.append(f"🤝 push — dealer blackjack")
                elif ptotal > 21:
                    results.append(f"💀 bust ({ptotal}) — lose {bet}")
                elif dealer_bust or ptotal > dealer_total:
                    pay = bet * 2
                    payout += pay
                    dsuffix = "dealer busts" if dealer_bust else f"beats dealer {dealer_total}"
                    results.append(f"🎉 win ({ptotal}, {dsuffix}) → +{bet}")
                elif ptotal == dealer_total:
                    payout += bet
                    results.append(f"🤝 push ({ptotal})")
                else:
                    results.append(f"💀 lose ({ptotal} vs {dealer_total}) — lose {bet}")
            p.payout = payout
            if payout:
                add_coins(r.guild_id, p.user_id, payout)
            p.result_text = " | ".join(results)

        content = self._render_playing(r, reveal_dealer=True, header_note="**Round complete!**")
        try:
            if interaction is not None and not interaction.response.is_done():
                await interaction.response.edit_message(content=content, view=None)
            elif r.message:
                await r.message.edit(content=content, view=None)
        except discord.HTTPException as e:
            logger.error(f"Failed to finalize blackjack message: {e}")

        self.rounds.pop(r.channel_id, None)

    # -------- Commands --------

    @commands.command(name="blackjack", aliases=["bj"])
    @commands.guild_only()
    async def blackjack_prefix(self, ctx, bet: int):
        await self._start_round(ctx, bet)

    @app_commands.command(name="blackjack", description="Start a multi-player blackjack round with a buy-in")
    @app_commands.describe(bet="Buy-in amount every player must match to join this round")
    async def blackjack_slash(self, interaction: discord.Interaction, bet: int):
        await self._start_round(interaction, bet)


async def setup(bot):
    await bot.add_cog(Blackjack(bot))
