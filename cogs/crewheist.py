import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
import logging
import time

import economy
from economy import HOUSE_HEIST_MIN_PCT, HOUSE_HEIST_MAX_PCT

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
# the take is the same capped band as a solo vault crack, split by the crew.

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
# Way, WAY worse odds than a player job — the vault pays a rolled cut of the
# house's ENTIRE on-hand pot (same HOUSE_HEIST band as solo /heist @bot, so the
# drain stays capped), so the win chance has to live near solo-heist territory
# (solo vault ≈ 0.8%), not lobby-game territory.
HOUSE_SUCCESS_RATES = {2: 0.02, 3: 0.04}   # crew size -> odds
HOUSE_ESCAPE_RATE = 0.20                    # the bot sees everything
HOUSE_JAIL_MIN_SECONDS = 1 * 60 * 60
HOUSE_JAIL_MAX_SECONDS = 24 * 60 * 60
HOUSE_BAIL_WALLET_PCT = 0.25                # bail = max(BAIL_AMOUNT, 25% of wealth: wallet + bank)
HOUSE_BAIL_CAP = 100_000_000
HOUSE_COOLDOWN = 6 * 60 * 60                # matches the solo /heist cooldown

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

HOUSE_FAIL_MESSAGES = [
    "The vault door didn't budge and the bot's security mainframe had already dialed everyone. Floodlights. Dogs. Regret.",
    "Turns out the 'blind spot' in the casino cameras was bait. The crew walked straight into it.",
    "Three steps into the counting room, every slot machine turned to face them. The house knew the whole time.",
]

LOBBY_TITLE = "🚐 Crew Heist — Recruiting"
INPROGRESS_TITLE = "🚐 The Job Is On…"


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


class CrewLobby:
    def __init__(self, guild_id: int, channel_id: int,
                 starter: discord.Member, victim: discord.Member, is_house: bool):
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.starter = starter
        self.victim = victim
        self.is_house = is_house
        self.members: list[discord.Member] = [starter]
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
        res = economy.transfer_to_house(lobby.guild_id, user.id, CREW_BUYIN, is_bet=False)
        if not res.get("ok"):
            if res.get("error") == "broke":
                await interaction.response.send_message(
                    f"💸 The buy-in is **{CREW_BUYIN:,}** coins and you have **{res.get('have', 0):,}**. "
                    "The crew doesn't do IOUs.", ephemeral=True)
            else:
                await interaction.response.send_message("⚠️ Couldn't collect your buy-in. Try again.", ephemeral=True)
            return
        lobby.members.append(user)
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
        economy.refund_from_house(lobby.guild_id, user.id, CREW_BUYIN)
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
                economy.refund_from_house(lobby.guild_id, m.id, CREW_BUYIN)

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
        if economy.is_memorial(user.id):
            return "kev2tall doesn't run jobs anymore. Rest easy, brother. 🕊️"
        if len(lobby.members) >= CREW_MAX_CREW:
            return f"The van only seats **{CREW_MAX_CREW}**."
        jmsg = economy.jail_message(lobby.guild_id, user.id)
        if jmsg:
            return jmsg
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
        if lobby.is_house:
            rate = _house_success_rate(eff)
            target_line = (f"**{lobby.starter.display_name}** is putting a crew together to hit "
                           f"**THE HOUSE VAULT**. Ambitious. Stupid. Both.")
            odds_line = (
                f"**Current odds:** {rate * 100:g}% — this is the vault, not somebody's sock drawer.\n"
                f"**The take:** {int(HOUSE_HEIST_MIN_PCT * 100)}–{int(HOUSE_HEIST_MAX_PCT * 100)}% of the house's "
                f"entire on-hand pot, split evenly.\n"
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

    async def _start(self, ctx_or_interaction, victim: discord.Member | None):
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
            await reply(f"Usage: `/crewheist target:@user` — recruit a crew ({CREW_BUYIN:,}/head) and hit their stash.")
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
        jmsg = economy.jail_message(guild.id, starter.id)
        if jmsg:
            await reply(jmsg)
            return
        cd = self._cooldown_remaining(guild.id, starter.id)
        if cd:
            h, rem = divmod(cd, 3600)
            m, s = divmod(rem, 60)
            await reply(f"You're laying low after your last job. Ready in **{h}h {m}m {s}s**.")
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
        self.active[channel.id] = lobby
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
        fee_total = (n - 1) * CREW_BUYIN
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
            if loot > 0 and paid_lines:
                headline = random.choice(success_pool).format(
                    victim=victim.display_name, amount=loot, pct=int(round(steal_pct * 100)))
                body = f"✅ **{headline}**\n\n" + "\n".join(paid_lines)
                if lobby.is_house:
                    body += f"\n\n({n}-way split. The house is furious.)"
                else:
                    body += (f"\n\n({int(round(steal_pct * 100))}% of the stash, {n}-way split. "
                             f"{victim.mention}, you just got crewed.)")
            else:
                body = (f"✅ The crew got in clean… and **{victim.display_name}**'s stash was already gone. "
                        "Somebody beat them to it. The van ride home was very quiet.")
            title = "🏦💎 THE CREW CRACKED THE VAULT" if lobby.is_house else "🚐💰 THE JOB PAID"
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
    async def crewheist_prefix(self, ctx, victim: discord.Member = None):
        """Recruit a crew (1M/recruit, paid to you) to hit a player — or the house vault."""
        await self._start(ctx, victim)

    @app_commands.command(name="crewheist", description=f"Recruit a crew ({CREW_BUYIN:,}/recruit, paid to you) to hit a player — or the house vault")
    @app_commands.describe(target="The player whose stash you're hitting — or the bot to try the house vault")
    async def crewheist_slash(self, interaction: discord.Interaction, target: discord.Member):
        await self._start(interaction, target)


async def setup(bot):
    await bot.add_cog(CrewHeist(bot))
