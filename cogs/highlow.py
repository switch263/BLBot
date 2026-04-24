import discord
from discord.ext import commands
from discord import app_commands
import random
import sys
import os
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from economy import get_coins, add_coins, deduct_coins, jail_message

logger = logging.getLogger(__name__)

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]  # 1-13

HOUSE_EDGE = 0.92  # 8% house edge applied to fair multiplier per correct pick


def rank_value(idx: int) -> int:
    """idx 0..12 maps to ranks A..K, value 1..13"""
    return idx + 1


def rank_label(idx: int) -> str:
    return RANKS[idx]


def random_card() -> tuple[int, str]:
    return random.randint(0, 12), random.choice(SUITS)


def suit_wrap(rank_idx: int, suit: str) -> str:
    label = rank_label(rank_idx)
    color = "diamond" if suit in ("♥", "♦") else "spade"
    return f"`{label}{suit}`"


def gain_factor(current_idx: int, guessed_higher: bool) -> float:
    """Fair multiplier gain for correctly predicting a strict higher/lower draw. Ties don't count."""
    cur_val = rank_value(current_idx)
    if guessed_higher:
        correct = 13 - cur_val  # cards strictly higher
    else:
        correct = cur_val - 1   # cards strictly lower
    if correct <= 0:
        return 1.0  # impossible guess; protective default
    # Fair mult = 13/correct. Apply house edge.
    return HOUSE_EDGE * 13 / correct


class HighLowGame:
    def __init__(self, guild_id, user_id, user_name, bet):
        self.guild_id = guild_id
        self.user_id = user_id
        self.user_name = user_name
        self.bet = bet
        self.current_rank_idx, self.current_suit = random_card()
        self.streak = 0
        self.multiplier = 1.0
        self.log: list[str] = []
        self.ended = False


class HigherButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.success, label="HIGHER", emoji="⬆️", row=0)

    async def callback(self, interaction: discord.Interaction):
        await self.view.cog._resolve(interaction, self.view, True)


class LowerButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="LOWER", emoji="⬇️", row=0)

    async def callback(self, interaction: discord.Interaction):
        await self.view.cog._resolve(interaction, self.view, False)


class CashOutButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="Cash Out (1.00×)", emoji="💰", row=0)

    async def callback(self, interaction: discord.Interaction):
        view: "HighLowView" = self.view  # type: ignore
        g = view.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message("Not your game.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return
        if g.streak == 0:
            await interaction.response.send_message("No streak yet — make at least one correct call first.", ephemeral=True)
            return
        g.ended = True
        payout = int(g.bet * g.multiplier)
        add_coins(g.guild_id, g.user_id, payout)
        net = payout - g.bet
        for child in view.children:
            child.disabled = True
        footer = (
            f"💰 **Cashed out** at **{g.multiplier:.2f}×** — **{payout}** coins "
            f"(net **+{net}**). Streak: **{g.streak}**.\n"
            f"Balance: **{get_coins(g.guild_id, g.user_id)}**"
        )
        await interaction.response.edit_message(content=view.cog._render(g, footer), view=view)


class HighLowView(discord.ui.View):
    def __init__(self, cog, game: HighLowGame):
        super().__init__(timeout=180)
        self.cog = cog
        self.game = game
        self.add_item(HigherButton())
        self.add_item(LowerButton())
        self.cashout = CashOutButton()
        self.add_item(self.cashout)

    def _refresh(self):
        g = self.game
        payout = int(g.bet * g.multiplier)
        self.cashout.label = f"Cash Out ({g.multiplier:.2f}×, +{payout - g.bet})"
        self.cashout.disabled = g.ended or g.streak == 0


class HigherOrLower(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Higher or Lower loaded.")

    async def _resolve(self, interaction: discord.Interaction, view: HighLowView, guessed_higher: bool):
        g = view.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message("Not your game.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return

        old_rank_idx = g.current_rank_idx
        old_suit = g.current_suit
        # Keep redrawing while we get ties — ties are a no-op.
        tie_count = 0
        while True:
            new_rank_idx, new_suit = random_card()
            if new_rank_idx == old_rank_idx:
                tie_count += 1
                if tie_count >= 5:
                    # Pathological safety: just break and treat as miss
                    break
                continue
            break

        if new_rank_idx > old_rank_idx:
            correct = guessed_higher
        else:
            correct = not guessed_higher

        tie_note = ""
        if tie_count > 0:
            tie_note = f" _(after {tie_count} tied redraw(s))_"

        if correct:
            gain = gain_factor(old_rank_idx, guessed_higher)
            g.multiplier *= gain
            g.streak += 1
            g.current_rank_idx = new_rank_idx
            g.current_suit = new_suit
            g.log.append(
                f"{suit_wrap(old_rank_idx, old_suit)} → **{'HIGHER' if guessed_higher else 'LOWER'}** → "
                f"{suit_wrap(new_rank_idx, new_suit)} ✅ (×{gain:.2f} step, now {g.multiplier:.2f}×){tie_note}"
            )
            view._refresh()
            await interaction.response.edit_message(content=self._render(g), view=view)
            return

        # Wrong
        g.ended = True
        g.log.append(
            f"{suit_wrap(old_rank_idx, old_suit)} → **{'HIGHER' if guessed_higher else 'LOWER'}** → "
            f"{suit_wrap(new_rank_idx, new_suit)} ❌ **BUST**{tie_note}"
        )
        g.current_rank_idx = new_rank_idx
        g.current_suit = new_suit
        for child in view.children:
            child.disabled = True
        footer = (
            f"💀 **BUSTED** at streak **{g.streak}**. Lost **{g.bet}** coins.\n"
            f"Balance: **{get_coins(g.guild_id, g.user_id)}**"
        )
        await interaction.response.edit_message(content=self._render(g, footer), view=view)

    def _render(self, g: HighLowGame, footer: str | None = None) -> str:
        lines = [
            f"🃏 **{g.user_name}'s Higher or Lower** — bet **{g.bet}**",
            f"Current card: **{suit_wrap(g.current_rank_idx, g.current_suit)}**",
            f"Streak: **{g.streak}** | Multiplier: **{g.multiplier:.2f}×**",
        ]
        if not g.ended:
            # Show preview gains
            up = gain_factor(g.current_rank_idx, True)
            down = gain_factor(g.current_rank_idx, False)
            lines.append(f"Next correct HIGHER → step ×**{up:.2f}** | LOWER → step ×**{down:.2f}**")
        if g.log:
            lines.append("")
            lines.extend(g.log[-6:])
        if footer:
            lines.append("")
            lines.append(footer)
        return "\n".join(lines)

    async def _start(self, ctx_or_interaction, bet: int):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild
        user = ctx_or_interaction.user if is_slash else ctx_or_interaction.author

        async def reply(content, **kwargs):
            if is_slash:
                await ctx_or_interaction.response.send_message(content, **kwargs)
                return await ctx_or_interaction.original_response()
            return await ctx_or_interaction.send(content, **kwargs)

        if not guild:
            await reply("Server only.")
            return
        jmsg = jail_message(guild.id, user.id)
        if jmsg:
            await reply(jmsg)
            return
        if bet <= 0:
            await reply("Bet > 0.")
            return
        if get_coins(guild.id, user.id) < bet:
            await reply(f"Too broke. Balance: **{get_coins(guild.id, user.id)}**")
            return

        deduct_coins(guild.id, user.id, bet)
        game = HighLowGame(guild.id, user.id, user.display_name, bet)
        view = HighLowView(self, game)
        view._refresh()
        await reply(self._render(game), view=view)

    @commands.command(name="highlow", aliases=["hilo", "higher", "lower"])
    @commands.guild_only()
    async def highlow_prefix(self, ctx, bet: int):
        await self._start(ctx, bet)

    @app_commands.command(name="highlow", description="Higher or Lower — predict the next card. Streak builds multiplier.")
    @app_commands.describe(bet="Coins to risk")
    async def highlow_slash(self, interaction: discord.Interaction, bet: int):
        await self._start(interaction, bet)


async def setup(bot):
    await bot.add_cog(HigherOrLower(bot))
