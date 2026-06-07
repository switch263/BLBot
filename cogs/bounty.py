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
from amount import parse_amount, amount_error

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


# Inmates-board flavor for jail rows created by /bounty. Used as the `reason`
# column so the inmates command displays something funnier than "Bounty placed by X".
# Two pools: one for the *target* (what the placer pinned on them), one for the
# *placer* themselves (what they got caught doing while arranging the hit).

TARGET_CRIME_REASONS = [
    "Caught laundering nickels through a Coinstar",
    "Fed the koi pond entire baguettes (no permit)",
    "Replaced the casino's complimentary peanuts with wasabi peas",
    "Convicted of being TOO good at thumb wars",
    "Yodeling in the no-yodeling zone",
    "Accepted a bribe of one (1) Werther's Original",
    "Unsanctioned interpretive dance at the craps table",
    "Failed a vibe check, repeatedly",
    "Wore Crocs to the high-stakes table",
    "Running a Ponzi scheme involving Beanie Babies",
    "Tampered with a slot machine using a fridge magnet",
    "Whispering to the dice. The dice confessed everything.",
    "Refused to tip the dealer 'on principle'",
    "Brought their own deck. From 2003. Pokémon on the back.",
    "Charged with crypto-something — nobody asked, they went anyway",
    "Uncomfortably loud at brunch",
    "Too friendly with the parking valet",
    "Excessive enthusiasm during 'Take Me Home, Country Roads'",
    "Replaced the casino's coffee with decaf",
    "Listed 'vibes' as occupation on their W-2",
    "Running an unlicensed lemonade stand inside the casino",
    "Made eye contact with the dealer for 17 uninterrupted seconds",
    "Wore the same outfit as the pit boss. On purpose.",
    "Tried to pay in Chuck E. Cheese tokens. Twice.",
    "Heckled the live piano player",
    "Smuggled a goldfish past security in a regular fish tank",
    "Microwaved fish in the high-roller lounge",
    "Caught reading aloud from a self-help book at the blackjack table",
    "Suspected of being a guy named Steve. They are not Steve.",
    "Refused to break eye contact with the security camera for 3 hours",
]

