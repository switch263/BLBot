import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

from economy import get_coins, jail_message, record_vault, transfer_to_house, casino_payout

logger = logging.getLogger(__name__)

CODE_LENGTH = 4
DIGITS = [1, 2, 3, 4, 5, 6]
MAX_ATTEMPTS = 5
MAX_BET = 1_000_000
MAX_PAYOUT = 10_000_000

# Payout by attempts used (1-indexed). Attempts=1 means cracked on first guess (pure luck).
PAYOUT_BY_ATTEMPT = {
    1: 15.0,
    2: 7.0,
    3: 3.5,
    4: 2.0,
    5: 1.25,
}

SOLVE_FLAVOR = [
    "🔓 **The vault hisses open.**",
    "🔓 **Click. Click. Click. Click. THUNK.** Open.",
    "🔓 **The tumblers align like the planets.**",
    "🔓 **An ominous green light. The door swings wide.**",
]

FAIL_FLAVOR = [
    "🚨 **FIVE STRIKES.** Thermite seals the vault. You flee with nothing.",
    "🚨 **Biometric lock engages.** The code is burned. Lose bet.",
    "🚨 **Security drones dispatched.** The vault laughs in binary.",
    "🚨 **The vault changes its code every 5 attempts.** You are now locked out forever.",
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
            raw_payout = int(g.bet * mult)
            requested = min(raw_payout, MAX_PAYOUT)
            capped = requested < raw_payout
            paid = casino_payout(g.guild_id, g.user_id, requested)
            record_vault(g.guild_id, g.user_id, won=True)
            for child in view.children:
                child.disabled = True
            cap_note = f" *(capped at {MAX_PAYOUT:,})*" if capped else ""
            short_note = f" *(house was short — owed {requested:,})*" if paid < requested else ""
            footer = (
                f"{random.choice(SOLVE_FLAVOR)}\n"
                f"Cracked in **{attempts_used}** attempt(s). Payout: **{mult:.2f}×** → **{paid:,}** coins{cap_note}{short_note} "
                f"(net **{paid - g.bet:+,}**).\n"
                f"Balance: **{get_coins(g.guild_id, g.user_id):,}**"
            )
        elif attempts_used >= MAX_ATTEMPTS:
            g.ended = True
            record_vault(g.guild_id, g.user_id, won=False)
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
        super().__init__(timeout=300)
        self.cog = cog
        self.game = game
        # Discord caps action rows at 5 buttons each; with 6 digits we split 3+3.
        half = len(DIGITS) // 2
        for d in DIGITS[:half]:
            self.add_item(DigitButton(d, row=0))
        for d in DIGITS[half:]:
            self.add_item(DigitButton(d, row=1))
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
            lines.append(f"**Payouts:** 1 try→15× | 2→7× | 3→3.5× | 4→2× | 5→1.25× *(max payout {MAX_PAYOUT:,})*")
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
        if bet > MAX_BET:
            await reply(f"Max bet is **{MAX_BET:,}** coins. Payouts cap at **{MAX_PAYOUT:,}**.")
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

    @commands.command(name="vault", aliases=["crack", "safecrack"])
    @commands.guild_only()
    async def vault_prefix(self, ctx, bet: int):
        await self._start(ctx, bet)

    @app_commands.command(name="vault", description="Crack a 4-digit vault using Mastermind-style deduction. 5 attempts.")
    @app_commands.describe(bet=f"Coins to risk (max {MAX_BET:,})")
    async def vault_slash(self, interaction: discord.Interaction, bet: int):
        await self._start(interaction, bet)


async def setup(bot):
    await bot.add_cog(TheVault(bot))
