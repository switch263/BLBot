"""Loot Dig — a free, twice-daily 4x4 push-your-luck grid, cousin to the grid
games (gridgame.GridView) but on /loot's schedule instead of a bet.

15 of the 16 tiles are loot: each one you flip adds an ESCALATING chunk to a
running bank (early tiles pay little, later ones pay a lot), and clearing all
15 pays the full 5,000,000,000 cap. One tile is bad juju 💀 — flip it and the
round's accrued bank is gone. Cash Out banks what you've dug any time.

No stake: winnings are minted straight to the wallet (like /loot), not paid
from the house pot. Available once per am/pm slot on the SAME 00:00/12:00
schedule as /loot, but on its own independent cooldown — you can do both.
"""
import discord
from discord.ext import commands
from discord import app_commands
from datetime import date
import random
import logging

import economy
from economy import add_coins, record_game, get_coins
from amount import format_compact
from game_common import STAKE_TIMEOUT, button_label
from gridgame import GridView
from cogs.lootdrop import _current_slot  # share /loot's am/pm slot schedule

logger = logging.getLogger(__name__)

GRID_ROWS = 4
GRID_COLS = 4
GRID_SIZE = GRID_ROWS * GRID_COLS  # 16
NUM_JUJU = 1                        # the one cursed tile
NUM_LOOT = GRID_SIZE - NUM_JUJU     # 15 payout tiles
DIG_CAP = 5_000_000_000            # clearing all 15 pays exactly this

KV_NAMESPACE = "juju"


