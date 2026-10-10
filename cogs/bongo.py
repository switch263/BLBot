"""Kitty Plays the Bongo — a grid push-your-luck game, cousin to Bigfoot
(cogs/bigfoot.py, built on gridgame.GridView). A cat picks tiles on a 4x4
board: most are safe paw-taps that bump the multiplier, two are scared cats
that drop the beat (bust), and one is a perfect bongo solo (jackpot).

It pays WAY better than the woods — and it's strictly ONCE PER DAY per player.
The day is spent the moment a game actually begins (view built, message sent),
so a refused/broke attempt costs nobody their shot.
"""
import discord
from discord.ext import commands
from discord import app_commands
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

# Tile composition per game:
NUM_BUST_CATS = 2    # scared cats — bust tiles (dropped the beat)
NUM_BONGO = 1        # perfect-solo tile — auto-wins on reveal
# remaining 13 are paw-taps that bump the multiplier
SAFE_BUMP = 1.0      # +100% of bet per clean paw-tap
BONGO_MULT = 25.0    # whole-bet multiplier for a perfect solo
# Nailing the solo on your very first tap (1-in-16 per game) skips the paw
# math entirely and pays this flat.
FIRST_SHOT_MULT = 250.0

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

FIRST_SHOT_NARRATIVES = [
    "First tap. The cat's paw hits the skin and out comes a flawless solo nobody taught it. Stadiums will hear of this.",
    "No warm-up, no rehearsal — one paw, one note, and the room goes silent before it goes insane.",
    "The kitty cracks its tiny knuckles and lays down a first-tap solo so clean the metronome apologizes.",
]

BONGO_NARRATIVES = [
    "The cat finds the pocket and does NOT leave it. A perfect solo. The crowd is weeping.",
    "Paws blur. The bongo sings. Somewhere a jazz legend tips their hat.",
    "A flawless fill, a cymbal of pure meow, and the set ends in a standing ovation.",
    "The kitty nails the solo, blinks slowly at you, and demands royalties. Worth it.",
    "Studio-clean, impossibly tight — the cat just reinvented percussion. You're rich.",
]

PAW_FLAVOR = [
    "A clean paw-tap. The rhythm holds.",
    "Another tap, right on the one.",
    "The cat finds the groove. Nice.",
    "Tiny paws, big pocket. Keep going.",
    "A confident little *bop*. Crowd nods.",
    "The kitty tilts an ear and taps again.",
    "Steady as a kitten. The beat deepens.",
    "That one slapped. Literally.",
]

CASHOUT_FLAVOR = [
    "The cat takes a bow and struts offstage with the winnings.",
    "You call the set before the zoomies hit. Smart.",
    "Kitty's had enough. Cash the groove in.",
    "A wise raccoon in the front row signals to bank. You listen.",
    "You quit while the beat's still hot.",
]


