"""Hire a lawyer to fight your jail sentence.

The paid cousin of /jailbreak. Jailbreak stakes your TIME (free, but
cooldown-gated and risks more time). Hiring a lawyer stakes your COINS: you
pay a non-refundable retainer to the house, then roll the dice on the verdict.

  WIN  → case dismissed, sentence cleared. The retainer is gone regardless.
  LOSE → you tested your fate against the casino gods and lost. Extra time is
         tacked onto your sentence, on top of the retainer you already burned.

The retainer is a PERCENTAGE of your wallet — a flat fee is pocket change to a
millionaire, so the house takes a cut proportional to what you're sitting on.
Four tiers trade money for odds. Even the dream team is shy of certain, because
the house owns the judge — the lone exception is the `freecard` tier, where your
lawyer plays a Get Out of Jail Free card at the hearing for a near-sure win.

State (cog_kv):
  namespace "lawyer"   per-user "until"          — attempt cooldown
  namespace "jailcard" per-user "last_use_date"  — one freecard play per day
Retainers route to the house on-hand (a closed loop, not burned).
"""
import discord
from discord.ext import commands
from discord import app_commands
import random
import time
import logging

from economy import (
    get_coins, jail_remaining, release_from_jail, adjust_jail_sentence,
    transfer_to_house, record_game, kv_get, kv_set, get_jail_info,
    item_qty, consume_item, grant_item, today_str,
)
from items import JAIL_CARD, display as item_display

logger = logging.getLogger(__name__)

# Spamming the court is its own kind of contempt. A retainer is a real cost, so
# this is shorter than the jailbreak throttle — just enough to stop re-rolling
# a fresh verdict every second.
COOLDOWN_SECONDS = 60
_CD_NS = "lawyer"

# One freecard play per calendar day, tracked here (shared concept with the shop).
_JAIL_CARD_NS = "jailcard"

# A retainer is never free even for a near-broke player.
MIN_FEE = 5_000

# Lawyer tiers: key -> (emoji, label, fee_pct, win_chance, loss_mult, needs_card).
#   fee_pct    — retainer = this share of the player's wallet (floored at MIN_FEE),
#                paid to the house win or lose.
#   win_chance — odds the case is dismissed. Capped under certainty: the house
#                owns the courthouse. The freecard tier is the exception — a real
#                Get Out of Jail Free card is hard to argue with.
#   loss_mult  — on a loss, extra sentence = remaining * loss_mult. Bigger bets
#                on yourself anger the casino gods more when they don't pay off.
#   needs_card — requires (and consumes) a Get Out of Jail Free card.
TIERS = {
    "public":   ("💼", "Public Defender",       0.03, 0.25, 0.40, False),
    "private":  ("🧑‍⚖️", "Private Attorney",      0.10, 0.45, 0.65, False),
    "hotshot":  ("🕴️", "Hotshot Defense Team",   0.25, 0.62, 1.00, False),
    "freecard": ("🃏", "Get Out of Jail Free Defense", 0.05, 0.98, 1.50, True),
}

_WIN_FLAVOR = [
    "Your lawyer finds a typo in the arrest paperwork and the whole case collapses.",
    "A surprise witness — your lawyer's cousin — swears you were at bingo all night.",
    "The prosecution forgot to file the right form. Case dismissed on a technicality.",
    "Your attorney quotes a statute nobody's heard of and the judge just... gives up.",
    "Three hours of objections later, the bailiff opens the cell. You're free.",
]
_CARD_WIN_FLAVOR = [
    "Your lawyer slides a **Get Out of Jail Free** card across the bench. The judge squints, shrugs, and signs.",
    "One look at that yellowing card and the prosecution packs up. Case closed.",
    "The card is technically not legal tender in any court. The judge honors it anyway.",
]
_LOSS_FLAVOR = [
    "The judge listens to your lawyer, sighs, and adds time out of sheer spite.",
    "Your attorney mispronounces the judge's name twice. It does not go well.",
    "The casino gods were watching. They were not impressed. Neither was the jury.",
    "Your lawyer's whole defense was 'my client is a vibe.' The gavel disagreed.",
    "Turns out the judge plays slots here. You never had a chance.",
]


