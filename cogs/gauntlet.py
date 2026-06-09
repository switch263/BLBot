"""The Gauntlet — a high-roller push-your-luck ladder.

A new shape for this bot: instead of a single bet→roll→payout, you ante any
amount and then repeatedly choose to **cash out** the multiplier you've banked
or **push your luck** into the next round. Each push either survives (the
multiplier balloons, the odds shrink) or busts (you lose the whole stake).

Why it isn't gated to the flat 100k MAX_BET: the table limit is a fraction of
the *house on-hand bankroll* (GAUNTLET_MAX_HOUSE_PCT), so a fat house lets high
rollers bet big. Winners are always paid in full — if casino_payout can't cover
a cash-out from house funds, the shortfall is minted (the casino already prints
money to replenish its reserve; this is the same idea at the moment of payout).
The table limit therefore exists only to bound how much can be minted in a
single lucky run, not to cap the player. The ladder also carries a per-push
house edge (the expected value of pushing is always below the multiplier you'd
walk away with), so over time the house grinds ahead no matter the stake. The
ante routes through transfer_to_house and the cash-out through casino_payout, so
the memorial tithe is handled automatically.
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

# Bet ceiling is this fraction of the house on-hand bankroll, not a flat number.
# It bounds how much the casino might have to mint to cover one lucky cash-out
# (winners are always paid in full — see _payout_now), so it caps per-event
# inflation rather than capping the player.
GAUNTLET_MAX_HOUSE_PCT = 0.25
GAUNTLET_MIN_BET = 1_000

# The ladder: (survival_prob, cumulative payout multiplier if you survive).
# Verify the edge by hand — EV(push) = survival_prob × next_mult must be below
# the multiplier you'd keep by cashing out *now*:
#   r1 from ×1.0: 0.75×1.3 = 0.975
#   r2 from ×1.3: 0.66×1.9 = 1.254  (< 1.3)
#   r3 from ×1.9: 0.57×3.1 = 1.767  (< 1.9)
#   r4 from ×3.1: 0.48×5.8 = 2.784  (< 3.1)
#   r5 from ×5.8: 0.40×12.0 = 4.80  (< 5.8)
# Survive all five and the ladder auto-cashes at the top (×12). Tune freely.
GAUNTLET_ROUNDS = [
    (0.75, 1.3),
    (0.66, 1.9),
    (0.57, 3.1),
    (0.48, 5.8),
    (0.40, 12.0),
]


class GauntletView(discord.ui.View):
    """Drives one player's run. Two buttons — Cash Out and Push Your Luck —
    gated to the runner. On timeout it auto-cashes whatever's banked so a player
    who wanders off never loses a survived run."""

    def __init__(self, cog, guild_id: int, user_id: int, bet: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.bet = bet
        self.survived = 0
        self.message: discord.Message | None = None
        self.resolved = False

        self.cash_btn = discord.ui.Button(style=discord.ButtonStyle.success)
        self.push_btn = discord.ui.Button(
            style=discord.ButtonStyle.danger, label="🎲 Push Your Luck"
        )
        self.cash_btn.callback = self._on_cash
        self.push_btn.callback = self._on_push
        self.add_item(self.cash_btn)
        self.add_item(self.push_btn)
        self._sync()

    # ---- state ----------------------------------------------------------
    @property
    def current_mult(self) -> float:
        return 1.0 if self.survived == 0 else GAUNTLET_ROUNDS[self.survived - 1][1]

    @property
    def banked(self) -> int:
        return int(self.bet * self.current_mult)

    def _next_round(self):
        """The (survival_prob, multiplier) the player is about to risk, or None
        if they've cleared the whole ladder."""
        if self.survived < len(GAUNTLET_ROUNDS):
            return GAUNTLET_ROUNDS[self.survived]
        return None

    def _sync(self):
        self.cash_btn.label = f"💰 Cash Out ({self.banked:,})"

    def _disable(self):
        for child in self.children:
            child.disabled = True

    # ---- embeds ---------------------------------------------------------
    def active_embed(self) -> discord.Embed:
        p, m = self._next_round()
        win_val = int(self.bet * m)
        lines = [
            f"**Bet:** {self.bet:,}",
            f"**Banked:** {self.banked:,}  (×{self.current_mult:g})",
        ]
        if self.survived:
            lines.append(f"Cleared **{self.survived}** round(s) so far.")
        lines += [
            "",
            f"**Round {self.survived + 1}:** {int(round(p * 100))}% to survive "
            f"→ ×{m:g} (**{win_val:,}**)",
            "Cash out now, or push your luck?",
        ]
        return discord.Embed(
            title="🎰 THE GAUNTLET",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )

    def _cash_embed(self, paid: int, minted: int, cleared: bool = False) -> discord.Embed:
        self._disable()
        net = paid - self.bet
        mint_note = "" if minted <= 0 else "\n*(the house fired up the money printer to cover it 🖨️)*"
        sign = "+" if net >= 0 else ""
        if cleared:
            title = "🏆 CLEARED THE GAUNTLET"
            lead = f"You survived all **{self.survived}** rounds at **×{self.current_mult:g}**. Absolute degenerate."
        else:
            title = "💰 CASHED OUT"
            lead = f"You walked after **{self.survived}** round(s) at **×{self.current_mult:g}**."
        return discord.Embed(
            title=title,
            description=f"{lead}\nPayout: **{paid:,}**  (net {sign}{net:,}){mint_note}",
            color=discord.Color.green(),
        )

    def _bust_embed(self) -> discord.Embed:
        self._disable()
        _p, m = self._next_round()
        missed = int(self.bet * m)
        return discord.Embed(
            title="💥 BUSTED",
            description=(
                f"Round {self.survived + 1} ate you alive. Your **{self.bet:,}** "
                f"stays with the house.\nYou were one nerve away from **{missed:,}**."
            ),
            color=discord.Color.dark_red(),
        )

    # ---- interaction ----------------------------------------------------
    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Not your run — start your own with `/gauntlet`.", ephemeral=True
            )
            return False
        return True

    def _payout_now(self, won: bool) -> tuple[int, int]:
        """Settle the current banked multiplier: pay the player IN FULL, record
        the game. casino_payout draws house funds (on-hand + reserve); any
        shortfall is minted so the winner is never shortchanged. Returns
        (paid, minted) where paid is always the full requested amount."""
        requested = int(self.bet * self.current_mult)
        paid = economy.casino_payout(self.guild_id, self.user_id, requested)
        minted = 0
        if paid < requested:
            minted = requested - paid
            economy.add_coins(self.guild_id, self.user_id, minted)
        economy.record_game(self.guild_id, self.user_id, "gauntlet", won)
        return requested, minted

    async def _on_cash(self, interaction: discord.Interaction):
        if not await self._guard(interaction) or self.resolved:
            return
        self.resolved = True
        paid, minted = self._payout_now(self.current_mult > 1.0)
        await interaction.response.edit_message(
            embed=self._cash_embed(paid, minted), view=self
        )
        self.stop()

    async def _on_push(self, interaction: discord.Interaction):
        if not await self._guard(interaction) or self.resolved:
            return
        p, _m = self._next_round()
        if random.random() >= p:  # bust — survived stays put so _bust_embed names the killer round
            self.resolved = True
            economy.record_game(self.guild_id, self.user_id, "gauntlet", False)
            await interaction.response.edit_message(embed=self._bust_embed(), view=self)
            self.stop()
            return
        self.survived += 1
        self._sync()
        if self._next_round() is None:  # cleared the top rung — auto cash out
            self.resolved = True
            paid, minted = self._payout_now(True)
            await interaction.response.edit_message(
                embed=self._cash_embed(paid, minted, cleared=True), view=self
            )
            self.stop()
            return
        await interaction.response.edit_message(embed=self.active_embed(), view=self)

    async def on_timeout(self):
        if self.resolved or self.message is None:
            return
        self.resolved = True
        paid, minted = self._payout_now(self.current_mult > 1.0)
        embed = self._cash_embed(paid, minted)
        embed.set_footer(text="Auto-cashed out — you went quiet.")
        try:
            await self.message.edit(embed=embed, view=self)
        except discord.HTTPException:
            pass


