"""Bounty cog — pay a lot of coins for a *chance* to throw someone in casino jail.

Bet is always paid to the house. On success the target is jailed for a random 1-36h.
On failure the placer eats their own random 1-36h sentence. Releases (and bail/extend
buttons on resulting jails) are handled by the Heist cog's existing infrastructure."""

import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

import economy

logger = logging.getLogger(__name__)

# Minimum bounty bet. Big number — this is a high-roller feature.
MIN_BOUNTY = 100_000_000

# Success chance scales linearly with bet, from MIN_RATE at MIN_BOUNTY up to MAX_RATE
# at SATURATION_BOUNTY (and clamps at MAX_RATE for any bet above that).
MIN_RATE = 0.25
MAX_RATE = 0.60
SATURATION_BOUNTY = 1_000_000_000  # 1B saturates the curve

# Jail duration when the bounty lands (or when it backfires on the placer).
BOUNTY_JAIL_MIN_SECONDS = 1 * 60 * 60
BOUNTY_JAIL_MAX_SECONDS = 36 * 60 * 60

# Rate limits — both apply; both must pass.
# Guild-wide: 2 bounties per rolling 7-day window.
BOUNTY_GUILD_LIMIT = 2
BOUNTY_GUILD_WINDOW_SECONDS = 7 * 24 * 60 * 60
# Per user: 1 bounty per rolling 30-day window.
BOUNTY_USER_LIMIT = 1
BOUNTY_USER_WINDOW_SECONDS = 30 * 24 * 60 * 60


SUCCESS_FLAVOR = [
    "💥 **{placer}** put up **{bet:,} coins** and it landed — **{target}** is dragged to casino jail for **{hours} hours**.",
    "💥 **{placer}**'s bounty went through. Two goons in suits scooped up **{target}**. **{hours}h** in the hole.",
    "💥 Money talks. **{target}** is now wearing casino-jail orange courtesy of **{placer}**'s **{bet:,}-coin** contract. **{hours}h**.",
    "💥 The bounty board flashes green. **{placer}** paid **{bet:,}**, **{target}** pays **{hours}h** of their freedom.",
    "💥 Hit confirmed. **{target}** never saw it coming. **{placer}** — your **{bet:,}** coins bought **{hours} hours** of peace.",
]

FAIL_FLAVOR = [
    "🪤 **{placer}**'s **{bet:,}-coin** bounty on **{target}** flopped — and the contract bounced back. **{placer}** is now in jail for **{hours}h**.",
    "🪤 The hit went sideways. **{target}** walked. The cops grabbed **{placer}** instead. **{hours}h** in the cooler.",
    "🪤 **{placer}** paid **{bet:,} coins** to a 'professional.' The professional turned them in. **{hours}h** of jail.",
    "🪤 Bounty botched. **{target}** is fine. **{placer}** is now staring at a cell ceiling for **{hours} hours**.",
    "🪤 The casino doesn't appreciate amateur hits. **{placer}** keeps the cell warm for **{hours}h**.",
]

ALREADY_JAILED_FLAVOR = [
    "💥 **{placer}**'s **{bet:,}-coin** bounty connected — but **{target}** is already locked up longer than **{hours}h**. The coins are gone; the sentence stays put.",
    "💥 The hit landed, but **{target}** was already serving a longer stretch. **{placer}**'s **{bet:,} coins** went to the house for nothing extra.",
]


def _success_rate(bet: int) -> float:
    if bet <= MIN_BOUNTY:
        return MIN_RATE
    if bet >= SATURATION_BOUNTY:
        return MAX_RATE
    span = SATURATION_BOUNTY - MIN_BOUNTY
    frac = (bet - MIN_BOUNTY) / span
    return MIN_RATE + frac * (MAX_RATE - MIN_RATE)


def _roll_jail_seconds() -> int:
    return random.randint(BOUNTY_JAIL_MIN_SECONDS, BOUNTY_JAIL_MAX_SECONDS)


