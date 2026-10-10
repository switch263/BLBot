import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
import logging
import time

import economy
from economy import (HOUSE_HEIST_MIN_PCT, HOUSE_HEIST_MAX_PCT, CREW_BOX_MAX_PCT,
                     BANK_RAID_MIN_PCT, BANK_RAID_MAX_PCT)

logger = logging.getLogger(__name__)

# Crew Heist — the multiplayer job. One player (the ringleader) cases a target,
# then recruits a crew. Each RECRUIT antes CREW_BUYIN; the ringleader antes
# nothing — the buy-ins are their recruiting fee, paid out the moment the job
# launches, win or lose. More crew = better odds AND a bigger slice of the
# take, but a bust sends everyone who doesn't slip away to casino jail.
#
# Money flow (per CLAUDE.md):
#   - buy-in: transfer_to_house(is_bet=False) at join — the house is only the
#     ESCROW agent here, so a ringleader can't pocket the fees and cancel.
#   - dissolve/cancel/timeout: refund_from_house back to each recruit.
#   - launch: refund_from_house releases the escrow to the RINGLEADER.
#   - loot: disburse(victim -> crew) — pure player↔player, atomic.
# The house CAN be targeted, at drastically worse odds (see the HOUSE_ block):
# a crew that gets in does THE FULL SWEEP — the vault (same capped band as a
# solo vault crack, off on-hand) AND the safe-deposit boxes (a rolled
# BANK_RAID cut of every player's bank, the crew's own excepted), split by
# the crew. A house job can also name ONE safe-deposit box — a single player's bank
# account — and pick an APPROACH (see the BOX_ block): each approach trades
# odds against take against how ugly the bust is.

CREW_BUYIN = 1_000_000
CREW_MIN_CREW = 2            # starter + at least one recruit
CREW_MAX_CREW = 3
LOBBY_TIMEOUT = 180          # seconds before an unlaunched lobby dissolves

# Floor on the target's stash (player wallet OR house on-hand). Sized so a
# recruit can NEVER lose money on a successful job: the worst possible roll is
# a 2-crew 10% take split two ways = stash/20 per head, so 25M guarantees at
# least 1.25M against the 1M seat. Checked at lobby creation AND re-checked at
# launch (with refunds) in case the stash shrank while the crew assembled.
MIN_VICTIM_COINS = 25_000_000

# Odds: 2-person crew starts at BASE, each extra body adds PER_MEMBER, capped.
BASE_SUCCESS_RATE = 0.40
PER_MEMBER_BONUS = 0.08
SUCCESS_RATE_CAP = 0.60  # generous headroom; a full crew of 3 sits at 48%

# Loot: rolled pct of the victim's wallet. Each extra crew member raises both
# ends of the band, the top end much faster — so a full crew of 3 rolls a wide
# 25–50% gamble instead of a tight guaranteed band. Hard cap STEAL_CAP_PCT.
STEAL_MIN_PCT = 0.10
STEAL_MAX_PCT = 0.15
PER_MEMBER_STEAL_LO = 0.15
PER_MEMBER_STEAL_HI = 0.35
STEAL_CAP_PCT = 0.50

# Bust: each member independently rolls to slip away; the rest get pinched.
ESCAPE_RATE = 0.40
JAIL_MIN_SECONDS = 30 * 60
JAIL_MAX_SECONDS = 2 * 60 * 60
BAIL_AMOUNT = 5 * CREW_BUYIN

CREW_COOLDOWN = 30 * 60  # per member, started when a job LAUNCHES

# ---- Robbing the house as a crew --------------------------------------------
# Way, WAY worse odds than a player job — a success is the full sweep: a
# rolled cut of the house's ENTIRE on-hand pot (same HOUSE_HEIST band as solo
# /heist @bot) PLUS a rolled BANK_RAID cut of every player's bank account, so
# both drains stay capped and the win chance has to live near solo-heist
# territory (solo vault ≈ 0.8%, solo full sweep 1/5000), not lobby-game odds.
HOUSE_SUCCESS_RATES = {2: 0.02, 3: 0.04}   # crew size -> odds
HOUSE_ESCAPE_RATE = 0.20                    # the bot sees everything
HOUSE_JAIL_MIN_SECONDS = 1 * 60 * 60
HOUSE_JAIL_MAX_SECONDS = 24 * 60 * 60
HOUSE_BAIL_WALLET_PCT = 0.25                # bail = max(BAIL_AMOUNT, 25% of wealth: wallet + bank)
HOUSE_BAIL_CAP = 100_000_000
HOUSE_COOLDOWN = 6 * 60 * 60                # matches the solo /heist cooldown

# ---- Cracking one safe-deposit box ------------------------------------------
# /crewheist target:@bot account:@player approach:<...> — the crew goes after
# the casino, but instead of the vault they drill ONE box: that player's bank.
# The take is a rolled cut of that account alone (never the house's on-hand),
# so the odds can live well above the vault's — but tests/test_crewbox.py pins
# every approach's expected take (odds x mean cut) BELOW the wallet job's at
# the same crew size, and every band under economy.CREW_BOX_MAX_PCT. The bank
# must stay the safer place to keep coins even now that a crew can reach it.
#
# Each approach: odds by crew size, take band, how many slip a bust, how long
# the caught sit, and (cyber only) a counter-hack fine on the caught — the bot
# traces the wire back and empties the pockets it finds. Bail is wealth-scaled
# like the vault's (HOUSE_BAIL_*); cooldown is the house job's.
BOX_APPROACHES = {
    "physical": {
        "emoji": "🔨", "label": "Physical Breach",
        "blurb": "Thermite, a diamond drill, and a van idling in the loading dock.",
        "odds": {2: 0.18, 3: 0.26},
        "take": (0.10, 0.20),
        "escape": 0.30,
        "jail": (1 * 60 * 60, 12 * 60 * 60),
        "fine_pct": 0.0,
    },
    "cyber": {
        "emoji": "💻", "label": "Cyberwarfare",
        "blurb": "Nobody leaves the apartment. The box opens itself — if the exploit lands.",
        "odds": {2: 0.12, 3: 0.18},
        "take": (0.15, 0.30),
        "escape": 0.10,
        "jail": (30 * 60, 4 * 60 * 60),
        "fine_pct": 0.10,
    },
    "social": {
        "emoji": "🎭", "label": "Social Engineering",
        "blurb": "A clipboard, a hi-vis vest, and the confidence of a man who belongs here.",
        "odds": {2: 0.28, 3: 0.36},
        "take": (0.05, 0.12),
        "escape": 0.50,
        "jail": (1 * 60 * 60, 6 * 60 * 60),
        "fine_pct": 0.0,
    },
    "inside": {
        "emoji": "🕴️", "label": "Inside Job",
        "blurb": "Somebody on the casino payroll owes somebody a favor. Big swing.",
        "odds": {2: 0.22, 3: 0.30},
        "take": (0.08, 0.25),
        "escape": 0.20,
        "jail": (2 * 60 * 60, 24 * 60 * 60),
        "fine_pct": 0.0,
    },
}
DEFAULT_APPROACH = "physical"

