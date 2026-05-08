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

CODE_LENGTH = 5
DIGITS = [1, 2, 3, 4, 5, 6, 7, 8, 9]
MAX_ATTEMPTS = 6

# Payout by attempts used (1-indexed). 5-digit code from 1-9 with no repeats =
# 9*8*7*6*5 = 15,120 possibilities, ~42x harder than the standard vault.
PAYOUT_BY_ATTEMPT = {
    1: 50.0,
    2: 25.0,
    3: 12.0,
    4: 6.0,
    5: 3.0,
    6: 1.5,
}

SOLVE_FLAVOR = [
    "🔓 **The reinforced vault hisses open.**",
    "🔓 **Tumblers scream. Plate shifts. THUNK.**",
    "🔓 **The vault concedes. You've outsmarted the algorithm.**",
    "🔓 **An ominous green light. The 12-inch door swings wide.**",
    "🔓 **Even the security guard is impressed.**",
]

FAIL_FLAVOR = [
    "🚨 **SIX STRIKES.** Magnesium thermite welds the vault shut.",
    "🚨 **Iris scanners, ankle monitors, drone strike. You lose everything.**",
    "🚨 **The vault's neural net laughs. Code burned. Bet evaporated.**",
    "🚨 **Lockdown. The walls slide in. You squeeze out empty-handed.**",
]


class VaultGame:
    def __init__(self, guild_id, user_id, user_name, bet):
        self.guild_id = guild_id
        self.user_id = user_id
        self.user_name = user_name
        self.bet = bet
        self.code = random.sample(DIGITS, CODE_LENGTH)
        self.attempts: list[tuple[list[int], str]] = []
        self.current: list[int] = []
        self.ended = False

    def feedback_for(self, guess: list[int]) -> str:
        parts = []
        for i, d in enumerate(guess):
            if d == self.code[i]:
                parts.append("🟢")
            elif d in self.code:
                parts.append("🟡")
            else:
                parts.append("⚫")
        return "".join(parts)


class DigitButton(discord.ui.Button):
    def __init__(self, digit: int, row: int):
        super().__init__(style=discord.ButtonStyle.secondary, label=str(digit), row=row)
        self.digit = digit

    async def callback(self, interaction: discord.Interaction):
        view: "VaultView" = self.view  # type: ignore
        g = view.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message("Not your vault.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return
        if len(g.current) >= CODE_LENGTH:
            await interaction.response.send_message("Guess is full — submit or undo.", ephemeral=True)
            return
        if self.digit in g.current:
            await interaction.response.send_message("No repeated digits — the real code has none.", ephemeral=True)
            return
        g.current.append(self.digit)
        view._refresh()
        await interaction.response.edit_message(content=view.cog._render(g), view=view)


class UndoButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="Undo", emoji="↩️", row=2)

    async def callback(self, interaction: discord.Interaction):
        view: "VaultView" = self.view  # type: ignore
        g = view.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message("Not your vault.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return
        if g.current:
            g.current.pop()
        view._refresh()
        await interaction.response.edit_message(content=view.cog._render(g), view=view)


class SubmitButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.success, label="Submit", emoji="🔒", row=2)

    async def callback(self, interaction: discord.Interaction):
        view: "VaultView" = self.view  # type: ignore
        g = view.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message("Not your vault.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return
        if len(g.current) != CODE_LENGTH:
            await interaction.response.send_message(f"Need {CODE_LENGTH} digits.", ephemeral=True)
            return
        feedback = g.feedback_for(g.current)
        g.attempts.append((list(g.current), feedback))
        solved = feedback == "🟢" * CODE_LENGTH
        attempts_used = len(g.attempts)
        g.current = []

        if solved:
            g.ended = True
            mult = PAYOUT_BY_ATTEMPT.get(attempts_used, PAYOUT_BY_ATTEMPT[MAX_ATTEMPTS])
            payout = int(g.bet * mult)
            add_coins(g.guild_id, g.user_id, payout)
            for child in view.children:
                child.disabled = True
            footer = (
                f"{random.choice(SOLVE_FLAVOR)}\n"
                f"Cracked in **{attempts_used}** attempt(s). Payout: **{mult:.2f}×** → **{payout:,}** coins "
                f"(net **+{payout - g.bet:,}**).\n"
                f"Balance: **{get_coins(g.guild_id, g.user_id):,}**"
            )
        elif attempts_used >= MAX_ATTEMPTS:
            g.ended = True
            for child in view.children:
                child.disabled = True
            code_str = "".join(str(d) for d in g.code)
            footer = (
                f"{random.choice(FAIL_FLAVOR)}\n"
                f"The code was **{code_str}**. Lost **{g.bet:,}** coins.\n"
                f"Balance: **{get_coins(g.guild_id, g.user_id):,}**"
            )
        else:
            view._refresh()
            footer = None

        await interaction.response.edit_message(content=view.cog._render(g, footer), view=view)


class VaultView(discord.ui.View):
    def __init__(self, cog, game: VaultGame):
        super().__init__(timeout=600)
        self.cog = cog
        self.game = game
        # 9 digits split across 2 rows (5 + 4) so action-row width caps don't break it.
        mid = (len(DIGITS) + 1) // 2
        for d in DIGITS[:mid]:
            self.add_item(DigitButton(d, row=0))
        for d in DIGITS[mid:]:
            self.add_item(DigitButton(d, row=1))
        self.undo = UndoButton()
        self.submit = SubmitButton()
        self.add_item(self.undo)
        self.add_item(self.submit)

    def _refresh(self):
        pass


class TheVaultHard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("The Vault (Hard) loaded.")

    def _render(self, g: VaultGame, footer: str | None = None) -> str:
        lines = [
            f"🏦💎 **{g.user_name}'s HARD-MODE Vault Heist** — bet **{g.bet:,}**",
            f"Crack a **{CODE_LENGTH}-digit code** using digits **1-9** (no repeats). **{MAX_ATTEMPTS - len(g.attempts)}** attempts left.",
            f"🟢 = right digit, right position | 🟡 = right digit, wrong position | ⚫ = not in code",
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
            lines.append(f"**Current guess:** `{' '.join(slots)}`")
            lines.append("")
            lines.append("**Payouts:** 1 try→50× | 2→25× | 3→12× | 4→6× | 5→3× | 6→1.5×")
            lines.append("*No bet cap. No payout cap. May the math be kind.*")
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
            await reply("Bet > 0 to crack the hard vault.")
            return
        if get_coins(guild.id, user.id) < bet:
            await reply(f"Too broke. Balance: **{get_coins(guild.id, user.id):,}**")
            return

        deduct_coins(guild.id, user.id, bet)
        game = VaultGame(guild.id, user.id, user.display_name, bet)
        view = VaultView(self, game)
        await reply(self._render(game), view=view)

    @commands.command(name="vault_hard", aliases=["vaulthard", "vh", "hardcrack"])
    @commands.guild_only()
    async def vault_hard_prefix(self, ctx, bet: int):
        await self._start(ctx, bet)

    @app_commands.command(name="vault_hard", description="Hard-mode vault: 5 digits from 1-9, 6 attempts. No bet cap.")
    @app_commands.describe(bet="Coins to risk (no cap — go nuts)")
    async def vault_hard_slash(self, interaction: discord.Interaction, bet: int):
        await self._start(interaction, bet)


async def setup(bot):
    await bot.add_cog(TheVaultHard(bot))
