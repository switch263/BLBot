"""Mines — a grid push-your-luck game.

A 5×4 board of 20 tiles hides `mines` bombs. Reveal tiles one at a time: every
safe tile (a 💎) ratchets your multiplier up, hitting a 💣 busts you for the
whole stake. Cash out whenever. Reveal every safe tile and it auto-cashes at the
top.

Money model mirrors the Gauntlet (cogs/gauntlet.py): the ante goes to the house
via transfer_to_house, the cash-out comes back through casino_payout, and any
shortfall is minted so a winner is always paid in full (the memorial tithe is
handled by those helpers). Two extra guards exist because a mines multiplier
grows far faster than the Gauntlet's ladder (clearing 3-mine boards pays ~1000×):
  - MINES_MAX_MULT caps the realized multiplier, and
  - MINES_MAX_HOUSE_PCT keeps the bet a small slice of the house,
so the most a single board can mint stays bounded.

The fair multiplier after revealing k safe tiles is (1 - edge) / P(survive k),
where P(survive k) is the probability of having picked k non-mine tiles in a
row. The (1 - edge) factor is the house edge, applied uniformly at every depth.
"""

import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

import economy
from economy import jail_message
from amount import parse_amount, amount_error

logger = logging.getLogger(__name__)

MINES_N = 20            # 5 columns × 4 rows of tiles
MINES_DEFAULT = 3
MINES_MIN = 1
MINES_MAX = 19          # leave at least one safe tile
MINES_EDGE = 0.03       # house edge baked into every multiplier
MINES_MAX_MULT = 100.0  # realized multiplier is capped here (bounds minting)
MINES_MAX_HOUSE_PCT = 0.10  # bet ceiling = 10% of house on-hand
MINES_MIN_BET = 1_000

_TILES_PER_ROW = 5