def _build_cumulative() -> list[int]:
    """Cumulative payout after flipping n safe tiles (index 0..15). Increments
    escalate as n^2, and flipping all 15 totals exactly DIG_CAP."""
    total_w = sum(n * n for n in range(1, NUM_LOOT + 1))
    cum = [0]
    acc = 0
    for n in range(1, NUM_LOOT + 1):
        acc += n * n
        cum.append(DIG_CAP * acc // total_w)
    cum[NUM_LOOT] = DIG_CAP  # force the full-clear to the exact cap
    return cum


# PAYOUT_CUMULATIVE[n] = coins banked after flipping n safe tiles.
PAYOUT_CUMULATIVE = _build_cumulative()


def _slot_key() -> str:
    return f"last_{_current_slot()}"


JUJU_NARRATIVES = [
    "You dig up a cursed idol. It hisses. Everything you banked turns to dust.",
    "Bad juju. The hole collapses and swallows the haul whole.",
    "A skull winks at you from the dirt. Then your coins are gone.",
    "You felt the bad vibes a second too late. The dig eats it all.",
    "Something ancient did NOT want to be found. It keeps your loot as rent.",
]

DIG_FLAVOR = [
    "Clink — more coins in the dirt.",
    "Another pocket of loot. Keep digging?",
    "The shovel hits something shiny.",
    "Pay dirt. Literally.",
    "A fatter seam this time.",
]

CASHOUT_FLAVOR = [
    "You haul the loot up and call it.",
    "Smart — you quit while the hole's still friendly.",
    "Pockets full. You climb out.",
    "You bank the dig before the juju finds you.",
]


class DigView(GridView):
    HIDDEN_LABEL = "🟫"

    def __init__(self, cog, guild_id: int, user_id: int, user_name: str):
        super().__init__(user_id, rows=GRID_ROWS, cols=GRID_COLS, timeout=STAKE_TIMEOUT,
                         not_yours="Dig your own hole.")
        self.cog = cog
        self.guild_id = guild_id
        self.user_name = user_name
        self.juju = random.randrange(GRID_SIZE)
        self.revealed: set[int] = set()
        self.safe = 0
        self.action_btn.label = "Cash Out (0)"
        self.action_btn.emoji = "🧺"

    @property
    def bank(self) -> int:
        return PAYOUT_CUMULATIVE[self.safe]

    # ---- GridView hooks ---------------------------------------------------
    def tile_face(self, idx: int):
        if idx == self.juju:
            return "💀", discord.ButtonStyle.danger
        if idx in self.revealed:
            return "🪙", discord.ButtonStyle.success
        return None

    async def on_tile(self, interaction: discord.Interaction, idx: int):
        self.revealed.add(idx)
        self.tile_btns[idx].disabled = True

        if idx == self.juju:
            lost = self.bank
            record_game(self.guild_id, self.user_id, "juju", won=False)
            self.finish()
            content = self.cog._render(
                self, f"💀 **BAD JUJU!** {random.choice(JUJU_NARRATIVES)}\n"
                      f"The **{lost:,}** coins you'd dug up are gone.")
            await interaction.response.edit_message(content=content, view=self)
            return

        # Loot tile
        self.safe += 1
        self.tile_btns[idx].label = "🪙"
        self.tile_btns[idx].style = discord.ButtonStyle.success

        if self.safe >= NUM_LOOT:
            # Cleared the whole board — the full cap, auto-banked.
            await self._bank(interaction,
                             f"🏆 **CLEARED THE DIG!** Every tile was loot — you haul the "
                             f"full **{DIG_CAP:,}** coins out of the ground.")
            return

        self._refresh_cashout()
        await interaction.response.edit_message(
            content=self.cog._render(self, random.choice(DIG_FLAVOR)), view=self)

    async def on_action(self, interaction: discord.Interaction):
        if self.safe == 0:
            await interaction.response.send_message(
                "Dig at least one tile before you cash out.", ephemeral=True)
            return
        await self._bank(interaction,
                         f"🧺 **Cashed out after {self.safe} tiles.** {random.choice(CASHOUT_FLAVOR)}")

    async def _bank(self, interaction: discord.Interaction, headline: str):
        amount = self.bank
        add_coins(self.guild_id, self.user_id, amount)
        record_game(self.guild_id, self.user_id, "juju", won=True)
        self.finish()
        content = self.cog._render(self, f"{headline}\nBanked **+{amount:,}** coins.")
        await interaction.response.edit_message(content=content, view=self)

    async def on_abandon(self):
        # No stake to refund — just auto-bank whatever was dug up.
        if self.safe > 0:
            amount = self.bank
            add_coins(self.guild_id, self.user_id, amount)
            record_game(self.guild_id, self.user_id, "juju", won=True)
            footer = (f"⏰ **Auto-cashed** at {self.safe} tiles — you went quiet. "
                      f"Banked **+{amount:,}** coins.")
        else:
            footer = "⏰ You wandered off before digging anything. Nothing banked."
        self.finish()
        if self.message is None:
            return
        try:
            await self.message.edit(content=self.cog._render(self, footer), view=self)
        except discord.HTTPException:
            pass

    def _refresh_cashout(self):
        self.action_btn.label = button_label(f"Cash Out ({format_compact(self.bank)})")


class LootDig(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Loot Dig loaded.")

    def _cooldown_refusal(self, guild_id: int, user_id: int):
        """None if the current am/pm slot is free, else a refusal string."""
        if economy.kv_get(guild_id, user_id, KV_NAMESPACE, _slot_key()) == date.today().isoformat():
            return ("⛏️ You've already worked the dig this shift. It resets at "
                    "**00:00** and **12:00** — same as `/loot`.")
        return None

    def _stamp(self, guild_id: int, user_id: int):
        economy.kv_set(guild_id, user_id, KV_NAMESPACE, _slot_key(), date.today().isoformat())

    def _render(self, v: DigView, footer: str | None = None) -> str:
        lines = [
            f"⛏️ **{v.user_name}'s Loot Dig** — free, twice a day",
            f"**{NUM_LOOT}** tiles are loot (escalating, up to **{DIG_CAP:,}** for a full clear); "
            f"**{NUM_JUJU}** is 💀 bad juju that buries everything you've dug.",
            f"Tiles dug: **{v.safe}** | Banked so far: **{v.bank:,}**",
        ]
        if not v.resolved:
            lines.append("Each tile digs up MORE than the last. Cash out any time — or push for the 💀.")
        if footer:
            lines.append("")
            lines.append(footer)
            lines.append(f"Balance: **{get_coins(v.guild_id, v.user_id):,}**")
        return "\n".join(lines)

    async def _start(self, ctx_or_interaction):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild
        user = ctx_or_interaction.user if is_slash else ctx_or_interaction.author

        async def reply(content, **kwargs):
            if is_slash:
                await ctx_or_interaction.response.send_message(content, **kwargs)
                return await ctx_or_interaction.original_response()
            return await ctx_or_interaction.send(content, **kwargs)

        if guild is None:
            await reply("The dig's only open in a server.")
            return
        refusal = self._cooldown_refusal(guild.id, user.id)
        if refusal:
            await reply(refusal)
            return
        view = DigView(self, guild.id, user.id, user.display_name)
        view.message = await reply(self._render(view), view=view)
        # A dig actually started — spend this shift's slot (after the send, so a
        # failed message doesn't silently burn it).
        self._stamp(guild.id, user.id)

    @commands.command(name="dig", aliases=["juju", "lootdig"])
    @commands.guild_only()
    async def dig_prefix(self, ctx):
        await self._start(ctx)

    @app_commands.command(name="dig", description="Dig for loot — free, twice a day. One tile is bad juju.")
    async def dig_slash(self, interaction: discord.Interaction):
        await self._start(interaction)


async def setup(bot):
    await bot.add_cog(LootDig(bot))
