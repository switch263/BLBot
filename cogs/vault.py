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

CODE_LENGTH = 4
DIGITS = [1, 2, 3, 4, 5, 6]
MAX_ATTEMPTS = 6

# Payout by attempts used (1-indexed). Attempts=1 means cracked on first guess (pure luck).
PAYOUT_BY_ATTEMPT = {
    1: 25.0,
    2: 15.0,
    3: 9.0,
    4: 5.0,
    5: 3.0,
    6: 2.0,
}

SOLVE_FLAVOR = [
    "🔓 **The vault hisses open.**",
    "🔓 **Click. Click. Click. Click. THUNK.** Open.",
    "🔓 **The tumblers align like the planets.**",
    "🔓 **An ominous green light. The door swings wide.**",
]

FAIL_FLAVOR = [
    "🚨 **SIX STRIKES.** Thermite seals the vault. You flee with nothing.",
    "🚨 **Biometric lock engages.** The code is burned. Lose bet.",
    "🚨 **Security drones dispatched.** The vault laughs in binary.",
    "🚨 **The vault changes its code every 6 attempts.** You are now locked out forever.",
]


class VaultGame:
    def __init__(self, guild_id, user_id, user_name, bet):
        self.guild_id = guild_id
        self.user_id = user_id
        self.user_name = user_name
        self.bet = bet
        # Code is 4 unique digits from 1-6
        self.code = random.sample(DIGITS, CODE_LENGTH)
        self.attempts: list[tuple[list[int], str]] = []  # (guess, feedback_emoji_string)
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
    def __init__(self, digit: int):
        super().__init__(style=discord.ButtonStyle.secondary, label=str(digit), row=0)
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
        super().__init__(style=discord.ButtonStyle.secondary, label="Undo", emoji="↩️", row=1)

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
        super().__init__(style=discord.ButtonStyle.success, label="Submit", emoji="🔒", row=1)

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
                f"Cracked in **{attempts_used}** attempt(s). Payout: **{mult:.2f}×** → **{payout}** coins "
                f"(net **+{payout - g.bet}**).\n"
                f"Balance: **{get_coins(g.guild_id, g.user_id)}**"
            )
        elif attempts_used >= MAX_ATTEMPTS:
            g.ended = True
            for child in view.children:
                child.disabled = True
            code_str = "".join(str(d) for d in g.code)
            footer = (
                f"{random.choice(FAIL_FLAVOR)}\n"
                f"The code was **{code_str}**. Lost **{g.bet}** coins.\n"
                f"Balance: **{get_coins(g.guild_id, g.user_id)}**"
            )
        else:
            view._refresh()
            footer = None

        await interaction.response.edit_message(content=view.cog._render(g, footer), view=view)


class VaultView(discord.ui.View):
    def __init__(self, cog, game: VaultGame):
        super().__init__(timeout=300)
        self.cog = cog
        self.game = game
        for d in DIGITS:
            self.add_item(DigitButton(d))
        self.undo = UndoButton()
        self.submit = SubmitButton()
        self.add_item(self.undo)
        self.add_item(self.submit)

    def _refresh(self):
        # Nothing dynamic on buttons themselves, but we could update labels here if needed.
        pass


class TheVault(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("The Vault loaded.")

    def _render(self, g: VaultGame, footer: str | None = None) -> str:
        lines = [
            f"🏦 **{g.user_name}'s Vault Heist** — bet **{g.bet}**",
            f"Crack a **{CODE_LENGTH}-digit code** using digits **1-6** (no repeats). **{MAX_ATTEMPTS - len(g.attempts)}** attempts left.",
            f"🟢 = right digit, right position | 🟡 = right digit, wrong position | ⚫ = not in code",
            "",
        ]
        if g.attempts:
            lines.append("**Attempts:**")
            for i, (guess, fb) in enumerate(g.attempts, 1):
                digits = " ".join(str(d) for d in guess)
                lines.append(f"`{i}.` **{digits}** → {fb}")
        # Current guess row
        if not g.ended:
            slots = [str(d) for d in g.current] + ["_"] * (CODE_LENGTH - len(g.current))
            lines.append("")
            lines.append(f"**Current guess:** `{' '.join(slots)}`")
            lines.append("")
            lines.append("**Payouts:** 1 try→25× | 2→15× | 3→9× | 4→5× | 5→3× | 6→2×")
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
            await reply("Bet > 0 to crack the vault.")
            return
        if get_coins(guild.id, user.id) < bet:
            await reply(f"Too broke. Balance: **{get_coins(guild.id, user.id)}**")
            return

        deduct_coins(guild.id, user.id, bet)
        game = VaultGame(guild.id, user.id, user.display_name, bet)
        view = VaultView(self, game)
        await reply(self._render(game), view=view)

    @commands.command(name="vault", aliases=["crack", "safecrack"])
    @commands.guild_only()
    async def vault_prefix(self, ctx, bet: int):
        await self._start(ctx, bet)

    @app_commands.command(name="vault", description="Crack a 4-digit vault using Mastermind-style deduction. 6 attempts.")
    @app_commands.describe(bet="Coins to risk")
    async def vault_slash(self, interaction: discord.Interaction, bet: int):
        await self._start(interaction, bet)


async def setup(bot):
    await bot.add_cog(TheVault(bot))