class Bounty(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Bounty module has been loaded")

    async def _run_bounty(self, guild: discord.Guild, channel_id: int,
                          placer: discord.Member, target: discord.Member, bet: int) -> str:
        if target is None:
            return (
                f"Usage: `!bounty @user <bet>` — put a contract on someone. Minimum bet **{MIN_BOUNTY:,} coins**. "
                f"Success chance scales with bet ({int(MIN_RATE*100)}% at the minimum, up to {int(MAX_RATE*100)}% at {SATURATION_BOUNTY:,}). "
                f"Limits: **once per 30 days per person**, **{BOUNTY_GUILD_LIMIT} per 7 days guild-wide**. "
                f"**If the bounty fails, you go to jail.**"
            )
        if target.bot:
            return "You can't bounty a bot. The house doesn't take contracts on itself."
        if target.id == placer.id:
            return "🚫 You can't bounty yourself. That's just paying to go to jail."
        if bet is None or bet < MIN_BOUNTY:
            return f"💼 Minimum bounty is **{MIN_BOUNTY:,} coins**. You offered **{(bet or 0):,}**."

        # Jail gate: a jailed placer can't put out a hit
        jmsg = economy.jail_message(guild.id, placer.id)
        if jmsg:
            return jmsg
        # If the target is already jailed, bounty money would still be lost.
        # That's allowed — but warn-by-flavor, not refusal.

        success = random.random() < _success_rate(bet)

        if success:
            jail_seconds = _roll_jail_seconds()
            result = economy.place_jail_bounty(
                guild.id, placer.id, target.id,
                bet=bet, success=True, jail_seconds=jail_seconds,
                channel_id=channel_id, reason=f"Bounty placed by {placer.display_name}",
                guild_limit=BOUNTY_GUILD_LIMIT, guild_window_seconds=BOUNTY_GUILD_WINDOW_SECONDS,
                user_limit=BOUNTY_USER_LIMIT, user_window_seconds=BOUNTY_USER_WINDOW_SECONDS,
            )
            if not result["ok"]:
                return self._format_economy_error(result, bet)
            hours = max(1, round(jail_seconds / 3600))
            if result.get("jailed_longer"):
                return random.choice(ALREADY_JAILED_FLAVOR).format(
                    placer=placer.mention, target=target.mention, bet=bet, hours=hours,
                )
            return random.choice(SUCCESS_FLAVOR).format(
                placer=placer.mention, target=target.mention, bet=bet, hours=hours,
            )

        # Failure path: bet still gets paid to the house, AND the placer is jailed.
        result = economy.place_jail_bounty(
            guild.id, placer.id, target.id,
            bet=bet, success=False, jail_seconds=0,
            channel_id=channel_id, reason="",
            guild_limit=BOUNTY_GUILD_LIMIT, guild_window_seconds=BOUNTY_GUILD_WINDOW_SECONDS,
            user_limit=BOUNTY_USER_LIMIT, user_window_seconds=BOUNTY_USER_WINDOW_SECONDS,
        )
        if not result["ok"]:
            return self._format_economy_error(result, bet)
        backfire_seconds = _roll_jail_seconds()
        economy.jail_user(
            guild.id, placer.id, backfire_seconds,
            reason=f"Botched bounty on {target.display_name}",
            bail_amount=0,  # no bail-out — they shouldn't have hired an idiot
            channel_id=channel_id,
        )
        hours = max(1, round(backfire_seconds / 3600))
        return random.choice(FAIL_FLAVOR).format(
            placer=placer.mention, target=target.mention, bet=bet, hours=hours,
        )

    def _format_wait(self, seconds: int) -> str:
        d, rem = divmod(max(0, seconds), 86400)
        h, rem = divmod(rem, 3600)
        m, _s = divmod(rem, 60)
        parts = []
        if d:
            parts.append(f"{d}d")
        if h:
            parts.append(f"{h}h")
        if not d:
            parts.append(f"{m}m")
        return " ".join(parts)

    def _format_economy_error(self, result: dict, bet: int) -> str:
        err = result.get("error")
        if err == "broke":
            return f"💸 You'd need **{result.get('need', bet):,} coins** to put up that bounty. You have **{result.get('have', 0):,}**."
        if err == "self":
            return "🚫 You can't bounty yourself."
        if err == "invalid_bet":
            return f"💼 Minimum bounty is **{MIN_BOUNTY:,} coins**."
        if err == "rate_limited_user":
            wait = self._format_wait(result.get("seconds_until_slot", 0))
            return (
                f"🛑 You've already used your **monthly bounty**. "
                f"You can place another in **{wait}**."
            )
        if err == "rate_limited_guild":
            limit = result.get("limit", BOUNTY_GUILD_LIMIT)
            wait = self._format_wait(result.get("seconds_until_slot", 0))
            return (
                f"🛑 This server has hit its **{limit} bounties per week** cap. "
                f"Next slot opens in **{wait}**."
            )
        return "⚠️ Bounty failed (database error). Try again in a moment."

    @commands.command(name="bounty")
    @commands.guild_only()
    async def bounty_prefix(self, ctx, target: discord.Member = None, bet: int = 0):
        """Place a coin bounty for a chance to jail another user. Fails put YOU in jail."""
        channel_id = ctx.channel.id if ctx.channel else 0
        msg = await self._run_bounty(ctx.guild, channel_id, ctx.author, target, bet)
        await ctx.send(msg)

    @app_commands.command(name="bounty", description=f"Pay ≥ {MIN_BOUNTY:,} coins for a chance to jail someone. Fails put YOU in jail.")
    @app_commands.describe(
        target="The user you want jailed",
        bet="How many coins to put up (min 100,000,000)",
    )
    async def bounty_slash(self, interaction: discord.Interaction, target: discord.Member, bet: int):
        channel_id = interaction.channel_id or 0
        msg = await self._run_bounty(interaction.guild, channel_id, interaction.user, target, bet)
        await interaction.response.send_message(msg)


async def setup(bot):
    await bot.add_cog(Bounty(bot))
