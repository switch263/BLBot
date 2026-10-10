"""Kitty Plays the Bongo — a grid push-your-luck game, cousin to Bigfoot
(cogs/bigfoot.py, built on gridgame.GridView). A cat picks tiles on a 4x4
board. A running multiplier starts at x1 and every tile you flip MULTIPLIES
it; you cash out whenever. Two scared cats end the set (you lose everything).
One kitty tile ends the set with a jackpot.

Board (16 tiles): 2 scared cats (enders), 1 kitty, 3 bongos (x25 each),
4 hundreds (x100 each), 6 paw-taps (x1.5 each).

It pays WAY better than the woods — and it's strictly ONCE PER DAY per player.
The day is spent the moment a game actually begins (view built, message sent),
so a refused/broke attempt costs nobody their shot.
"""
import discord
from discord.ext import commands
from discord import app_commands
from fractions import Fraction
import random
import logging

import economy
from economy import get_coins, casino_payout, record_game
from amount import format_compact
from game_common import STAKE_TIMEOUT, casino_prelude, refund_stake, button_label
from gridgame import GridView

logger = logging.getLogger(__name__)

# 4x4 grid of bongo-skin tiles
GRID_ROWS = 4
GRID_COLS = 4
GRID_SIZE = GRID_ROWS * GRID_COLS  # 16

# Tile composition per game (must sum to <= GRID_SIZE):
NUM_ENDERS = 2    # scared cats — bust tiles, lose everything
NUM_KITTY = 1     # the star — ends the set with a jackpot
NUM_BONGO = 3     # x25 stacking multipliers
NUM_BIG = 4       # x100 stacking multipliers
NUM_SMALL = GRID_SIZE - NUM_ENDERS - NUM_KITTY - NUM_BONGO - NUM_BIG  # 6 paw-taps

# Multiplier each tile applies to the running total (multiplicative).
SMALL_MULT = Fraction(3, 2)   # 1.5x
BONGO_MULT = Fraction(25)     # 25x
BIG_MULT = Fraction(100)      # 100x
# Kitty ends the set: flat x1000 if it's your very first tap, else running x25.
KITTY_MULT = Fraction(25)
KITTY_FIRST_MULT = Fraction(1000)

# Once per calendar day.
KV_NAMESPACE = "bongo"
KV_LAST_DAY = "last_day"

BUST_NARRATIVES = [
    "A scared cat bolts across the kit and knocks the whole thing over. Set's done.",
    "The kitty hears the vacuum, freezes, and dropkicks the bongo into next week.",
    "You pet the wrong cat. It does not want to be a drummer. It never did.",
    "A cat that was absolutely not supposed to be here hisses and the beat dies.",
    "The cat gets the zoomies mid-fill and takes the whole rig with it.",
    "Red laser dot appears. Cat gone. Rhythm gone. You, broke.",
    "The cat stares at you, slowly pushes the bongo off the table, and leaves.",
]

KITTY_FIRST_NARRATIVES = [
    "FIRST TAP and you found the kitty herself — she lays down a thousand-fold solo nobody will believe.",
    "No warm-up, no rehearsal — your very first tap is THE cat, and the room detonates.",
    "One tap. The kitty. A x1000 miracle. Jazz historians are already arguing about it.",
]

KITTY_NARRATIVES = [
    "The kitty struts out, multiplies the whole set by 25, bows, and leaves on top.",
    "You found her. The kitty caps the run x25 and the crowd loses it.",
    "Grand finale: the kitty takes everything you've built and x25's it. Set closed.",
]

BONGO_NARRATIVES = [
    "A perfect bongo fill — x25 and the pocket deepens.",
    "The cat nails a solo. x25. Keep going or bank it.",
    "Bongo! x25. The groove is getting dangerous.",
]

BIG_NARRATIVES = [
    "💯 — a hundred-fold hit. The rig is smoking.",
    "x100. The cat is operating on another plane now.",
    "💯 clean. Your multiplier just ate a zero.",
]

PAW_FLAVOR = [
    "A clean paw-tap. x1.5 and the rhythm holds.",
    "Another tap, right on the one. x1.5.",
    "The cat finds the groove. x1.5.",
    "Tiny paws, big pocket. x1.5.",
]

CASHOUT_FLAVOR = [
    "The cat takes a bow and struts offstage with the winnings.",
    "You call the set before the zoomies hit. Smart.",
    "Kitty's had enough. Cash the groove in.",
    "You quit while the beat's still hot.",
]


def tile_mult(kind: str) -> Fraction:
    """The stacking multiplier a continue-tile applies to the running total."""
    return {"small": SMALL_MULT, "bongo": BONGO_MULT, "big": BIG_MULT}[kind]


