"""The Vault — one game, three difficulties, one /vault command.

Consolidates the old vault / vault_hard / vault_extra_hard cogs:
  normal — 4-digit code, digits 1-6, no repeats, per-position hints,
           payouts 15×…1.25×, payout capped at 10M.
  hard   — 5-digit code, digits 1-9, no repeats, per-position hints,
           payouts 75×…0.5× (limp to the last try and you LOSE half).
  extra  — 3-wheel suitcase lock, wheels 0-3, repeats ALLOWED, and hints
           are counts only (Bulls-and-Cows), payouts 50×…1×.

Per-difficulty stats keep their original game names (vault / vault_hard /
vault_extra_hard) so leaderboards and history carry over. Prefix commands
!vault_hard and !vault_extra_hard survive as aliases into their difficulty;
the slash surface is a single /vault with a difficulty option.
"""
import discord
from discord.ext import commands
from discord import app_commands
import random
import logging
from collections import Counter

from economy import (
    get_coins, jail_message, record_game, transfer_to_house, casino_payout,
    MAX_BET,
)
from amount import parse_amount, amount_error

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5

DIFFICULTIES: dict[str, dict] = {
    "normal": {
        "title": "Vault Heist",
        "thing": "vault",
        "code_length": 4,
        "digits": [1, 2, 3, 4, 5, 6],
        "repeats": False,
        "counts_only": False,
        "payouts": {1: 15.0, 2: 7.0, 3: 3.5, 4: 2.0, 5: 1.25},
        "max_payout": 10_000_000,
        "timeout": 300,
        "game": "vault",
        "rules": "Crack a **4-digit code** using digits **1-6** (no repeats).",
        "legend": "🟢 = right digit, right position | 🟡 = right digit, wrong position | ⚫ = not in code",
        "solve_flavor": [
            "🔓 **The vault hisses open.**",
            "🔓 **Click. Click. Click. Click. THUNK.** Open.",
            "🔓 **The tumblers align like the planets.**",
            "🔓 **An ominous green light. The door swings wide.**",
        ],
        "fail_flavor": [
            "🚨 **FIVE STRIKES.** Thermite seals the vault. You flee with nothing.",
            "🚨 **Biometric lock engages.** The code is burned. Lose bet.",
            "🚨 **Security drones dispatched.** The vault laughs in binary.",
            "🚨 **The vault changes its code every 5 attempts.** You are now locked out forever.",
        ],
    },
    "hard": {
        "title": "Hard Vault",
        "thing": "vault",
        "code_length": 5,
        "digits": [1, 2, 3, 4, 5, 6, 7, 8, 9],
        "repeats": False,
        "counts_only": False,
        # 5 unique digits from 1-9 = 15,120 possibilities in 5 tries.
        "payouts": {1: 75.0, 2: 30.0, 3: 8.0, 4: 2.0, 5: 0.5},
        "max_payout": None,
        "timeout": 600,
        "game": "vault_hard",
        "rules": "Crack a **5-digit code** using digits **1-9** (no repeats).",
        "legend": "🟢 = right digit, right position | 🟡 = right digit, wrong position | ⚫ = not in code",
        "solve_flavor": [
            "🔓 **The reinforced vault hisses open.**",
            "🔓 **Tumblers scream. Plate shifts. THUNK.**",
            "🔓 **The vault concedes. You've outsmarted the algorithm.**",
            "🔓 **An ominous green light. The 12-inch door swings wide.**",
            "🔓 **Even the security guard is impressed.**",
        ],
        "fail_flavor": [
            "🚨 **THREE STRIKES.** Magnesium thermite welds the vault shut.",
            "🚨 **Iris scanners, ankle monitors, drone strike. The house collects.**",
            "🚨 **The vault's neural net laughs. Code burned. The house pockets your bet.**",
            "🚨 **Lockdown. The walls slide in. The house takes everything.**",
        ],
    },
    "extra": {
        "title": "Suitcase Lock",
        "thing": "suitcase",
        "code_length": 3,
        "digits": [0, 1, 2, 3],
        "repeats": True,
        "counts_only": True,
        # 4^3 = 64 combos, counts-only hints: pure Bulls-and-Cows deduction.
        "payouts": {1: 50.0, 2: 15.0, 3: 5.0, 4: 2.0, 5: 1.0},
        "max_payout": None,
        "timeout": 600,
        "game": "vault_extra_hard",
        "rules": ("Crack a **3-wheel suitcase lock**, wheels **0-3** — the same "
                  "number **can repeat**. Hints are **counts only**, not positions."),
        "legend": "🟢 = right number, right wheel | 🟡 = right number, wrong wheel | ⚫ = matches nothing",
        "solve_flavor": [
            "🔓 **The suitcase clicks open.** Inside: everything.",
            "🔓 **Three wheels align. The latches pop.**",
            "🔓 **The lock surrenders. Deduction beats luck.**",
        ],
        "fail_flavor": [
            "🚨 **The suitcase self-destructs.** The house sweeps up the coins.",
            "🚨 **Wrong again. The lock fuses solid. The house collects.**",
            "🚨 **A dye pack explodes.** Your bet is house property now.",
        ],
    },
}