# Floor on the box's balance: the stingiest possible roll (lowest take_lo of
# any approach, full crew) must still pay each recruit at least their seat.
BOX_MIN_BANK = -(-CREW_BUYIN * CREW_MAX_CREW // min(a["take"][0] for a in BOX_APPROACHES.values()))
BOX_MIN_BANK = int(BOX_MIN_BANK)

REVEAL_DELAY = 1.5

BUILDUP = [
    "🚐 The crew piles into a van with no plates and one working headlight…",
    "🗺️ {starter} taps the blueprint. \"Everyone knows the plan. Nobody improvises.\"",
    "🧤 Gloves on. Masks down. {crew_size} sets of footsteps in the dark…",
    "💰 They're at {victim}'s stash. Hands moving fast…",
]

SUCCESS_MESSAGES = [
    "The crew cleaned out **{amount:,}** coins from {victim}'s stash and was gone before the porch light flicked on.",
    "Flawless. In, out, **{amount:,}** coins of {victim}'s money in duffel bags, and the van didn't even stall.",
    "{victim} slept through the whole thing. The crew walked with **{amount:,}** coins and took the good snacks too.",
    "The safe popped on the first try. **{amount:,}** coins of {victim}'s savings, split like a pizza.",
    "Security cameras caught nothing but a raccoon. Meanwhile the crew moved **{amount:,}** coins of {victim}'s stash out the back.",
]

FAIL_MESSAGES = [
    "{victim}'s dog would not stop barking. Floodlights, sirens, chaos — the job fell apart at the door.",
    "Someone leaned on the panic button trying to look casual. The crew scattered as the cops rolled in on {victim}'s street.",
    "The getaway van got wedged in {victim}'s driveway. It's a two-way driveway. The crew ran on foot.",
    "{victim} was home. Awake. Holding a sandwich. Eye contact was made. The job was over.",
    "The 'inside guy' was {victim}'s cousin the whole time. Total setup. Run.",
]

ESCAPE_LINES = [
    "🏃 {member} vaulted a fence, crossed two backyards, and was home in bed before the sirens faded.",
    "🏃 {member} ripped the mask off and joined the crowd of onlookers. \"Crazy night, huh?\"",
    "🏃 {member} slid under a parked RV and simply waited it out. Four hours. Worth it.",
    "🏃 {member} stole a bicycle from the crime scene and pedaled into the night. A second, smaller crime.",
]

CAUGHT_LINES = [
    "🚔 {member} tripped over a garden gnome mid-sprint. Pinched.",
    "🚔 {member} ran into a cul-de-sac. It's in the name. Pinched.",
    "🚔 {member} stopped to grab the duffel bag. Loyalty to money is still loyalty. Pinched.",
    "🚔 {member} hid in a porta-potty. The K-9 unit did not respect the sanctity. Pinched.",
]

HOUSE_SUCCESS_MESSAGES = [
    "The crew drilled the vault wall for six hours and it PAID: **{amount:,}** coins — **{pct}%** of everything the house had on hand.",
    "Inside man, dead cameras, a very confused pit boss — the crew walked the vault for **{amount:,}** coins ({pct}% of on-hand).",
    "The house always wins. Except tonight. **{amount:,}** coins — **{pct}%** of the pot — out the loading dock.",
]

HOUSE_BOXES_MESSAGES = [
    "🏧 And on the way out — the **safe-deposit boxes**: **{pct}%** skimmed off **{accounts} bank account{plural}** for another **{amount:,}** coins.",
    "🏧 Then the crew took a crowbar to the **safe-deposit boxes** — **{pct}%** out of **{accounts} account{plural}**, **{amount:,}** coins more.",
]
HOUSE_BOXES_EMPTY = "🏧 The safe-deposit boxes were empty. The vault will have to do."
HOUSE_VAULT_EMPTY = "🏦 The vault was bare — somebody drained it first. The boxes will have to do."

HOUSE_FAIL_MESSAGES = [
    "The vault door didn't budge and the bot's security mainframe had already dialed everyone. Floodlights. Dogs. Regret.",
    "Turns out the 'blind spot' in the casino cameras was bait. The crew walked straight into it.",
    "Three steps into the counting room, every slot machine turned to face them. The house knew the whole time.",
]

BOX_BUILDUP = {
    "physical": [
        "🚐 The van backs up to the casino's loading dock. Someone kills the dome light…",
        "🗺️ {starter} taps the blueprint. \"Box {box}. {account}'s. In and out, nobody gets cute.\"",
        "🔨 Thermite on the hinge. {crew_size} sets of goggles staring at the glow…",
        "🔥 The plate sags. The drill screams. The box is right THERE…",
    ],
    "cyber": [
        "💻 {crew_size} laptops, one apartment, zero natural light. {starter} cracks their knuckles…",
        "📡 The casino's box registry is on a subnet somebody forgot about. Port open…",
        "🔑 {account}'s box record loads. Escalating privileges… the mainframe is thinking about it…",
        "⌛ Progress bar. 60%. 80%. 99%…",
    ],
    "social": [
        "🎭 {starter} straightens a hi-vis vest that fits nobody and picks up a clipboard…",
        "🚪 \"Fire inspection. Box {box}.\" The pit boss squints. {crew_size} people smile too hard…",
        "🗝️ \"{account} called ahead. Said we'd have the master key waiting.\" Nobody said that…",
        "🤝 The floor manager reaches for the keyring. Or the phone. Hard to tell…",
    ],
    "inside": [
        "🕴️ A dealer on the casino payroll leaves a side door propped with a matchbook…",
        "🗺️ {starter} whispers: \"Box {box}. {account}. Our guy swapped the audit tape.\"",
        "🔦 {crew_size} shadows in the counting room. The inside man's badge beeps them through…",
        "🔓 The box drawer slides. Something upstairs clicks. Could be the AC…",
    ],
}

BOX_SUCCESS_MESSAGES = {
    "physical": [
        "The hinge gave and so did **{amount:,}** coins of {account}'s box — **{pct}%** of the account — into duffel bags before the sprinklers kicked on.",
        "Drilled, popped, emptied. **{amount:,}** coins ({pct}% of {account}'s bank) wheeled out the loading dock in a laundry cart.",
        "The box came off the wall in one piece. The crew took the whole thing. **{amount:,}** coins of {account}'s savings.",
    ],
    "cyber": [
        "The exploit landed. {account}'s box balance quietly reassigned itself — **{amount:,}** coins, **{pct}%** of the account — to {crew_size} new owners.",
        "One ledger edit, no fingerprints. **{amount:,}** coins ({pct}% of {account}'s bank) now belong to a group chat.",
        "The mainframe asked for a password and the crew said yes. **{amount:,}** coins of {account}'s box routed through nine countries and into the van.",
    ],
    "social": [
        "The floor manager opened box {box} himself and apologized for the wait. **{amount:,}** coins — **{pct}%** of {account}'s account — walked out under a clipboard.",
        "\"Routine audit,\" said {starter}. The pit boss held the door. **{amount:,}** coins ({pct}% of {account}'s bank) left in a branded tote bag.",
        "Nobody checked the vest. Nobody ever checks the vest. **{amount:,}** coins of {account}'s savings, signed out on a fake form.",
    ],
    "inside": [
        "The inside man swapped the tape and the crew swapped the box. **{amount:,}** coins — **{pct}%** of {account}'s account — gone before the shift change.",
        "Badge beeped, drawer slid, **{amount:,}** coins ({pct}% of {account}'s bank) left through the employee entrance.",
        "The casino will find the discrepancy at next month's audit. By then **{amount:,}** coins of {account}'s box will be very, very spent.",
    ],
}

BOX_FAIL_MESSAGES = {
    "physical": [
        "The thermite lit the wrong hinge. Then the wall. Then the sprinklers, the alarm, and every light in the building.",
        "The drill bit snapped on box {box}'s reinforced plate. The noise brought security, the dogs, and the fire department.",
        "The van in the loading dock got boxed in by a delivery truck. The crew was still holding the drill when the shutters dropped.",
    ],
    "cyber": [
        "The 'forgotten subnet' was a honeypot. The bot logged every keystroke, every IP, and, somehow, everyone's home address.",
        "99% became 'CONNECTION TRACED'. The apartment's smart lock engaged from the outside.",
        "The exploit ran fine. On the crew's own machines. The bot mirrored the payload back with interest.",
    ],
    "social": [
        "The pit boss asked for the inspection permit number. {starter} said a number. It was the year.",
        "\"{account} called ahead\" fell apart when {account} walked in to make a deposit.",
        "The hi-vis vest said CONTRACTOR on the back and the crew had misspelled it.",
    ],
    "inside": [
        "The inside man was inside for the house. The propped side door led straight into the security office.",
        "The audit tape was swapped. So was the box — for a decoy full of dye packs.",
        "The dealer took the favor, the matchbook, and a promotion. The crew got a wall of floodlights.",
    ],
}

BOX_ESCAPE_LINES = {
    "physical": [
        "🏃 {member} rode the laundry cart down the service ramp and out into traffic.",
        "🏃 {member} slipped out through the loading dock behind a linen delivery. Nobody counts linen.",
    ],
    "cyber": [
        "🏃 {member} yanked the router, wiped the drive, and was asleep before the knock.",
        "🏃 {member} had a VPN inside a VPN inside a coffee shop. The trace stopped at a barista.",
    ],
    "social": [
        "🏃 {member} kept the vest on and helped security look for the suspects.",
        "🏃 {member} clipboard-walked straight out the front doors. Confidence is a getaway car.",
    ],
    "inside": [
        "🏃 {member} clocked out on the inside man's badge and left through the employee lot.",
        "🏃 {member} hid in the dealers' break room and ate someone's labeled lunch until the shift changed.",
    ],
}

BOX_CAUGHT_LINES = {
    "physical": [
        "🚔 {member} was still holding the drill. Pinched.",
        "🚔 {member} tried to hide inside a slot machine cabinet. The cabinet was on. Pinched.",
    ],
    "cyber": [
        "🚔 {member}'s webcam light came on by itself. Then the door. Pinched — and the bot took a cut on the way out.",
        "🚔 {member} was mid-'rm -rf' when the smart lock clicked. Pinched, and counter-hacked.",
    ],
    "social": [
        "🚔 {member} was asked to state the fire code. {member} stated the fire code from a movie. Pinched.",
        "🚔 {member} signed the visitor log with a real name. Pinched.",
    ],
    "inside": [
        "🚔 {member} followed the inside man through the 'exit'. It was the security office. Pinched.",
        "🚔 {member} was dye-packed head to toe and tried to say it was a fashion choice. Pinched.",
    ],
}

LOBBY_TITLE = "🚐 Crew Heist — Recruiting"
INPROGRESS_TITLE = "🚐 The Job Is On…"
BOX_INPROGRESS_TITLE = "{emoji} The Job Is On — {label}…"


def _success_rate(crew_size: int) -> float:
    return min(SUCCESS_RATE_CAP,
               BASE_SUCCESS_RATE + PER_MEMBER_BONUS * (crew_size - CREW_MIN_CREW))


def _house_success_rate(crew_size: int) -> float:
    return HOUSE_SUCCESS_RATES.get(crew_size, HOUSE_SUCCESS_RATES[CREW_MAX_CREW])


def _steal_pct_bounds(crew_size: int) -> tuple[float, float]:
    extra = crew_size - CREW_MIN_CREW
    lo = min(STEAL_CAP_PCT, STEAL_MIN_PCT + PER_MEMBER_STEAL_LO * extra)
    hi = min(STEAL_CAP_PCT, STEAL_MAX_PCT + PER_MEMBER_STEAL_HI * extra)
    return lo, hi


def _box_success_rate(approach: str, crew_size: int) -> float:
    odds = BOX_APPROACHES[approach]["odds"]
    return odds.get(crew_size, odds[CREW_MAX_CREW])


def _box_take_bounds(approach: str) -> tuple[float, float]:
    lo, hi = BOX_APPROACHES[approach]["take"]
    return min(lo, CREW_BOX_MAX_PCT), min(hi, CREW_BOX_MAX_PCT)


def resolve_approach(text: str | None) -> str | None:
    """Map a typed approach ('cyber', 'Cyberwarfare', 'phys'…) to a key.
    None/blank -> DEFAULT_APPROACH; unknown -> None."""
    if text is None or not text.strip():
        return DEFAULT_APPROACH
    t = text.strip().lower()
    for key, a in BOX_APPROACHES.items():
        if t == key or t == a["label"].lower():
            return key
    for key, a in BOX_APPROACHES.items():
        if key.startswith(t) or a["label"].lower().startswith(t):
            return key
    return None


def _span(seconds: int) -> str:
    """'30m' / '4h' for a jail-range display."""
    return f"{seconds // 3600}h" if seconds >= 3600 else f"{seconds // 60}m"


def _approach_usage() -> str:
    return " / ".join(f"`{k}`" for k in BOX_APPROACHES)


class CrewLobby:
    def __init__(self, guild_id: int, channel_id: int,
                 starter: discord.Member, victim: discord.Member, is_house: bool,
                 account: discord.Member | None = None, approach: str | None = None):
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.starter = starter
        self.victim = victim
        self.is_house = is_house
        # Box job: the crew is still hitting the casino (is_house stays True —
        # house cooldown, house bail scaling) but the loot is ONE player's bank.
        self.account = account
        self.approach = approach
        self.is_box = account is not None
        self.members: list[discord.Member] = [starter]
        self.paid: dict[int, int] = {}  # user_id -> buy-in actually paid (surcharged)
        self.message: discord.Message | None = None
        self.resolved = False  # launched, cancelled, or timed out

    def is_member(self, user_id: int) -> bool:
        return any(m.id == user_id for m in self.members)


class CrewHeistView(discord.ui.View):
    def __init__(self, cog, lobby: CrewLobby):
        super().__init__(timeout=LOBBY_TIMEOUT)
        self.cog = cog
        self.lobby = lobby

    async def on_timeout(self):
        lobby = self.lobby
        if lobby.resolved:
            return
        lobby.resolved = True
        self.cog._close_lobby(lobby)
        self.cog._refund_all(lobby)
        for child in self.children:
            child.disabled = True
        if lobby.message:
            try:
                await lobby.message.edit(
                    content=None,
                    embed=discord.Embed(
                        title="🚐 Crew Heist — Called Off",
                        description=("The crew sat in the van arguing about the radio until sunrise. "
                                     "Nobody left the safehouse. **Buy-ins refunded.**"),
                        color=discord.Color.dark_grey(),
                    ),
                    view=self,
                )
            except discord.HTTPException:
                pass

    @discord.ui.button(label=f"Join the crew — {CREW_BUYIN:,}", style=discord.ButtonStyle.success, emoji="🧤")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        lobby = self.lobby
        if lobby.resolved:
            await interaction.response.send_message("This job's already over.", ephemeral=True)
            return
        user = interaction.user
        err = self.cog._can_join(lobby, user)
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return
        # The prestigious pay more for everything. is_bet=False means economy
        # won't auto-surcharge this escrow, so apply it here. The seat/min-bank
        # checks stay on base CREW_BUYIN — only the actual charge is surcharged.
        amount = economy.prestige_surcharge(lobby.guild_id, user.id, CREW_BUYIN)
        res = economy.transfer_to_house(lobby.guild_id, user.id, amount, is_bet=False)
        if not res.get("ok"):
            if res.get("error") == "broke":
                await interaction.response.send_message(
                    f"💸 The buy-in is **{amount:,}** coins and you have **{res.get('have', 0):,}**. "
                    "The crew doesn't do IOUs.", ephemeral=True)
            else:
                await interaction.response.send_message("⚠️ Couldn't collect your buy-in. Try again.", ephemeral=True)
            return
        lobby.members.append(user)
        lobby.paid[user.id] = amount
        await interaction.response.edit_message(embed=self.cog._lobby_embed(lobby), view=self)

    @discord.ui.button(label="Back out", style=discord.ButtonStyle.secondary, emoji="🚪")
    async def back_out(self, interaction: discord.Interaction, button: discord.ui.Button):
        lobby = self.lobby
        if lobby.resolved:
            await interaction.response.send_message("This job's already over.", ephemeral=True)
            return
        user = interaction.user
        if user.id == lobby.starter.id:
            await interaction.response.send_message(
                "You're the ringleader — use **Call it off** to dissolve the whole job.", ephemeral=True)
            return
        if not lobby.is_member(user.id):
            await interaction.response.send_message("You're not on this crew.", ephemeral=True)
            return
        lobby.members = [m for m in lobby.members if m.id != user.id]
        economy.refund_from_house(lobby.guild_id, user.id, lobby.paid.pop(user.id, CREW_BUYIN))
        await interaction.response.edit_message(embed=self.cog._lobby_embed(lobby), view=self)

    @discord.ui.button(label="Launch the job", style=discord.ButtonStyle.danger, emoji="🚀")
    async def launch(self, interaction: discord.Interaction, button: discord.ui.Button):
        lobby = self.lobby
        if interaction.user.id != lobby.starter.id:
            await interaction.response.send_message("Only the ringleader launches the job.", ephemeral=True)
            return
        if lobby.resolved:
            await interaction.response.send_message("This job's already over.", ephemeral=True)
            return
        if len(lobby.members) < CREW_MIN_CREW:
            await interaction.response.send_message(
                f"You need at least **{CREW_MIN_CREW}** on the crew. Recruit somebody.", ephemeral=True)
            return
        lobby.resolved = True
        self.stop()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        await self.cog._run_job(lobby, interaction)

    @discord.ui.button(label="Call it off", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        lobby = self.lobby
        if interaction.user.id != lobby.starter.id:
            await interaction.response.send_message("Only the ringleader can call it off.", ephemeral=True)
            return
        if lobby.resolved:
            await interaction.response.send_message("This job's already over.", ephemeral=True)
            return
        lobby.resolved = True
        self.stop()
        self.cog._close_lobby(lobby)
        self.cog._refund_all(lobby)
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="🚐 Crew Heist — Called Off",
                description=f"**{lobby.starter.display_name}** got cold feet. Job's off. **Buy-ins refunded.**",
                color=discord.Color.dark_grey(),
            ),
            view=self,
        )