class MinesView(discord.ui.View):
    """One board for one player. 20 tile buttons (rows 0-3) plus a Cash Out
    button (row 4). Gated to the player; on timeout it auto-cashes whatever's
    banked so a survived board is never lost."""

    def __init__(self, cog, guild_id: int, user_id: int, bet: int, num_mines: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.bet = bet
        self.num_mines = num_mines
        self.safe = MINES_N - num_mines
        self.mines = set(random.sample(range(MINES_N), num_mines))
        self.revealed: set[int] = set()
        self.message: discord.Message | None = None
        self.resolved = False

        self.tile_btns: list[discord.ui.Button] = []
        for i in range(MINES_N):
            btn = discord.ui.Button(label="⬛", style=discord.ButtonStyle.secondary, row=i // _TILES_PER_ROW)
            btn.callback = self._make_tile_cb(i)
            self.tile_btns.append(btn)
            self.add_item(btn)

        self.cash_btn = discord.ui.Button(style=discord.ButtonStyle.success, row=4)
        self.cash_btn.callback = self._on_cash
        self.add_item(self.cash_btn)
        self._sync()

    # ---- multiplier math ------------------------------------------------
    def _mult(self, k: int) -> float:
        if k <= 0:
            return 1.0
        p = 1.0
        for i in range(k):
            p *= (self.safe - i) / (MINES_N - i)
        return min(MINES_MAX_MULT, (1 - MINES_EDGE) / p)

    @property
    def current_mult(self) -> float:
        return self._mult(len(self.revealed))

    @property
    def banked(self) -> int:
        return int(self.bet * self.current_mult)

    # ---- rendering ------------------------------------------------------
    def _sync(self):
        self.cash_btn.label = f"💰 Cash Out ({self.banked:,})"

    def _disable_all(self):
        for child in self.children:
            child.disabled = True

    def active_embed(self) -> discord.Embed:
        k = len(self.revealed)
        lines = [
            f"**Bet:** {self.bet:,}   **Mines:** {self.num_mines}/{MINES_N}",
            f"**Gems:** {k}/{self.safe}   **Banked:** {self.banked:,} (×{self.current_mult:g})",
        ]
        if k < self.safe:
            nxt = self._mult(k + 1)
            lines.append(f"Next gem → ×{nxt:g} (**{int(self.bet * nxt):,}**)")
        lines.append("Pick a tile, or cash out.")
        return discord.Embed(
            title="💣 MINES",
            description="\n".join(lines),
            color=discord.Color.teal(),
        )

    def _cash_embed(self, paid: int, minted: int, cleared: bool = False) -> discord.Embed:
        self._reveal_board()
        self._disable_all()
        net = paid - self.bet
        sign = "+" if net >= 0 else ""
        mint_note = "" if minted <= 0 else "\n*(the house fired up the money printer to cover it 🖨️)*"
        if cleared:
            title = "🏆 SWEPT THE BOARD"
            lead = f"You cleared all **{self.safe}** gems at **×{self.current_mult:g}**. Nerves of steel."
        else:
            title = "💰 CASHED OUT"
            lead = f"You banked **{len(self.revealed)}** gem(s) at **×{self.current_mult:g}**."
        return discord.Embed(
            title=title,
            description=f"{lead}\nPayout: **{paid:,}**  (net {sign}{net:,}){mint_note}",
            color=discord.Color.green(),
        )

    def _bust_embed(self, hit: int) -> discord.Embed:
        self._reveal_board(hit=hit)
        self._disable_all()
        return discord.Embed(
            title="💥 BOOM",
            description=(
                f"Tile {hit + 1} was a mine. Your **{self.bet:,}** stays with the house — "
                f"after **{len(self.revealed)}** clean pick(s)."
            ),
            color=discord.Color.dark_red(),
        )

    def _reveal_board(self, hit: int | None = None):
        """Flip every tile face-up for the end-state render."""
        for i, btn in enumerate(self.tile_btns):
            if i in self.mines:
                btn.label = "💥" if i == hit else "💣"
                btn.style = discord.ButtonStyle.danger
            elif i in self.revealed:
                btn.label = "💎"
                btn.style = discord.ButtonStyle.success
            else:
                btn.label = "🟦"
                btn.style = discord.ButtonStyle.secondary

    # ---- payout ---------------------------------------------------------
    def _payout_now(self, won: bool) -> tuple[int, int]:
        """Pay the player IN FULL, minting any shortfall; record the game.
        Returns (paid, minted)."""
        requested = int(self.bet * self.current_mult)
        paid = economy.casino_payout(self.guild_id, self.user_id, requested)
        minted = 0
        if paid < requested:
            minted = requested - paid
            economy.add_coins(self.guild_id, self.user_id, minted)
        economy.record_game(self.guild_id, self.user_id, "mines", won)
        return requested, minted

    # ---- interaction ----------------------------------------------------
    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Not your board — start your own with `/mines`.", ephemeral=True
            )
            return False
        return True

    def _make_tile_cb(self, index: int):
        async def _cb(interaction: discord.Interaction):
            if not await self._guard(interaction) or self.resolved:
                return
            if index in self.revealed:
                await interaction.response.defer()
                return
            if index in self.mines:  # bust
                self.resolved = True
                economy.record_game(self.guild_id, self.user_id, "mines", False)
                await interaction.response.edit_message(embed=self._bust_embed(index), view=self)
                self.stop()
                return
            # safe pick
            self.revealed.add(index)
            self.tile_btns[index].label = "💎"
            self.tile_btns[index].style = discord.ButtonStyle.success
            self.tile_btns[index].disabled = True
            self._sync()
            if len(self.revealed) == self.safe:  # swept the board → auto cash out
                self.resolved = True
                paid, minted = self._payout_now(True)
                await interaction.response.edit_message(
                    embed=self._cash_embed(paid, minted, cleared=True), view=self
                )
                self.stop()
                return
            await interaction.response.edit_message(embed=self.active_embed(), view=self)
        return _cb

    async def _on_cash(self, interaction: discord.Interaction):
        if not await self._guard(interaction) or self.resolved:
            return
        if not self.revealed:
            await interaction.response.send_message(
                "Reveal at least one tile before cashing out.", ephemeral=True
            )
            return
        self.resolved = True
        paid, minted = self._payout_now(self.current_mult > 1.0)
        await interaction.response.edit_message(embed=self._cash_embed(paid, minted), view=self)
        self.stop()

    async def on_timeout(self):
        if self.resolved or self.message is None:
            return
        self.resolved = True
        if not self.revealed:
            # Nothing banked — refund the ante so an ignored board isn't a loss.
            economy.casino_payout(self.guild_id, self.user_id, self.bet)
            economy.record_game(self.guild_id, self.user_id, "mines", False)
            self._reveal_board()
            self._disable_all()
            embed = discord.Embed(
                title="🕰️ Board Abandoned",
                description=f"You never picked a tile. Your **{self.bet:,}** was refunded.",
                color=discord.Color.greyple(),
            )
        else:
            paid, minted = self._payout_now(self.current_mult > 1.0)
            embed = self._cash_embed(paid, minted)
            embed.set_footer(text="Auto-cashed out — you went quiet.")
        try:
            await self.message.edit(embed=embed, view=self)
        except discord.HTTPException:
            pass


class Mines(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Mines loaded.")

    async def _start(self, ctx_or_interaction, bet_text, num_mines: int):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild
        user = ctx_or_interaction.user if is_slash else ctx_or_interaction.author

        async def reply(content=None, **kwargs):
            if is_slash:
                await ctx_or_interaction.response.send_message(content, **kwargs)
                return await ctx_or_interaction.original_response()
            return await ctx_or_interaction.send(content, **kwargs)

        if not guild:
            await reply("Server only.")
            return
        if bet_text is None:
            await reply("Usage: `!mines <amount> [mines]` — e.g. `!mines 250k 3`.")
            return
        amt = parse_amount(bet_text)
        if amt is None:
            await reply(amount_error(bet_text))
            return
        bet = amt

        if not (MINES_MIN <= num_mines <= MINES_MAX):
            await reply(f"Mines must be between **{MINES_MIN}** and **{MINES_MAX}**.")
            return
        jmsg = jail_message(guild.id, user.id)
        if jmsg:
            await reply(jmsg)
            return
        if bet < MINES_MIN_BET:
            await reply(f"Minimum buy-in for Mines is **{MINES_MIN_BET:,}**.")
            return

        house_on_hand = economy.get_coins(guild.id, economy.get_house_id())
        table_limit = int(house_on_hand * MINES_MAX_HOUSE_PCT)
        if table_limit < MINES_MIN_BET:
            await reply("The house is too thin to open the Mines table right now. Come back later.")
            return
        if bet > table_limit:
            await reply(
                f"Table limit right now is **{table_limit:,}** "
                f"({int(MINES_MAX_HOUSE_PCT * 100)}% of the house bankroll)."
            )
            return

        bet_result = economy.transfer_to_house(guild.id, user.id, bet)
        if not bet_result.get("ok"):
            if bet_result.get("error") == "broke":
                await reply(f"Too broke. Balance: **{bet_result.get('have', 0):,}**")
            else:
                await reply("Bet failed. Try again.")
            return

        view = MinesView(self, guild.id, user.id, bet, num_mines)
        msg = await reply(embed=view.active_embed(), view=view)
        view.message = msg

    @commands.command(name="mines", aliases=["minesweeper"])
    @commands.guild_only()
    async def mines_prefix(self, ctx, bet: str = None, mines: int = MINES_DEFAULT):
        await self._start(ctx, bet, mines)

    @app_commands.command(name="mines", description="Reveal gems, dodge mines — cash out or boom. No flat 100k cap.")
    @app_commands.describe(
        bet="Coins to risk (e.g. 250k, 2m). Limited by the house bankroll.",
        mines=f"How many mines on the board ({MINES_MIN}-{MINES_MAX}, default {MINES_DEFAULT}). More mines = bigger multipliers.",
    )
    async def mines_slash(self, interaction: discord.Interaction, bet: str, mines: int = MINES_DEFAULT):
        await self._start(interaction, bet, mines)


async def setup(bot):
    await bot.add_cog(Mines(bot))