PREFIX_DIFFICULTY_ALIASES = {
    "normal": "normal", "easy": "normal",
    "hard": "hard",
    "extra": "extra", "extrahard": "extra", "extra_hard": "extra",
    "suitcase": "extra",
}


def score(guess: list[int], code: list[int]) -> tuple[int, int, int]:
    """Repeat-aware Mastermind / Bulls-and-Cows scoring.
    Returns (exact, misplaced, absent). Correct for unique-digit codes too."""
    exact = sum(1 for g, c in zip(guess, code) if g == c)
    gc, cc = Counter(guess), Counter(code)
    total_match = sum(min(gc[d], cc[d]) for d in gc)
    return exact, total_match - exact, len(guess) - total_match


class VaultGame:
    def __init__(self, guild_id, user_id, user_name, bet, cfg: dict):
        self.guild_id = guild_id
        self.user_id = user_id
        self.user_name = user_name
        self.bet = bet
        self.cfg = cfg
        if cfg["repeats"]:
            self.code = [random.choice(cfg["digits"]) for _ in range(cfg["code_length"])]
        else:
            self.code = random.sample(cfg["digits"], cfg["code_length"])
        self.attempts: list[tuple[list[int], str]] = []  # (guess, feedback string)
        self.current: list[int] = []
        self.ended = False

    def feedback_for(self, guess: list[int]) -> tuple[str, bool]:
        exact, misplaced, absent = score(guess, self.code)
        solved = exact == self.cfg["code_length"]
        if self.cfg["counts_only"]:
            return f"🟢×{exact}  🟡×{misplaced}  ⚫×{absent}", solved
        parts = []
        for i, d in enumerate(guess):
            if d == self.code[i]:
                parts.append("🟢")
            elif d in self.code:
                parts.append("🟡")
            else:
                parts.append("⚫")
        return "".join(parts), solved