def kitty_mult(running: Fraction, first_tile: bool) -> Fraction:
    """Final multiplier when the kitty is revealed (the set ends)."""
    return KITTY_FIRST_MULT if first_tile else running * KITTY_MULT


def _fmt_mult(m: Fraction) -> str:
    try:
        f = float(m)
    except OverflowError:
        return "huge"
    if f >= 100_000:
        return format_compact(int(m))
    return f"{f:,.2f}"


def _day_gate_refusal(last_day, today):
    """Pure predicate for the once-per-day gate. Returns a refusal string if
    the player already spent today's game, else None. Factored out of the cog
    so it's testable without economy or a Discord client."""
    if last_day == today:
        return ("🐱 The kitty's already played the bongos today. "
                "Come back tomorrow — even cats need to rest their paws.")
    return None


class BongoView(GridView):
    HIDDEN_LABEL = "🎵"

    def __init__(self, cog, guild_id: int, user_id: int, user_name: str, bet: int):
        super().__init__(user_id, rows=GRID_ROWS, cols=GRID_COLS, timeout=STAKE_TIMEOUT,
                         not_yours="Get your own cat.")
        self.cog = cog
        self.guild_id = guild_id
        self.user_name = user_name
        self.bet = bet
        # Randomly place every tile type.
        slots = list(range(GRID_SIZE))
        random.shuffle(slots)
        self.enders = set(slots[:NUM_ENDERS])
        self.kitty = slots[NUM_ENDERS]
        b0 = NUM_ENDERS + NUM_KITTY
        self.bongos = set(slots[b0:b0 + NUM_BONGO])
        g0 = b0 + NUM_BONGO
        self.bigs = set(slots[g0:g0 + NUM_BIG])
        # everything else is a small 1.5x paw-tap
        self.revealed: set[int] = set()
        self.mult = Fraction(1)
        self.reveals = 0
        self.action_btn.label = "Call the Set (1.00×)"
        self.action_btn.emoji = "🎤"

    def _kind(self, idx: int) -> str:
        if idx in self.enders:
            return "ender"
        if idx == self.kitty:
            return "kitty"
        if idx in self.bongos:
            return "bongo"
        if idx in self.bigs:
            return "big"
        return "small"

    # ---- GridView hooks ---------------------------------------------------
    def tile_face(self, idx: int):
        kind = self._kind(idx)
        faces = {"ender": "🙀", "kitty": "😻", "bongo": "🥁", "big": "💯", "small": "🐾"}
        if kind == "ender":
            return "🙀", discord.ButtonStyle.danger
        style = discord.ButtonStyle.success if idx in self.revealed else discord.ButtonStyle.secondary
        return faces[kind], style

    async def on_tile(self, interaction: discord.Interaction, idx: int):
        self.revealed.add(idx)
        self.tile_btns[idx].disabled = True
        kind = self._kind(idx)

        if kind == "ender":
            record_game(self.guild_id, self.user_id, "bongo", won=False)
            self.finish()
            content = self.cog._render(
                self, f"🙀 **DROPPED THE BEAT!** {random.choice(BUST_NARRATIVES)}\n"
                      f"You lose **{self.bet:,}** coins.")
            await interaction.response.edit_message(content=content, view=self)
            return

        if kind == "kitty":
            first = len(self.revealed) == 1
            final = kitty_mult(self.mult, first)
            requested = int(self.bet * final)
            paid = casino_payout(self.guild_id, self.user_id, requested)
            record_game(self.guild_id, self.user_id, "bongo", won=True)
            self.finish()
            net = paid - self.bet
            short = f" *(house was short — owed {requested:,})*" if paid < requested else ""
            if first:
                headline = "😻 **FIRST-TAP KITTY!** " + random.choice(KITTY_FIRST_NARRATIVES)
            else:
                headline = "😻 **THE KITTY!** " + random.choice(KITTY_NARRATIVES)
            content = self.cog._render(
                self, f"{headline}\nFinal multiplier **{_fmt_mult(final)}×** → net **{net:+,}** coins.{short}")
            await interaction.response.edit_message(content=content, view=self)
            return

        # Stacking continue-tile (small / bongo / big)
        self.mult *= tile_mult(kind)
        self.reveals += 1
        face = {"bongo": "🥁", "big": "💯", "small": "🐾"}[kind]
        self.tile_btns[idx].label = face
        self.tile_btns[idx].style = discord.ButtonStyle.success
        flavor = {"bongo": BONGO_NARRATIVES, "big": BIG_NARRATIVES, "small": PAW_FLAVOR}[kind]
        self._refresh_cashout()
        await interaction.response.edit_message(
            content=self.cog._render(self, random.choice(flavor)), view=self)

    async def on_action(self, interaction: discord.Interaction):
        if self.reveals == 0:
            await interaction.response.send_message(
                "The cat hasn't touched the drum yet.", ephemeral=True)
            return
        requested = int(self.bet * self.mult)
        paid = casino_payout(self.guild_id, self.user_id, requested)
        record_game(self.guild_id, self.user_id, "bongo", won=True)
        self.finish()
        net = paid - self.bet
        short = f" *(house was short — owed {requested:,})*" if paid < requested else ""
        content = self.cog._render(
            self,
            f"🎤 **Called the set after {self.reveals} tiles.** {random.choice(CASHOUT_FLAVOR)}\n"
            f"Multiplier **{_fmt_mult(self.mult)}×** → net **{net:+,}** coins.{short}",
        )
        await interaction.response.edit_message(content=content, view=self)

    async def on_abandon(self):
        # Walked away mid-set: bank whatever stacked, or refund if nothing did.
        if self.reveals > 0:
            requested = int(self.bet * self.mult)
            paid = casino_payout(self.guild_id, self.user_id, requested)
            record_game(self.guild_id, self.user_id, "bongo", won=True)
            short = f" *(house was short — owed {requested:,})*" if paid < requested else ""
            footer = (f"⏰ **Auto-called the set** at **{_fmt_mult(self.mult)}×** — you went quiet. "
                      f"Net **{paid - self.bet:+,}** coins.{short}")
        else:
            footer = refund_stake(self.guild_id, self.user_id, self.bet)
        self.finish()
        if self.message is None:
            return
        try:
            await self.message.edit(content=self.cog._render(self, footer), view=self)
        except discord.HTTPException:
            pass

    def _refresh_cashout(self):
        net = int(self.bet * self.mult) - self.bet
        self.action_btn.label = button_label(f"Call the Set ({_fmt_mult(self.mult)}×, +{format_compact(net)})")