class Lawyer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Lawyer module loaded.")

    @staticmethod
    def _fmt(seconds: int) -> str:
        seconds = max(0, int(seconds))
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h > 0:
            return f"{h}h {m}m"
        if m > 0:
            return f"{m}m {s}s"
        return f"{s}s"

    @staticmethod
    def _fee(wallet: int, fee_pct: float) -> int:
        return max(MIN_FEE, int(wallet * fee_pct))

    def _menu(self, wallet: int) -> str:
        lines = ["⚖️ **Pick your defense** — `lawyer <tier>` (retainer = a cut of your wallet, paid win or lose):"]
        for key, (emoji, label, fee_pct, win, _mult, needs_card) in TIERS.items():
            fee = self._fee(wallet, fee_pct)
            extra = " — needs a 🃏 Get Out of Jail Free card, one per day" if needs_card else ""
            lines.append(
                f"{emoji} **`{key}`** — {label}: **{int(fee_pct * 100)}%** of wallet "
                f"(~**{fee:,}** for you), ~**{int(win * 100)}%** to walk{extra}."
            )
        lines.append("_Lose and you serve extra time on top — bigger bets, bigger backfire._")
        return "\n".join(lines)

    async def _start(self, ctx_or_interaction, tier: str | None):
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

        remaining = jail_remaining(guild.id, user.id)
        if remaining <= 0:
            await reply("🔓 You're not in jail. No case to fight — go gamble.")
            return

        # Repeat tax-evasion holds are card-proof and break-proof — no lawyer,
        # no card touches them. Checked before anything is consumed or charged.
        info = get_jail_info(guild.id, user.id)
        if info and info.get("no_release"):
            await reply(
                "🔒 This is a **tax-evasion** hold. No lawyer, no bribe, no card. "
                "Even the casino gods won't hear an appeal. Serve every second."
            )
            return

        wallet = get_coins(guild.id, user.id)
        key = (tier or "").strip().lower()
        if key not in TIERS:
            await reply(self._menu(wallet))
            return

        emoji, label, fee_pct, win_chance, loss_mult, needs_card = TIERS[key]

        # Attempt cooldown (shared across all tiers).
        now = time.time()
        until = kv_get(guild.id, user.id, _CD_NS, "until", 0) or 0
        wait = int(until - now)
        if wait > 0:
            await reply(
                f"🧑‍⚖️ The court's still in recess from your last hearing. "
                f"Try again in **{self._fmt(wait)}**."
            )
            return

        # Freecard prerequisites: once per calendar day, and you must own a card.
        if needs_card:
            if kv_get(guild.id, user.id, _JAIL_CARD_NS, "last_use_date", "") == today_str():
                await reply(
                    "🃏 You've already played a **Get Out of Jail Free** card today. "
                    "One per calendar day — hire a different lawyer or sit tight."
                )
                return
            if item_qty(guild.id, user.id, JAIL_CARD) < 1:
                await reply(
                    f"🃏 You don't own a {item_display(JAIL_CARD)} card to play. "
                    f"Grab one from `/shop`, or hire a `public`/`private`/`hotshot` lawyer instead."
                )
                return

        fee = self._fee(wallet, fee_pct)
        if wallet < fee:
            await reply(
                f"💸 {emoji} A **{label}** wants **{fee:,}** coins up front "
                f"({int(fee_pct * 100)}% of your wallet). You've got **{wallet:,}**. "
                f"Make some money first."
            )
            return

        # Commit: lock cooldown, consume the card (freecard), collect the retainer.
        kv_set(guild.id, user.id, _CD_NS, "until", now + COOLDOWN_SECONDS)
        if needs_card and not consume_item(guild.id, user.id, JAIL_CARD):
            await reply(f"You don't own a {item_display(JAIL_CARD)} card.")
            return
        paid = transfer_to_house(guild.id, user.id, fee, is_bet=False)
        if not paid.get("ok"):
            if needs_card:
                grant_item(guild.id, user.id, JAIL_CARD)  # un-charge the card
            await reply("Retainer payment failed. Try again.")
            return
        if needs_card:
            kv_set(guild.id, user.id, _JAIL_CARD_NS, "last_use_date", today_str())

        won = random.random() < win_chance
        record_game(guild.id, user.id, "lawyer", won)

        if won:
            release_from_jail(guild.id, user.id)
            flavor = random.choice(_CARD_WIN_FLAVOR if needs_card else _WIN_FLAVOR)
            result = "🟢 **CASE DISMISSED.** You walk free."
        else:
            extra = max(600, int(remaining * loss_mult))
            res = adjust_jail_sentence(guild.id, user.id, extra)
            flavor = random.choice(_LOSS_FLAVOR)
            card_note = " Your card was torn up in the process." if needs_card else ""
            result = (
                f"🔴 **GUILTY — and then some.** **+{self._fmt(extra)}** added.{card_note} "
                f"**{self._fmt(res.get('remaining', remaining + extra))}** left to serve."
            )

        text = (
            f"⚖️ **{user.display_name} lawyers up — {emoji} {label}** "
            f"(**{fee:,}** coin retainer)\n\n"
            f"_{flavor}_\n\n"
            f"{result}"
        )
        await reply(text)

    @commands.command(name="lawyer", aliases=["attorney", "hirelawyer"])
    @commands.guild_only()
    async def lawyer_prefix(self, ctx, tier: str | None = None):
        await self._start(ctx, tier)

    @app_commands.command(name="lawyer", description="Hire a lawyer to fight your jail sentence — pay a cut of your wallet to roll the verdict.")
    @app_commands.describe(tier="Which defense to hire — pricier means better (but never certain) odds.")
    @app_commands.choices(tier=[
        app_commands.Choice(name="Public Defender — 3% of wallet, ~25%", value="public"),
        app_commands.Choice(name="Private Attorney — 10% of wallet, ~45%", value="private"),
        app_commands.Choice(name="Hotshot Defense Team — 25% of wallet, ~62%", value="hotshot"),
        app_commands.Choice(name="Play Get Out of Jail Free card — 5% of wallet, ~98%", value="freecard"),
    ])
    async def lawyer_slash(self, interaction: discord.Interaction, tier: app_commands.Choice[str]):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        await self._start(interaction, tier.value)


async def setup(bot):
    await bot.add_cog(Lawyer(bot))