class DigitButton(discord.ui.Button):
    def __init__(self, digit: int, row: int):
        super().__init__(style=discord.ButtonStyle.secondary, label=str(digit), row=row)
        self.digit = digit

    async def callback(self, interaction: discord.Interaction):
        view: "VaultView" = self.view  # type: ignore
        g = view.game
        cfg = g.cfg
        if interaction.user.id != g.user_id:
            await interaction.response.send_message(f"Not your {cfg['thing']}.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return
        if len(g.current) >= cfg["code_length"]:
            await interaction.response.send_message("Guess is full — submit or undo.", ephemeral=True)
            return
        if not cfg["repeats"] and self.digit in g.current:
            await interaction.response.send_message("No repeated digits — the real code has none.", ephemeral=True)
            return
        g.current.append(self.digit)
        await interaction.response.edit_message(content=view.cog._render(g), view=view)


class UndoButton(discord.ui.Button):
    def __init__(self, row: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="Undo", emoji="↩️", row=row)

    async def callback(self, interaction: discord.Interaction):
        view: "VaultView" = self.view  # type: ignore
        g = view.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message(f"Not your {g.cfg['thing']}.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return
        if g.current:
            g.current.pop()
        await interaction.response.edit_message(content=view.cog._render(g), view=view)


class SubmitButton(discord.ui.Button):
    def __init__(self, row: int):
        super().__init__(style=discord.ButtonStyle.success, label="Submit", emoji="🔒", row=row)

    async def callback(self, interaction: discord.Interaction):
        view: "VaultView" = self.view  # type: ignore
        g = view.game
        cfg = g.cfg
        if interaction.user.id != g.user_id:
            await interaction.response.send_message(f"Not your {cfg['thing']}.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return
        if len(g.current) != cfg["code_length"]:
            await interaction.response.send_message(f"Need {cfg['code_length']} digits.", ephemeral=True)
            return
        feedback, solved = g.feedback_for(g.current)
        g.attempts.append((list(g.current), feedback))
        attempts_used = len(g.attempts)
        g.current = []

        if solved:
            g.ended = True
            mult = cfg["payouts"].get(attempts_used, cfg["payouts"][MAX_ATTEMPTS])
            raw_payout = int(g.bet * mult)
            cap = cfg["max_payout"]
            requested = min(raw_payout, cap) if cap else raw_payout
            paid = casino_payout(g.guild_id, g.user_id, requested)
            record_game(g.guild_id, g.user_id, cfg["game"], won=True)
            for child in view.children:
                child.disabled = True
            cap_note = f" *(capped at {cap:,})*" if cap and requested < raw_payout else ""
            short_note = f" *(house was short — owed {requested:,})*" if paid < requested else ""
            footer = (
                f"{random.choice(cfg['solve_flavor'])}\n"
                f"Cracked in **{attempts_used}** attempt(s). Payout: **{mult:.2f}×** → **{paid:,}** coins{cap_note}{short_note} "
                f"(net **{paid - g.bet:+,}**).\n"
                f"Balance: **{get_coins(g.guild_id, g.user_id):,}**"
            )
        elif attempts_used >= MAX_ATTEMPTS:
            g.ended = True
            # Bet already went to the house at game start; nothing more to move.
            record_game(g.guild_id, g.user_id, cfg["game"], won=False)
            for child in view.children:
                child.disabled = True
            code_str = "".join(str(d) for d in g.code)
            footer = (
                f"{random.choice(cfg['fail_flavor'])}\n"
                f"The code was **{code_str}**. **{g.bet:,}** coins transferred to the house.\n"
                f"Balance: **{get_coins(g.guild_id, g.user_id):,}**"
            )
        else:
            footer = None

        await interaction.response.edit_message(content=view.cog._render(g, footer), view=view)


class VaultView(discord.ui.View):
    def __init__(self, cog, game: VaultGame):
        super().__init__(timeout=game.cfg["timeout"])
        self.cog = cog
        self.game = game
        # Digit buttons fill rows 0-1 (Discord caps a row at 5 buttons);
        # controls live on the next free row.
        digits = game.cfg["digits"]
        rows = 1 if len(digits) <= 5 else 2
        per_row = (len(digits) + rows - 1) // rows
        for i, d in enumerate(digits):
            self.add_item(DigitButton(d, row=i // per_row))
        control_row = rows
        self.add_item(UndoButton(row=control_row))
        self.add_item(SubmitButton(row=control_row))


class TheVault(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("The Vault loaded (difficulties: %s).", ", ".join(DIFFICULTIES))

    def _render(self, g: VaultGame, footer: str | None = None) -> str:
        cfg = g.cfg
        lines = [
            f"🏦 **{g.user_name}'s {cfg['title']}** — bet **{g.bet:,}**",
            f"{cfg['rules']} **{MAX_ATTEMPTS - len(g.attempts)}** attempts left.",
            cfg["legend"],
            "",
        ]
        if g.attempts:
            lines.append("**Attempts:**")
            for i, (guess, fb) in enumerate(g.attempts, 1):
                digits = " ".join(str(d) for d in guess)
                lines.append(f"`{i}.` **{digits}** → {fb}")
        if not g.ended:
            slots = [str(d) for d in g.current] + ["_"] * (cfg["code_length"] - len(g.current))
            payline = " | ".join(f"{n}→{m:g}×" for n, m in sorted(cfg["payouts"].items()))
            cap = cfg["max_payout"]
            cap_note = f" *(max payout {cap:,})*" if cap else ""
            lines += [
                "",
                f"**Current guess:** `{' '.join(slots)}`",
                "",
                f"**Payouts by attempt:** {payline}{cap_note}",
            ]
        if footer:
            lines += ["", footer]
        return "\n".join(lines)

    async def _start(self, ctx_or_interaction, bet, difficulty: str):
        cfg = DIFFICULTIES[difficulty]
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
        amt = parse_amount(bet)
        if amt is None:
            await reply(amount_error(bet))
            return
        bet = amt
        jmsg = jail_message(guild.id, user.id)
        if jmsg:
            await reply(jmsg)
            return
        if bet <= 0:
            await reply(f"Bet > 0 to crack the {cfg['thing']}.")
            return
        if bet > MAX_BET:
            await reply(f"Easy, high roller — max bet is **{MAX_BET:,}** coins.")
            return
        bet_result = transfer_to_house(guild.id, user.id, bet)
        if not bet_result.get("ok"):
            if bet_result.get("error") == "broke":
                await reply(f"Too broke. Balance: **{bet_result.get('have', 0):,}**")
            else:
                await reply("Bet failed. Try again.")
            return
        game = VaultGame(guild.id, user.id, user.display_name, bet, cfg)
        view = VaultView(self, game)
        await reply(self._render(game), view=view)

    # ---- prefix: !vault <bet> [difficulty], plus legacy aliases ------------

    @commands.command(name="vault", aliases=["crack", "safecrack"])
    @commands.guild_only()
    async def vault_prefix(self, ctx, bet: str, difficulty: str = "normal"):
        """Crack the vault: !vault <bet> [normal|hard|extra]"""
        diff = PREFIX_DIFFICULTY_ALIASES.get(difficulty.lower())
        if diff is None:
            await ctx.send("Difficulty is `normal`, `hard`, or `extra`.")
            return
        await self._start(ctx, bet, diff)

    @commands.command(name="vault_hard", aliases=["vaulthard", "vh", "hardcrack"])
    @commands.guild_only()
    async def vault_hard_prefix(self, ctx, bet: str):
        """Legacy alias for !vault <bet> hard"""
        await self._start(ctx, bet, "hard")

    @commands.command(name="vault_extra_hard",
                      aliases=["vaultextrahard", "veh", "suitcase", "briefcase"])
    @commands.guild_only()
    async def vault_extra_hard_prefix(self, ctx, bet: str):
        """Legacy alias for !vault <bet> extra"""
        await self._start(ctx, bet, "extra")

    # ---- slash: one /vault with a difficulty option ------------------------

    @app_commands.command(
        name="vault",
        description="Crack a code Mastermind-style. Pick your difficulty — harder locks, fatter multipliers.",
    )
    @app_commands.describe(
        bet=f"Coins to risk (max {MAX_BET:,}) — supports 1k, 5m, 100,000",
        difficulty="normal: 4 digits 1-6 · hard: 5 digits 1-9 · extra: suitcase lock, counts-only hints",
    )
    @app_commands.choices(difficulty=[
        app_commands.Choice(name="normal — 4 digits (1-6), up to 15×, payout capped", value="normal"),
        app_commands.Choice(name="hard — 5 digits (1-9), up to 75×, last-try pays 0.5×", value="hard"),
        app_commands.Choice(name="extra — suitcase lock, counts-only hints, up to 50×", value="extra"),
    ])
    async def vault_slash(self, interaction: discord.Interaction, bet: str,
                          difficulty: app_commands.Choice[str] = None):
        await self._start(interaction, bet, difficulty.value if difficulty else "normal")


async def setup(bot):
    await bot.add_cog(TheVault(bot))
