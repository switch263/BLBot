import discord
from discord.ext import commands
from discord import app_commands
import random
import logging
from collections import Counter

from economy import (
    get_coins, jail_message, record_game,
    transfer_to_house, casino_payout,
    MAX_BET,
)

logger = logging.getLogger(__name__)

CODE_LENGTH = 3
DIGITS = [0, 1, 2, 3]  # four numbers, and the same one CAN repeat across wheels
MAX_ATTEMPTS = 5
GAME_NAME = "vault_extra_hard"

# A 3-wheel suitcase lock: each wheel is 0-3 and the same number can appear on
# more than one wheel → 4^3 = 64 possible combinations. Unlike the other vaults
# you get ONLY peg counts back (how many right, how many misplaced) — not which
# position — so it's pure Bulls-and-Cows deduction. Hard, but crackable.
#
# Payout by attempts used (1-indexed). On failure the full bet goes to the
# house. Tuned for the 64-combo space: big reward for an early (lucky/sharp)
# crack, break-even if you limp to the last try, so it can't be farmed.
PAYOUT_BY_ATTEMPT = {
    1: 50.0,
    2: 15.0,
    3: 5.0,
    4: 2.0,
    5: 1.0,
}

SOLVE_FLAVOR = [
    "🔓 **The suitcase clasps spring open with a satisfying *snap*.**",
    "🔓 **Three wheels align. The briefcase yawns open.**",
    "🔓 **CLICK-CLICK-CLICK. You read the lock like a book.**",
    "🔓 **The combination falls. The case surrenders its secrets.**",
    "🔓 **Even the lock is impressed. It opens almost politely.**",
]

FAIL_FLAVOR = [
    "🚨 **The case auto-shreds its contents. The house keeps your stake.**",
    "🚨 **Dye pack. Alarm. A very smug briefcase. The house collects.**",
    "🚨 **The wheels jam solid. Whatever was inside is gone — so is your bet.**",
    "🚨 **Five wrong tugs and the handle snaps off. The house pockets everything.**",
]


def score(guess: list[int], code: list[int]) -> tuple[int, int, int]:
    """Repeat-aware Mastermind / Bulls-and-Cows scoring.
    Returns (exact, misplaced, absent):
      exact     — right digit in the right wheel
      misplaced — right digit, wrong wheel (no double-counting)
      absent    — pegs that match nothing
    """
    exact = sum(1 for g, c in zip(guess, code) if g == c)
    gc, cc = Counter(guess), Counter(code)
    total_match = sum(min(gc[d], cc[d]) for d in gc)
    misplaced = total_match - exact
    absent = CODE_LENGTH - total_match
    return exact, misplaced, absent


class VaultGame:
    def __init__(self, guild_id, user_id, user_name, bet):
        self.guild_id = guild_id
        self.user_id = user_id
        self.user_name = user_name
        self.bet = bet
        # Repeats allowed → choice per wheel, not sample.
        self.code = [random.choice(DIGITS) for _ in range(CODE_LENGTH)]
        self.attempts: list[tuple[list[int], str]] = []
        self.current: list[int] = []
        self.ended = False

    def feedback_for(self, guess: list[int]) -> tuple[str, bool]:
        exact, misplaced, absent = score(guess, self.code)
        solved = exact == CODE_LENGTH
        fb = f"🟢×{exact}  🟡×{misplaced}  ⚫×{absent}"
        return fb, solved