PLACER_BOTCH_REASONS = [
    "Tripped over their own getaway scooter mid-handoff",
    "Hired a 'hitman' off Craigslist. It was a guy named Greg who flips couches.",
    "Wrote 'eliminate {target}' on a napkin and left it at the table",
    "Paid the hitman in Chuck E. Cheese tokens",
    "Tried to recruit a hitman in a Wendy's drive-thru. Wendy's has cameras.",
    "Drunkenly Yelp-reviewed the failed hit",
    "Texted the contract to their mom by mistake. Mom called the cops.",
    "Posted the bounty on LinkedIn",
    "Hired a hitman who turned out to be an undercover Boy Scout",
    "Caught practicing menacing in a mirror at Cabela's",
    "Wore a fedora to the meet. Profiled immediately.",
    "Confessed everything during a TED talk audition",
    "Submitted the bounty paperwork as a Mad Libs",
    "Hired their own roommate. Roommate ratted for the security deposit.",
    "Dropped the contract under a coffee cup at the DMV",
    "Tried to bribe a goldfish to deliver the contract. Goldfish testified.",
    "Solicited a hit in the comments of a bonsai forum",
    "Used the wrong burner phone. It was actually a calculator.",
    "Said 'I'd like to place a bounty' out loud, in line, at a Starbucks",
    "Wrote out the hit instructions in fridge magnets at a friend's house",
    "Hired a hitman with a Pinterest board titled 'wet work'",
    "Tried to pay the hitman in unsigned IOUs. They cashed one anyway.",
    "Carved the target's name into a park bench in front of three witnesses",
    "Forgot the target's name mid-handoff and just said 'you know, that guy'",
    "Tried to slip the hitman a folded note in cursive. They couldn't read cursive.",
    "Gave the hitman a printed PowerPoint deck. Slide 7 was self-incriminating.",
    "Live-tweeted the planning phase. Pinned the worst tweet.",
    "Got mistaken for their own hitman. Arrested by both teams.",
    "Stored the contract in their Notes app. iCloud sync did the rest.",
    "Tried to subcontract the hit to a Roomba",
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
        # kev2tall is a memorial player. Trying to bounty him gets you smited —
        # no bet floor, no rate limit, no jail gate. The desecration is enough.
        if economy.is_memorial(target.id):
            return await self._smite_for_memorial_bounty(guild, placer)
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
            # Unhinged inmates-board crime; tag the placer so people can tell who paid.
            crime = f"{random.choice(TARGET_CRIME_REASONS)} (bountied by {placer.display_name})"
            result = economy.place_jail_bounty(
                guild.id, placer.id, target.id,
                bet=bet, success=True, jail_seconds=jail_seconds,
                channel_id=channel_id, reason=crime,
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
        # Unhinged botch flavor; substitute the target's name where the template asks for it.
        botch = random.choice(PLACER_BOTCH_REASONS).format(target=target.display_name)
        economy.jail_user(
            guild.id, placer.id, backfire_seconds,
            reason=botch,
            bail_amount=0,  # no bail-out — they shouldn't have hired an idiot
            channel_id=channel_id,
        )
        hours = max(1, round(backfire_seconds / 3600))
        return random.choice(FAIL_FLAVOR).format(
            placer=placer.mention, target=target.mention, bet=bet, hours=hours,
        )

    async def _smite_for_memorial_bounty(self, guild: discord.Guild, placer: discord.Member) -> str:
        """kev2tall is a memorial player. Putting a bounty on him is a
        desecration: half the placer's wallet is torn loose and locked away
        in the house's safe-harbor reserve (untouchable), and kev2tall makes
        his displeasure known."""
        balance = economy.get_coins(guild.id, placer.id)
        smite_amount = balance // 2

        seized = 0
        if smite_amount > 0:
            result = economy.transfer_to_reserve(guild.id, placer.id, smite_amount)
            if result.get("ok"):
                seized = smite_amount

        crab = " 🦀 "
        msg = (
            f"🕊️🦀 **WHO DARES.**\n"
            f"{placer.mention} put a bounty on **kev2tall**. The memorial does not rest so lightly.\n"
            f"*\"You disturb my peace{crab}for COIN?{crab}I was a MEMBER here.\"*\n"
        )
        if seized > 0:
            msg += (
                f"kev2tall tears **{seized:,} coins** — half of {placer.mention}'s wallet — "
                f"loose and locks them away in the house's safe-harbor reserve.{crab}"
                f"Untouchable now. Let this be a lesson."
            )
        else:
            msg += (
                f"kev2tall reaches for {placer.mention}'s wallet and finds it bare. "
                f"The smite lands on empty pockets.{crab}Consider yourself warned."
            )
        return msg

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
        if err == "memorial":
            return "🕊️ kev2tall can't be bountied. The memorial is off-limits — nothing was charged."
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
    async def bounty_prefix(self, ctx, target: discord.Member = None, bet: str = ""):
        """Place a coin bounty for a chance to jail another user. Fails put YOU in jail."""
        channel_id = ctx.channel.id if ctx.channel else 0
        parsed_bet = None
        if bet:
            parsed_bet = parse_amount(bet)
            if parsed_bet is None:
                await ctx.send(amount_error(bet))
                return
        msg = await self._run_bounty(ctx.guild, channel_id, ctx.author, target, parsed_bet)
        await ctx.send(msg)

    @app_commands.command(name="bounty", description=f"Pay ≥ {MIN_BOUNTY:,} coins for a chance to jail someone. Fails put YOU in jail.")
    @app_commands.describe(
        target="The user you want jailed",
        bet="How many coins to put up (min 100,000,000)",
    )
    async def bounty_slash(self, interaction: discord.Interaction, target: discord.Member, bet: str):
        channel_id = interaction.channel_id or 0
        parsed_bet = parse_amount(bet)
        if parsed_bet is None:
            await interaction.response.send_message(amount_error(bet), ephemeral=True)
            return
        msg = await self._run_bounty(interaction.guild, channel_id, interaction.user, target, parsed_bet)
        await interaction.response.send_message(msg)


async def setup(bot):
    await bot.add_cog(Bounty(bot))