def current_multiplier(paws: int) -> float:
    return 1.0 + SAFE_BUMP * paws


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
        # Randomly place scared cats and 1 bongo solo
        slots = list(range(GRID_SIZE))
        random.shuffle(slots)
        self.bust_cats = set(slots[:NUM_BUST_CATS])
        self.bongo = slots[NUM_BUST_CATS]
        self.revealed: set[int] = set()
        self.paws_found = 0
        self.action_btn.label = "Call the Set (1.00×)"
        self.action_btn.emoji = "🎤"

    # ---- GridView hooks ---------------------------------------------------
    def tile_face(self, idx: int):
        if idx in self.bust_cats:
            return "🙀", discord.ButtonStyle.danger
        if idx == self.bongo:
            return "🥁", (discord.ButtonStyle.success if idx in self.revealed
                          else discord.ButtonStyle.secondary)
        if idx in self.revealed:
            return "🐾", discord.ButtonStyle.success
        return None

    async def on_tile(self, interaction: discord.Interaction, idx: int):
        self.revealed.add(idx)
        self.tile_btns[idx].disabled = True

        if idx in self.bust_cats:
            record_game(self.guild_id, self.user_id, "bongo", won=False)
            self.finish()
            narrative = random.choice(BUST_NARRATIVES)
            content = self.cog._render(
                self, f"🙀 **DROPPED THE BEAT!** {narrative}\nYou lose **{self.bet:,}** coins.")
            await interaction.response.edit_message(content=content, view=self)
            return

        if idx == self.bongo:
            first_shot = len(self.revealed) == 1
            if first_shot:
                # Perfect solo on the very first tap: flat FIRST_SHOT_MULT jackpot.
                final_mult = FIRST_SHOT_MULT
                headline = "🥁 **FIRST-TAP SOLO!** " + random.choice(FIRST_SHOT_NARRATIVES)
                breakdown = f"Final multiplier: **{final_mult:.0f}×** — first-tap jackpot, no warm-up needed."
            else:
                base_mult = current_multiplier(self.paws_found)
                final_mult = base_mult * BONGO_MULT
                headline = f"🥁 **PERFECT BONGO SOLO!** {random.choice(BONGO_NARRATIVES)}"
                breakdown = (f"Final multiplier: **{final_mult:.2f}×** "
                             f"({base_mult:.2f}× paws × {BONGO_MULT:.0f}× solo).")
            requested = int(self.bet * final_mult)
            paid = casino_payout(self.guild_id, self.user_id, requested)
            record_game(self.guild_id, self.user_id, "bongo", won=True)
            self.finish()
            net = paid - self.bet
            short = f" *(house was short — owed {requested:,})*" if paid < requested else ""
            content = self.cog._render(
                self, f"{headline}\n{breakdown} Net **{net:+,}** coins.{short}")
            await interaction.response.edit_message(content=content, view=self)
            return

        # Paw-tap (safe)
        self.paws_found += 1
        self.tile_btns[idx].label = "🐾"
        self.tile_btns[idx].style = discord.ButtonStyle.success
        self._refresh_cashout()
        await interaction.response.edit_message(content=self.cog._render(self), view=self)

    async def on_action(self, interaction: discord.Interaction):
        if self.paws_found == 0:
            await interaction.response.send_message(
                "The cat hasn't touched the drum yet.", ephemeral=True)
            return
        mult = current_multiplier(self.paws_found)
        requested = int(self.bet * mult)
        paid = casino_payout(self.guild_id, self.user_id, requested)
        record_game(self.guild_id, self.user_id, "bongo", won=True)
        self.finish()
        net = paid - self.bet
        short = f" *(house was short — owed {requested:,})*" if paid < requested else ""
        narrative = random.choice(CASHOUT_FLAVOR)
        content = self.cog._render(
            self,
            f"🎤 **Called the set after {self.paws_found} clean taps.** {narrative}\n"
            f"Multiplier **{mult:.2f}×** → net **{net:+,}** coins.{short}",
        )
        await interaction.response.edit_message(content=content, view=self)

    async def on_abandon(self):
        # Walked away mid-set: bank whatever taps landed, or refund the stake
        # if the cat never touched the drum.
        if self.paws_found > 0:
            mult = current_multiplier(self.paws_found)
            requested = int(self.bet * mult)
            paid = casino_payout(self.guild_id, self.user_id, requested)
            record_game(self.guild_id, self.user_id, "bongo", won=True)
            short = f" *(house was short — owed {requested:,})*" if paid < requested else ""
            footer = f"⏰ **Auto-called the set** at **{mult:.2f}×** — you went quiet. Net **{paid - self.bet:+,}** coins.{short}"
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
        mult = current_multiplier(self.paws_found)
        net = int(self.bet * mult) - self.bet
        self.action_btn.label = button_label(f"Call the Set ({mult:.2f}×, +{format_compact(net)})")


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
        mult = current_multiplier(v.paws_found)
        lines = [
            f"🥁 **{v.user_name}'s Bongo Solo** — bet **{v.bet:,}** coins",
            f"Somewhere in these **{GRID_SIZE}** tiles: **{NUM_BUST_CATS} scared cats** and **1 perfect solo** (jackpot ×{BONGO_MULT:.0f}).",
            f"Clean taps: **{v.paws_found}** | Multiplier: **{mult:.2f}×**",
        ]
        if not v.resolved:
            lines.append(
                f"Each clean paw-tap bumps the multiplier. Hit the 🥁 and the multiplier is ×{BONGO_MULT:.0f} — "
                f"or a flat **×{FIRST_SHOT_MULT:.0f}** if it's your very first tap. Once a day, so make it count."
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