class Gauntlet(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("The Gauntlet loaded.")

    async def _start(self, ctx_or_interaction, bet_text):
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
            await reply("Usage: `!gauntlet <amount>` — e.g. `!gauntlet 500k`.")
            return
        amt = parse_amount(bet_text)
        if amt is None:
            await reply(amount_error(bet_text))
            return
        bet = amt

        jmsg = jail_message(guild.id, user.id)
        if jmsg:
            await reply(jmsg)
            return
        if bet < GAUNTLET_MIN_BET:
            await reply(f"Minimum buy-in for the Gauntlet is **{GAUNTLET_MIN_BET:,}**.")
            return

        # The whole point: the ceiling scales with the house, not a flat 100k.
        house_on_hand = economy.get_coins(guild.id, economy.get_house_id())
        table_limit = int(house_on_hand * GAUNTLET_MAX_HOUSE_PCT)
        if table_limit < GAUNTLET_MIN_BET:
            await reply("The house is too thin to open the Gauntlet right now. Come back when the pot's healthier.")
            return
        if bet > table_limit:
            await reply(
                f"Table limit right now is **{table_limit:,}** "
                f"({int(GAUNTLET_MAX_HOUSE_PCT * 100)}% of the house bankroll). "
                f"High roller, but not *that* high."
            )
            return

        bet_result = economy.transfer_to_house(guild.id, user.id, bet)
        if not bet_result.get("ok"):
            if bet_result.get("error") == "broke":
                await reply(f"Too broke. Balance: **{bet_result.get('have', 0):,}**")
            else:
                await reply("Bet failed. Try again.")
            return

        view = GauntletView(self, guild.id, user.id, bet)
        msg = await reply(embed=view.active_embed(), view=view)
        view.message = msg

    @commands.command(name="gauntlet", aliases=["thegauntlet"])
    @commands.guild_only()
    async def gauntlet_prefix(self, ctx, bet: str = None):
        await self._start(ctx, bet)

    @app_commands.command(
        name="gauntlet",
        description="High-roller push-your-luck ladder. Cash out or bust — no flat 100k cap.",
    )
    @app_commands.describe(bet="Coins to risk (e.g. 250k, 2m). Limited by the house bankroll, not a flat 100k.")
    async def gauntlet_slash(self, interaction: discord.Interaction, bet: str):
        await self._start(interaction, bet)


async def setup(bot):
    await bot.add_cog(Gauntlet(bot))