class DigitButton(discord.ui.Button):
    def __init__(self, digit: int, row: int):
        super().__init__(style=discord.ButtonStyle.secondary, label=str(digit), row=row)
        self.digit = digit

    async def callback(self, interaction: discord.Interaction):
        view: "VaultView" = self.view  # type: ignore
        g = view.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message("Not your suitcase.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return
        if len(g.current) >= CODE_LENGTH:
            await interaction.response.send_message("All 3 wheels set — submit or undo.", ephemeral=True)
            return
        # Repeats ARE allowed here — no duplicate check.
        g.current.append(self.digit)
        await interaction.response.edit_message(content=view.cog._render(g), view=view)


class UndoButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="Undo", emoji="↩️", row=1)

    async def callback(self, interaction: discord.Interaction):
        view: "VaultView" = self.view  # type: ignore
        g = view.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message("Not your suitcase.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return
        if g.current:
            g.current.pop()
        await interaction.response.edit_message(content=view.cog._render(g), view=view)


class SubmitButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.success, label="Submit", emoji="🧳", row=1)

    async def callback(self, interaction: discord.Interaction):
        view: "VaultView" = self.view  # type: ignore
        g = view.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message("Not your suitcase.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return
        if len(g.current) != CODE_LENGTH:
            await interaction.response.send_message(f"Set all {CODE_LENGTH} wheels first.", ephemeral=True)
            return
        feedback, solved = g.feedback_for(g.current)
        g.attempts.append((list(g.current), feedback))
        attempts_used = len(g.attempts)
        g.current = []

        if solved:
            g.ended = True
            mult = PAYOUT_BY_ATTEMPT.get(attempts_used, PAYOUT_BY_ATTEMPT[MAX_ATTEMPTS])
            requested = int(g.bet * mult)
            payout = casino_payout(g.guild_id, g.user_id, requested)
            record_game(g.guild_id, g.user_id, GAME_NAME, True)
            for child in view.children:
                child.disabled = True
            short_note = ""
            if payout < requested:
                short_note = f" *(house was short — owed {requested:,})*"
            footer = (
                f"{random.choice(SOLVE_FLAVOR)}\n"
                f"Cracked in **{attempts_used}** attempt(s). Payout: **{mult:.2f}×** → **{payout:,}** coins{short_note} "
                f"(net **{payout - g.bet:+,}**).\n"
                f"Balance: **{get_coins(g.guild_id, g.user_id):,}**"
            )
        elif attempts_used >= MAX_ATTEMPTS:
            g.ended = True
            # Bet already routed to the house at game start; nothing more on fail.
            record_game(g.guild_id, g.user_id, GAME_NAME, False)
            for child in view.children:
                child.disabled = True
            code_str = "".join(str(d) for d in g.code)
            footer = (
                f"{random.choice(FAIL_FLAVOR)}\n"
                f"The combination was **{code_str}**. **{g.bet:,}** coins transferred to the house.\n"
                f"Balance: **{get_coins(g.guild_id, g.user_id):,}**"
            )
        else:
            footer = None

        await interaction.response.edit_message(content=view.cog._render(g, footer), view=view)


class VaultView(discord.ui.View):
    def __init__(self, cog, game: VaultGame):
        super().__init__(timeout=600)
        self.cog = cog
        self.game = game
        # Four digit buttons (0-3) on one row.
        for d in DIGITS:
            self.add_item(DigitButton(d, row=0))
        self.add_item(UndoButton())
        self.add_item(SubmitButton())


class TheVaultExtraHard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("The Vault (Extra Hard / Suitcase Lock) loaded.")

    def _render(self, g: VaultGame, footer: str | None = None) -> str:
        lines = [
            f"🧳🔒 **{g.user_name}'s SUITCASE LOCK** — bet **{g.bet:,}**",
            f"Crack a **{CODE_LENGTH}-wheel combo**, digits **0-3** (**repeats allowed!**). "
            f"**{MAX_ATTEMPTS - len(g.attempts)}** attempts left.",
            f"You only get **counts**, not positions: 🟢 = right digit & wheel | 🟡 = right digit, wrong wheel | ⚫ = not in the combo.",
            "",
        ]
        if g.attempts:
            lines.append("**Attempts:**")
            for i, (guess, fb) in enumerate(g.attempts, 1):
                digits = " ".join(str(d) for d in guess)
                lines.append(f"`{i}.` **{digits}** → {fb}")
        if not g.ended:
            slots = [str(d) for d in g.current] + ["_"] * (CODE_LENGTH - len(g.current))
            lines.append("")
            lines.append(f"**Current combo:** `{' '.join(slots)}`")
            lines.append("")
            lines.append("**Payouts:** 1 try→50× | 2→15× | 3→5× | 4→2× | 5→1×")
            lines.append("*No payout cap. **Lose all 5 → bet goes to the house.***")
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
            await reply("Bet > 0 to take on the suitcase lock.")
            return
        if bet > MAX_BET:
            await reply(f"Easy, high roller — max bet is {MAX_BET:,} coins.")
            return
        bet_result = transfer_to_house(guild.id, user.id, bet)
        if not bet_result.get("ok"):
            if bet_result.get("error") == "broke":
                await reply(f"Too broke. Balance: **{bet_result.get('have', 0):,}**")
            else:
                await reply("Bet failed. Try again.")
            return
        game = VaultGame(guild.id, user.id, user.display_name, bet)
        view = VaultView(self, game)
        await reply(self._render(game), view=view)

    @commands.command(name="vault_extra_hard",
                      aliases=["vaultextrahard", "veh", "suitcase", "briefcase"])
    @commands.guild_only()
    async def vault_extra_hard_prefix(self, ctx, bet: int):
        await self._start(ctx, bet)

    @app_commands.command(
        name="vault_extra_hard",
        description="Suitcase lock: 3 wheels 0-3 (repeats allowed), counts-only hints, 5 tries. Big payouts.",
    )
    @app_commands.describe(bet="Coins to risk (max bet applies)")
    async def vault_extra_hard_slash(self, interaction: discord.Interaction, bet: int):
        await self._start(interaction, bet)


async def setup(bot):
    await bot.add_cog(TheVaultExtraHard(bot))