class CrewHeist(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active: dict[int, CrewLobby] = {}   # channel_id -> lobby
        self._cooldowns: dict[tuple[int, int], float] = {}

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Crew Heist module has been loaded")

    # ---- lobby bookkeeping -------------------------------------------------

    def _close_lobby(self, lobby: CrewLobby):
        if self.active.get(lobby.channel_id) is lobby:
            del self.active[lobby.channel_id]

    def _refund_all(self, lobby: CrewLobby):
        # Recruits get their escrowed buy-in back; the ringleader never paid one.
        for m in lobby.members:
            if m.id != lobby.starter.id:
                economy.refund_from_house(lobby.guild_id, m.id, lobby.paid.get(m.id, CREW_BUYIN))

    def _cooldown_remaining(self, guild_id: int, user_id: int) -> int:
        # Stored as EXPIRY timestamps — player and house jobs cool down differently.
        expiry = self._cooldowns.get((guild_id, user_id), 0)
        return max(0, int(expiry - time.time()))

    def _can_join(self, lobby: CrewLobby, user: discord.Member) -> str | None:
        """Ephemeral error string if `user` can't join, else None."""
        if user.bot:
            return "Bots can't crew up."
        if lobby.is_member(user.id):
            return "You're already on the crew."
        if user.id == lobby.victim.id:
            return "You can't join a heist against yourself. Bold, though."
        if lobby.account is not None and user.id == lobby.account.id:
            return "That's YOUR safe-deposit box they're drilling. You can't be on this crew."
        if economy.is_memorial(user.id):
            return "kev2tall doesn't run jobs anymore. Rest easy, brother. 🕊️"
        if len(lobby.members) >= CREW_MAX_CREW:
            return f"The van only seats **{CREW_MAX_CREW}**."
        jmsg = economy.jail_message(lobby.guild_id, user.id)
        if jmsg:
            return jmsg
        ban = economy.casino_ban_message(lobby.guild_id, user.id)
        if ban:
            return ban
        cd = self._cooldown_remaining(lobby.guild_id, user.id)
        if cd:
            m, s = divmod(cd, 60)
            return f"You're laying low after your last job. Ready in **{m // 60}h {m % 60}m {s}s**."
        return None

    # ---- embeds --------------------------------------------------------------

    def _lobby_embed(self, lobby: CrewLobby) -> discord.Embed:
        n = len(lobby.members)
        eff = max(n, CREW_MIN_CREW)
        crew_lines = "\n".join(f"• {m.mention}" + (" — ringleader" if m.id == lobby.starter.id else "")
                               for m in lobby.members)
        if lobby.is_box:
            a = BOX_APPROACHES[lobby.approach]
            rate = _box_success_rate(lobby.approach, eff)
            lo, hi = _box_take_bounds(lobby.approach)
            target_line = (f"**{lobby.starter.display_name}** is putting a crew together to hit the casino's "
                           f"safe-deposit boxes — specifically **{lobby.account.display_name}**'s.\n"
                           f"**Approach:** {a['emoji']} **{a['label']}** — {a['blurb']}")
            fine_line = ""
            if a["fine_pct"] > 0:
                fine_line = (f" The bot counter-hacks whoever it catches: **{int(a['fine_pct'] * 100)}%** "
                             f"of their wealth (wallet + bank), gone.")
            odds_line = (
                f"**Current odds:** {rate * 100:g}% (a full crew of {CREW_MAX_CREW}: "
                f"{_box_success_rate(lobby.approach, CREW_MAX_CREW) * 100:g}%).\n"
                f"**The take:** {int(lo * 100)}–{int(hi * 100)}% of **{lobby.account.display_name}**'s "
                f"bank account, split evenly. The house's own pot isn't touched.\n"
                f"**A bust:** {int(a['escape'] * 100)}% slip away — the caught eat "
                f"{_span(a['jail'][0])}–{_span(a['jail'][1])} of casino jail, bail scaling "
                f"with their wealth.{fine_line}\n"
                f"Cooldown after launch: {HOUSE_COOLDOWN // 3600}h."
            )
        elif lobby.is_house:
            rate = _house_success_rate(eff)
            target_line = (f"**{lobby.starter.display_name}** is putting a crew together for "
                           f"**THE FULL SWEEP** — the house vault AND every safe-deposit box in it. "
                           f"Ambitious. Stupid. Both.")
            odds_line = (
                f"**Current odds:** {rate * 100:g}% — this is the vault, not somebody's sock drawer.\n"
                f"**The take:** {int(HOUSE_HEIST_MIN_PCT * 100)}–{int(HOUSE_HEIST_MAX_PCT * 100)}% of the house's "
                f"entire on-hand pot **plus** {int(BANK_RAID_MIN_PCT * 100)}–{int(BANK_RAID_MAX_PCT * 100)}% of "
                f"**every player's bank account** (the crew's own spared), split evenly.\n"
                f"**A bust:** only {int(HOUSE_ESCAPE_RATE * 100)}% slip the bot's security — the caught eat up to "
                f"{HOUSE_JAIL_MAX_SECONDS // 3600}h of casino jail, bail scaling with their wealth (wallet + bank).\n"
                f"Cooldown after launch: {HOUSE_COOLDOWN // 3600}h."
            )
        else:
            rate = _success_rate(eff)
            lo, hi = _steal_pct_bounds(eff)
            target_line = (f"**{lobby.starter.display_name}** is putting a crew together to hit "
                           f"**{lobby.victim.display_name}**'s stash.")
            odds_line = (
                f"**Current odds:** {int(rate * 100)}% • **Take:** {int(lo * 100)}–{int(hi * 100)}% of the stash, split evenly.\n"
                f"A full crew of **{CREW_MAX_CREW}** runs {int(_success_rate(CREW_MAX_CREW) * 100)}% odds for "
                f"**{int(_steal_pct_bounds(CREW_MAX_CREW)[0] * 100)}–{int(_steal_pct_bounds(CREW_MAX_CREW)[1] * 100)}%** "
                f"of everything they've got.\n"
                f"**A bust:** everyone rolls to slip away — the slow ones eat up to "
                f"{JAIL_MAX_SECONDS // 3600}h of casino jail (bail {BAIL_AMOUNT:,})."
            )
        desc = (
            f"{target_line}\n\n"
            f"**Buy-in:** {CREW_BUYIN:,} coins per recruit, held in escrow — paid to the "
            f"**ringleader** when the job launches (win or lose). Ringleader rides free.\n"
            f"**Crew ({n}/{CREW_MAX_CREW}):**\n{crew_lines}\n\n"
            f"{odds_line}\n\n"
            f"Need **{CREW_MIN_CREW}+** to roll out. Lobby dissolves (with refunds) in "
            f"{LOBBY_TIMEOUT // 60} minutes if the ringleader doesn't launch."
        )
        return discord.Embed(title=LOBBY_TITLE, description=desc, color=discord.Color.orange())

    # ---- starting a lobby ----------------------------------------------------

    async def _start(self, ctx_or_interaction, victim: discord.Member | None,
                     account: discord.Member | None = None, approach_text: str | None = None):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)

        async def reply(text: str, ephemeral: bool = True):
            if is_slash:
                await ctx_or_interaction.response.send_message(text, ephemeral=ephemeral)
            else:
                await ctx_or_interaction.send(text)

        guild = ctx_or_interaction.guild
        if guild is None:
            await reply("Server only.")
            return
        starter = ctx_or_interaction.user if is_slash else ctx_or_interaction.author
        channel = ctx_or_interaction.channel

        if victim is None:
            await reply(f"Usage: `/crewheist target:@user` — recruit a crew ({CREW_BUYIN:,}/head) and hit their stash. "
                        f"Or `/crewheist target:@bot account:@user approach:<{_approach_usage()}>` "
                        f"to crack one player's safe-deposit box inside the casino.")
            return
        if channel.id in self.active:
            await reply("There's already a crew recruiting in this channel. One job at a time.")
            return
        if victim.id == starter.id:
            await reply("You can't put a crew together to rob yourself. Talk to somebody.")
            return
        is_house = bool(self.bot.user and victim.id == self.bot.user.id)
        if victim.bot and not is_house:
            await reply("That bot has no wallet. No wallet, no job.")
            return
        if economy.is_memorial(victim.id):
            await reply("Nobody hits kev2tall's stash. Job's off before it started. 🕊️")
            return
        if economy.is_memorial(starter.id):
            await reply("kev2tall doesn't run jobs anymore. Rest easy, brother. 🕊️")
            return
        # ---- box job validation ------------------------------------------------
        approach = None
        if account is not None or (approach_text is not None and approach_text.strip()):
            if not is_house:
                await reply("The **account** and **approach** options are for jobs on the casino — the box is "
                            "inside the bot's vault. Target the bot, then name whose box you want.")
                return
            if account is None:
                await reply(f"An approach needs a box to open. Name whose account you're after: "
                            f"`/crewheist target:@bot account:@user approach:<{_approach_usage()}>`.")
                return
            approach = resolve_approach(approach_text)
            if approach is None:
                await reply(f"Never heard of that approach. Pick one: {_approach_usage()}.")
                return
            if account.id == starter.id:
                await reply("You want to hire a crew to crack your own box? Just use `/withdraw`.")
                return
            if account.bot:
                await reply("Bots don't have safe-deposit boxes. The house IS the box. Name a player.")
                return
            if economy.is_memorial(account.id):
                await reply("Nobody touches kev2tall's box. Job's off before it started. 🕊️")
                return
        jmsg = economy.jail_message(guild.id, starter.id)
        if jmsg:
            await reply(jmsg)
            return
        ban = economy.casino_ban_message(guild.id, starter.id)
        if ban:
            await reply(ban)
            return
        cd = self._cooldown_remaining(guild.id, starter.id)
        if cd:
            h, rem = divmod(cd, 3600)
            m, s = divmod(rem, 60)
            await reply(f"You're laying low after your last job. Ready in **{h}h {m}m {s}s**.")
            return
        if account is not None:
            banked = economy.bank_balance(guild.id, account.id)
            if banked < BOX_MIN_BANK:
                await reply(f"**{account.display_name}**'s box holds under **{BOX_MIN_BANK:,}** coins. "
                            "Even a clean job would pay recruits less than their seats. Pick a fatter box.")
                return
            lobby = CrewLobby(guild.id, channel.id, starter, victim, is_house,
                              account=account, approach=approach)
            await self._open_lobby(ctx_or_interaction, is_slash, lobby)
            return
        stash_id = economy.get_house_id() if is_house else victim.id
        if economy.get_coins(guild.id, stash_id) < MIN_VICTIM_COINS:
            if is_house:
                await reply(f"The house's on-hand pot is under **{MIN_VICTIM_COINS:,}** coins right now — "
                            "even a successful vault job would pay less than the seats. Let it fatten up.")
            else:
                await reply(f"**{victim.display_name}**'s stash is under **{MIN_VICTIM_COINS:,}** coins. "
                            "Not worth the buy-ins — pick a richer mark.")
            return

        lobby = CrewLobby(guild.id, channel.id, starter, victim, is_house)
        await self._open_lobby(ctx_or_interaction, is_slash, lobby)

    async def _open_lobby(self, ctx_or_interaction, is_slash: bool, lobby: CrewLobby):
        self.active[lobby.channel_id] = lobby
        view = CrewHeistView(self, lobby)
        embed = self._lobby_embed(lobby)
        if is_slash:
            await ctx_or_interaction.response.send_message(embed=embed, view=view)
            lobby.message = await ctx_or_interaction.original_response()
        else:
            lobby.message = await ctx_or_interaction.send(embed=embed, view=view)

    # ---- running the job -------------------------------------------------------

    async def _run_job(self, lobby: CrewLobby, interaction: discord.Interaction):
        guild_id = lobby.guild_id
        crew = list(lobby.members)
        n = len(crew)
        victim = lobby.victim
        self._close_lobby(lobby)
        message = lobby.message or interaction.message
        channel_id = interaction.channel_id or 0

        if lobby.is_box:
            await self._run_box_job(lobby, message, channel_id)
            return

        # Target re-check: the stash may have shrunk (mark got robbed, house pot
        # got drained) while the crew assembled. Below the floor a "win" would
        # pay recruits less than their seats — no job, no fees, full refunds.
        stash_id = economy.get_house_id() if lobby.is_house else victim.id
        stash_now = economy.get_coins(guild_id, stash_id)
        if stash_now < MIN_VICTIM_COINS:
            self._refund_all(lobby)
            if lobby.is_house:
                desc = (f"The crew rolled up and the house's on-hand pot was down to "
                        f"**{stash_now:,}** coins — someone drained it first. Not worth the "
                        f"gas. **Buy-ins refunded.**")
            else:
                desc = (f"The crew rolled up and **{victim.display_name}**'s stash was down to "
                        f"**{stash_now:,}** coins. Not worth the gas. **Buy-ins refunded.**")
            await self._edit(message, discord.Embed(
                title="🚐 Crew Heist — Target Skipped Town",
                description=desc,
                color=discord.Color.dark_grey(),
            ))
            return

        # From here the job is ON: the escrowed buy-ins release to the
        # ringleader — their recruiting fee, win or lose — and cooldowns start.
        fee_total = sum(lobby.paid.get(m.id, CREW_BUYIN)
                        for m in lobby.members if m.id != lobby.starter.id)
        if fee_total > 0:
            economy.refund_from_house(guild_id, lobby.starter.id, fee_total)
        cooldown = HOUSE_COOLDOWN if lobby.is_house else CREW_COOLDOWN
        for m in crew:
            self._cooldowns[(guild_id, m.id)] = time.time() + cooldown

        # Heist Shield: an activated shield blocks the whole crew (player jobs
        # only — the house has no shield, it has odds). The ringleader still
        # keeps the fees; casing a hardened target is on them.
        if not lobby.is_house and \
                economy.kv_get(guild_id, victim.id, "heistshield", "active_date", "") == economy.today_str():
            await self._edit(message, discord.Embed(
                title="🛡️ Job Blocked!",
                description=(f"The crew hit **{victim.display_name}**'s place — and bounced straight off an "
                             f"active **Heist Shield**. The recruits are out **{CREW_BUYIN:,}** each and "
                             f"**{lobby.starter.display_name}** still pocketed the fees. Awkward van ride."),
                color=discord.Color.blue(),
            ))
            return

        # Stream the buildup as an append-only log, then land the outcome.
        fmt = dict(starter=lobby.starter.mention, victim=victim.display_name, crew_size=n)
        buildup = [line.format(**fmt) for line in BUILDUP]
        revealed = []
        for line in buildup:
            revealed.append(line)
            await self._edit(message, discord.Embed(
                title=INPROGRESS_TITLE, description="\n".join(revealed),
                color=discord.Color.dark_grey(),
            ))
            await asyncio.sleep(REVEAL_DELAY)

        rate = _house_success_rate(n) if lobby.is_house else _success_rate(n)
        success = random.random() < rate
        for m in crew:
            economy.record_game(guild_id, m.id, "crewheist", success)

        log = "\n".join(buildup) + "\n\n"
        if success:
            if lobby.is_house:
                # Same capped band as a solo vault crack (0-60% of ON-HAND only;
                # the safe-harbor reserve is untouchable), split by the crew.
                steal_pct = random.uniform(HOUSE_HEIST_MIN_PCT, HOUSE_HEIST_MAX_PCT)
                source_id = economy.get_house_id()
                stash = economy.get_coins(guild_id, source_id)
                success_pool = HOUSE_SUCCESS_MESSAGES
            else:
                lo, hi = _steal_pct_bounds(n)
                steal_pct = random.uniform(lo, hi)
                source_id = victim.id
                # Re-read right before moving money — the buildup takes a few seconds.
                stash = economy.get_coins(guild_id, source_id)
                success_pool = SUCCESS_MESSAGES
            loot = max(0, int(stash * steal_pct))
            share = loot // n
            paid_lines = []
            if share > 0:
                remainder = loot - share * n
                payments = [(m.id, share + (remainder if m.id == lobby.starter.id else 0)) for m in crew]
                res = economy.disburse(guild_id, source_id, payments)
                if res.get("ok"):
                    if not lobby.is_house:
                        economy.kv_set(guild_id, victim.id, "heistins", "last_loss",
                                       f"{loot}:{int(time.time())}")
                    paid_lines = [f"💰 {m.mention} pockets **{amt:,}** coins."
                                  for m, (_, amt) in zip(crew, payments)]
                else:
                    loot = 0
            if lobby.is_house:
                # The full sweep: the boxes too — a rolled BANK_RAID cut of every
                # player's bank account, the crew's own spared, split by the crew.
                raid_pct = random.uniform(BANK_RAID_MIN_PCT, BANK_RAID_MAX_PCT)
                raid = economy.bank_raid_split(guild_id, [m.id for m in crew], raid_pct)
                raid_paid = dict(raid["paid"])
                if raid["total"] > 0:
                    plural = "s" if raid["accounts"] != 1 else ""
                    boxes_line = random.choice(HOUSE_BOXES_MESSAGES).format(
                        amount=raid["total"], pct=int(round(raid_pct * 100)),
                        accounts=raid["accounts"], plural=plural)
                else:
                    boxes_line = HOUSE_BOXES_EMPTY
                vault_paid = dict(payments) if paid_lines else {}
                if loot > 0 and paid_lines:
                    headline = "✅ **" + random.choice(success_pool).format(
                        victim=victim.display_name, amount=loot, pct=int(round(steal_pct * 100))) + "**"
                else:
                    headline = HOUSE_VAULT_EMPTY
                if loot > 0 or raid["total"] > 0:
                    paid_lines = [f"💰 {m.mention} pockets **{vault_paid.get(m.id, 0) + raid_paid.get(m.id, 0):,}** coins."
                                  for m in crew]
                    body = (f"{headline}\n{boxes_line}\n\n" + "\n".join(paid_lines) +
                            f"\n\n({n}-way split. The house is furious. So is everyone with a bank account.)")
                else:
                    body = ("✅ The crew got in clean… and the vault AND the boxes were already bare. "
                            "Somebody beat them to everything. The van ride home was very quiet.")
            elif loot > 0 and paid_lines:
                headline = random.choice(success_pool).format(
                    victim=victim.display_name, amount=loot, pct=int(round(steal_pct * 100)))
                body = (f"✅ **{headline}**\n\n" + "\n".join(paid_lines) +
                        f"\n\n({int(round(steal_pct * 100))}% of the stash, {n}-way split. "
                        f"{victim.mention}, you just got crewed.)")
            else:
                body = (f"✅ The crew got in clean… and **{victim.display_name}**'s stash was already gone. "
                        "Somebody beat them to it. The van ride home was very quiet.")
            title = "💎 THE CREW PULLED THE FULL SWEEP" if lobby.is_house else "🚐💰 THE JOB PAID"
            await self._edit(message, discord.Embed(
                title=title, description=log + body, color=discord.Color.gold(),
            ))
        else:
            if lobby.is_house:
                headline = random.choice(HOUSE_FAIL_MESSAGES)
                escape_rate = HOUSE_ESCAPE_RATE
                jail_lo, jail_hi = HOUSE_JAIL_MIN_SECONDS, HOUSE_JAIL_MAX_SECONDS
                reason = "Crew job on the house vault went sideways"
            else:
                headline = random.choice(FAIL_MESSAGES).format(victim=victim.display_name)
                escape_rate = ESCAPE_RATE
                jail_lo, jail_hi = JAIL_MIN_SECONDS, JAIL_MAX_SECONDS
                reason = f"Crew heist on {victim.display_name} went sideways"
            lines = [f"🚨 **{headline}**", ""]
            for m in crew:
                if random.random() < escape_rate:
                    lines.append(random.choice(ESCAPE_LINES).format(member=m.mention))
                else:
                    seconds = random.randint(jail_lo, jail_hi)
                    if lobby.is_house:
                        wealth = economy.get_wealth(guild_id, m.id)
                        bail = min(HOUSE_BAIL_CAP,
                                   max(BAIL_AMOUNT, int(wealth * HOUSE_BAIL_WALLET_PCT)))
                    else:
                        bail = BAIL_AMOUNT
                    economy.jail_user(
                        guild_id, m.id, seconds,
                        reason=reason, bail_amount=bail, channel_id=channel_id,
                    )
                    if seconds >= 3600:
                        stretch = f"**{max(1, round(seconds / 3600))} hours**"
                    else:
                        stretch = f"**{max(1, seconds // 60)} minutes**"
                    lines.append(random.choice(CAUGHT_LINES).format(member=m.mention) +
                                 f" {stretch} in casino jail (bail {bail:,}).")
            if fee_total > 0:
                lines.append("")
                lines.append(f"**{lobby.starter.display_name}** still pockets the "
                             f"**{fee_total:,}** coins in recruiting fees. Obviously.")
            await self._edit(message, discord.Embed(
                title="🚔 THE JOB WENT SIDEWAYS", description=log + "\n".join(lines),
                color=discord.Color.dark_red(),
            ))

    def _stretch(self, seconds: int) -> str:
        if seconds >= 3600:
            return f"**{max(1, round(seconds / 3600))} hours**"
        return f"**{max(1, seconds // 60)} minutes**"

    async def _run_box_job(self, lobby: CrewLobby, message: discord.Message | None, channel_id: int):
        """The safe-deposit-box job: same lobby, same fees, same cooldown as a
        vault job — but the loot is ONE player's bank and the odds/take/bust
        profile comes from the chosen approach."""
        guild_id = lobby.guild_id
        crew = list(lobby.members)
        n = len(crew)
        account = lobby.account
        approach = lobby.approach
        a = BOX_APPROACHES[approach]

        # Re-check the box: the owner may have withdrawn while the crew assembled.
        banked_now = economy.bank_balance(guild_id, account.id)
        if banked_now < BOX_MIN_BANK:
            self._refund_all(lobby)
            await self._edit(message, discord.Embed(
                title="🚐 Crew Heist — Target Skipped Town",
                description=(f"The crew rolled up and **{account.display_name}**'s box was down to "
                             f"**{banked_now:,}** coins — they withdrew while the van was warming up. "
                             f"Not worth the gas. **Buy-ins refunded.**"),
                color=discord.Color.dark_grey(),
            ))
            return

        # Job's ON: fees release to the ringleader, house-job cooldown starts.
        fee_total = sum(lobby.paid.get(m.id, CREW_BUYIN)
                        for m in lobby.members if m.id != lobby.starter.id)
        if fee_total > 0:
            economy.refund_from_house(guild_id, lobby.starter.id, fee_total)
        for m in crew:
            self._cooldowns[(guild_id, m.id)] = time.time() + HOUSE_COOLDOWN

        # The box owner's Heist Shield covers their box the same as their wallet.
        if economy.kv_get(guild_id, account.id, "heistshield", "active_date", "") == economy.today_str():
            await self._edit(message, discord.Embed(
                title="🛡️ Job Blocked!",
                description=(f"The crew reached **{account.display_name}**'s box — and it was wrapped in an "
                             f"active **Heist Shield**. The recruits are out **{CREW_BUYIN:,}** each and "
                             f"**{lobby.starter.display_name}** still pocketed the fees. Awkward van ride."),
                color=discord.Color.blue(),
            ))
            return

        box_no = (account.id % 900) + 100   # cosmetic "box number" — stable per player
        fmt = dict(starter=lobby.starter.mention, account=account.display_name,
                   crew_size=n, box=box_no)
        buildup = [line.format(**fmt) for line in BOX_BUILDUP[approach]]
        title = BOX_INPROGRESS_TITLE.format(emoji=a["emoji"], label=a["label"])
        revealed = []
        for line in buildup:
            revealed.append(line)
            await self._edit(message, discord.Embed(
                title=title, description="\n".join(revealed), color=discord.Color.dark_grey(),
            ))
            await asyncio.sleep(REVEAL_DELAY)

        success = random.random() < _box_success_rate(approach, n)
        for m in crew:
            economy.record_game(guild_id, m.id, "crewheist", success)

        log = "\n".join(buildup) + "\n\n"
        if success:
            lo, hi = _box_take_bounds(approach)
            take_pct = random.uniform(lo, hi)
            # Re-read right before moving money — the buildup takes a few seconds.
            banked = economy.bank_balance(guild_id, account.id)
            loot = max(0, int(banked * take_pct))
            share = loot // n
            body = None
            if share > 0:
                remainder = loot - share * n
                payments = [(m.id, share + (remainder if m.id == lobby.starter.id else 0)) for m in crew]
                res = economy.bank_box_disburse(guild_id, account.id, payments)
                if res.get("ok"):
                    loot = res["total"]
                    paid = dict(res["paid"])
                    economy.kv_set(guild_id, account.id, "heistins", "last_loss",
                                   f"{loot}:{int(time.time())}")
                    headline = random.choice(BOX_SUCCESS_MESSAGES[approach]).format(
                        amount=loot, pct=int(round(take_pct * 100)), **fmt)
                    paid_lines = [f"💰 {m.mention} pockets **{paid.get(m.id, 0):,}** coins." for m in crew]
                    body = (f"✅ **{headline}**\n\n" + "\n".join(paid_lines) +
                            f"\n\n({int(round(take_pct * 100))}% of the box, {n}-way split. "
                            f"{account.mention}, your safe-deposit box just got crewed. The house is furious.)")
            if body is None:
                body = (f"✅ The crew got the box open… and **{account.display_name}** had already emptied it. "
                        "Somebody tipped them off. The van ride home was very quiet.")
            await self._edit(message, discord.Embed(
                title=f"🏦🔓 THE BOX IS OPEN — {a['label'].upper()}",
                description=log + body, color=discord.Color.gold(),
            ))
            return

        headline = random.choice(BOX_FAIL_MESSAGES[approach]).format(**fmt)
        jail_lo, jail_hi = a["jail"]
        lines = [f"🚨 **{headline}**", ""]
        for m in crew:
            if random.random() < a["escape"]:
                lines.append(random.choice(BOX_ESCAPE_LINES[approach]).format(member=m.mention))
                continue
            seconds = random.randint(jail_lo, jail_hi)
            wealth = economy.get_wealth(guild_id, m.id)
            bail = min(HOUSE_BAIL_CAP, max(BAIL_AMOUNT, int(wealth * HOUSE_BAIL_WALLET_PCT)))
            economy.jail_user(
                guild_id, m.id, seconds,
                reason=f"Crew job on {account.display_name}'s safe-deposit box went sideways ({a['label']})",
                bail_amount=bail, channel_id=channel_id,
            )
            line = (random.choice(BOX_CAUGHT_LINES[approach]).format(member=m.mention) +
                    f" {self._stretch(seconds)} in casino jail (bail {bail:,}).")
            if a["fine_pct"] > 0:
                fined = economy.fine_user_wealth(guild_id, m.id, int(wealth * a["fine_pct"]))
                if fined > 0:
                    line += f" Counter-hacked for **{fined:,}** coins."
            lines.append(line)
        if fee_total > 0:
            lines.append("")
            lines.append(f"**{lobby.starter.display_name}** still pockets the "
                         f"**{fee_total:,}** coins in recruiting fees. Obviously.")
        await self._edit(message, discord.Embed(
            title=f"🚔 THE JOB WENT SIDEWAYS — {a['label'].upper()}",
            description=log + "\n".join(lines), color=discord.Color.dark_red(),
        ))

    async def _edit(self, message: discord.Message | None, embed: discord.Embed):
        if message is None:
            return
        try:
            await message.edit(content=None, embed=embed, view=None)
        except discord.HTTPException:
            pass

    # ---- commands ------------------------------------------------------------

    @commands.command(name="crewheist", aliases=["crew"])
    @commands.guild_only()
    async def crewheist_prefix(self, ctx, victim: discord.Member = None,
                               account: discord.Member = None, approach: str = None):
        """Recruit a crew (1M/recruit, paid to you) to hit a player, the whole casino
        (vault + every bank account), or — `!crewheist @bot @player
        <physical|cyber|social|inside>` — one player's safe-deposit box."""
        await self._start(ctx, victim, account, approach)

    @app_commands.command(name="crewheist", description=f"Recruit a crew ({CREW_BUYIN:,}/recruit, paid to you) to hit a player, the whole casino, or one player's bank box")
    @app_commands.describe(
        target="The player whose stash you're hitting — or the bot for the full sweep (vault + every bank account)",
        account="(bot jobs only) Whose safe-deposit box — their bank account — the crew cracks instead of the vault",
        approach="(bot + account only) How the crew goes in; each trades odds vs take vs how ugly a bust gets",
    )
    @app_commands.choices(approach=[
        app_commands.Choice(name=f"{a['emoji']} {a['label']} — {a['blurb']}"[:100], value=key)
        for key, a in BOX_APPROACHES.items()
    ])
    async def crewheist_slash(self, interaction: discord.Interaction, target: discord.Member,
                              account: discord.Member | None = None,
                              approach: app_commands.Choice[str] | None = None):
        await self._start(interaction, target, account, approach.value if approach else None)


async def setup(bot):
    await bot.add_cog(CrewHeist(bot))