class BongoKitty(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Kitty Plays the Bongo loaded.")

    def _day_gate(self, guild_id: int, user_id: int):
        last_day = economy.kv_get(guild_id, user_id, KV_NAMESPACE, KV_LAST_DAY)
        return _day_gate_refusal(last_day, economy.today_str())

    def _render(self, v: BongoView, footer: str | None = None) -> str:
        lines = [
            f"🥁 **{v.user_name}'s Bongo Solo** — bet **{v.bet:,}** coins",
            f"**{NUM_SMALL}×🐾 (×1.5)**, **{NUM_BIG}×💯 (×100)**, **{NUM_BONGO}×🥁 (×25)**, "
            f"**1×😻 kitty**, **{NUM_ENDERS}×🙀 enders** across **{GRID_SIZE}** tiles.",
            f"Tiles flipped: **{v.reveals}** | Running multiplier: **{_fmt_mult(v.mult)}×**",
        ]
        if not v.resolved:
            lines.append(
                "Every tile MULTIPLIES your total — cash out any time. A 🙀 ends it all. "
                "The 😻 kitty closes the set at **×25** (or a flat **×1000** if it's your first tap). Once a day."
            )
        if footer:
            lines.append("")
            lines.append(footer)
            lines.append(f"Balance: **{get_coins(v.guild_id, v.user_id):,}**")
        return "\n".join(lines)

    async def _start(self, ctx_or_interaction, bet):
        start = await casino_prelude(
            ctx_or_interaction, bet,
            zero_msg="The cat doesn't play for free. Bet something.",
            no_guild_msg="The kitty only drums in a server.",
            gate=self._day_gate,
        )
        if start is None:
            return
        view = BongoView(self, start.guild.id, start.user.id,
                         start.user.display_name, start.bet)
        view.message = await start.reply(self._render(view), view=view)
        # A game actually began — spend today's shot. (After the message so a
        # failed send doesn't silently burn the day.)
        economy.kv_set(start.guild.id, start.user.id, KV_NAMESPACE, KV_LAST_DAY,
                       economy.today_str())

    @commands.command(name="bongo", aliases=["kitty", "bongos"])
    @commands.guild_only()
    async def bongo_prefix(self, ctx, bet: str):
        await self._start(ctx, bet)

    @app_commands.command(name="bongo", description="Let the kitty play the bongos. Pays big — once a day.")
    @app_commands.describe(bet="Coins to risk on the solo — supports 1k, 5m, all, half, 50%")
    async def bongo_slash(self, interaction: discord.Interaction, bet: str):
        await self._start(interaction, bet)


async def setup(bot):
    await bot.add_cog(BongoKitty(bot))
