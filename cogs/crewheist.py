import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
import logging
import time

import economy

logger = logging.getLogger(__name__)

# Crew Heist — the multiplayer job. One player cases a target, then recruits a
# crew: every member (starter included) antes CREW_BUYIN into the house as the
# cost of doing business (bribes, ski masks, a van that smells like regret).
# Buy-ins are NEVER returned once the job launches — win or lose, the house
# keeps its cut. More crew = better odds AND a bigger slice of the victim's
# wallet, but a bust sends everyone who doesn't slip away to casino jail.
#
# Money flow (per CLAUDE.md):
#   - buy-in:  transfer_to_house(is_bet=False) — a fee, not a stake, so it
#     doesn't distort the weekly-tax net_won basis.
#   - dissolve/cancel/timeout: refund_from_house — exact undo, no stat bumps.
#   - loot: disburse(victim -> crew) — pure player↔player, atomic.
# The house is NOT a valid target — that's solo /heist @bot territory.

CREW_BUYIN = 10_000
CREW_MIN_CREW = 2            # starter + at least one recruit
CREW_MAX_CREW = 3
LOBBY_TIMEOUT = 180          # seconds before an unlaunched lobby dissolves

MIN_VICTIM_COINS = 100_000   # below this the job isn't worth the buy-ins

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

CREW_COOLDOWN = 3 * 60 * 60  # per member, started when a job LAUNCHES

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

LOBBY_TITLE = "🚐 Crew Heist — Recruiting"
INPROGRESS_TITLE = "🚐 The Job Is On…"


def _success_rate(crew_size: int) -> float:
    return min(SUCCESS_RATE_CAP,
               BASE_SUCCESS_RATE + PER_MEMBER_BONUS * (crew_size - CREW_MIN_CREW))


def _steal_pct_bounds(crew_size: int) -> tuple[float, float]:
    extra = crew_size - CREW_MIN_CREW
    lo = min(STEAL_CAP_PCT, STEAL_MIN_PCT + PER_MEMBER_STEAL_LO * extra)
    hi = min(STEAL_CAP_PCT, STEAL_MAX_PCT + PER_MEMBER_STEAL_HI * extra)
    return lo, hi


class CrewLobby:
    def __init__(self, guild_id: int, channel_id: int,
                 starter: discord.Member, victim: discord.Member):
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.starter = starter
        self.victim = victim
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
        for m in lobby.members:
            economy.refund_from_house(lobby.guild_id, m.id, CREW_BUYIN)

    def _cooldown_remaining(self, guild_id: int, user_id: int) -> int:
        last = self._cooldowns.get((guild_id, user_id), 0)
        return max(0, int(CREW_COOLDOWN - (time.time() - last)))

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
        rate = int(_success_rate(max(n, CREW_MIN_CREW)) * 100)
        lo, hi = _steal_pct_bounds(max(n, CREW_MIN_CREW))
        crew_lines = "\n".join(f"• {m.mention}" + (" — ringleader" if m.id == lobby.starter.id else "")
                               for m in lobby.members)
        desc = (
            f"**{lobby.starter.display_name}** is putting a crew together to hit "
            f"**{lobby.victim.display_name}**'s stash.\n\n"
            f"**Buy-in:** {CREW_BUYIN:,} coins — the house keeps it, win or lose.\n"
            f"**Crew ({n}/{CREW_MAX_CREW}):**\n{crew_lines}\n\n"
            f"**Current odds:** {rate}% • **Take:** {int(lo * 100)}–{int(hi * 100)}% of the stash, split evenly.\n"
            f"A full crew of **{CREW_MAX_CREW}** runs {int(_success_rate(CREW_MAX_CREW) * 100)}% odds for "
            f"**{int(_steal_pct_bounds(CREW_MAX_CREW)[0] * 100)}–{int(_steal_pct_bounds(CREW_MAX_CREW)[1] * 100)}%** "
            f"of everything they've got.\n"
            f"**A bust:** everyone rolls to slip away — the slow ones eat up to "
            f"{JAIL_MAX_SECONDS // 3600}h of casino jail (bail {BAIL_AMOUNT:,}).\n\n"
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
        if victim.bot:
            if self.bot.user and victim.id == self.bot.user.id:
                await reply("The house is a solo job — that's `/heist @me` territory. A crew just means more witnesses.")
            else:
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
        if economy.get_coins(guild.id, victim.id) < MIN_VICTIM_COINS:
            await reply(f"**{victim.display_name}**'s stash is under **{MIN_VICTIM_COINS:,}** coins. "
                        "Not worth the buy-ins — pick a richer mark.")
            return
        res = economy.transfer_to_house(guild.id, starter.id, CREW_BUYIN, is_bet=False)
        if not res.get("ok"):
            if res.get("error") == "broke":
                await reply(f"💸 The buy-in is **{CREW_BUYIN:,}** coins and you have **{res.get('have', 0):,}**. "
                            "Even the ringleader pays.")
            else:
                await reply("⚠️ Couldn't collect your buy-in. Try again.")
            return

        lobby = CrewLobby(guild.id, channel.id, starter, victim)
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

        # Target re-check: the mark may have gone broke (or gotten robbed) while
        # the crew was assembling. No job, no forfeits — everyone gets refunded.
        victim_coins = economy.get_coins(guild_id, victim.id)
        if victim_coins < MIN_VICTIM_COINS:
            self._refund_all(lobby)
            await self._edit(message, discord.Embed(
                title="🚐 Crew Heist — Target Skipped Town",
                description=(f"The crew rolled up and **{victim.display_name}**'s stash was down to "
                             f"**{victim_coins:,}** coins. Not worth the gas. **Buy-ins refunded.**"),
                color=discord.Color.dark_grey(),
            ))
            return

        # From here the job is ON — buy-ins belong to the house, cooldowns start.
        for m in crew:
            self._cooldowns[(guild_id, m.id)] = time.time()

        # Heist Shield: an activated shield blocks the whole crew. Buy-ins are
        # forfeit — you cased a hardened target, that's on the ringleader.
        if economy.kv_get(guild_id, victim.id, "heistshield", "active_date", "") == economy.today_str():
            await self._edit(message, discord.Embed(
                title="🛡️ Job Blocked!",
                description=(f"The crew hit **{victim.display_name}**'s place — and bounced straight off an "
                             f"active **Heist Shield**. {n} buy-ins, gone. The house sends its regards."),
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

        success = random.random() < _success_rate(n)
        for m in crew:
            economy.record_game(guild_id, m.id, "crewheist", success)

        log = "\n".join(buildup) + "\n\n"
        if success:
            lo, hi = _steal_pct_bounds(n)
            steal_pct = random.uniform(lo, hi)
            # Re-read right before moving money — the buildup takes a few seconds.
            victim_coins = economy.get_coins(guild_id, victim.id)
            loot = max(0, int(victim_coins * steal_pct))
            share = loot // n
            paid_lines = []
            if share > 0:
                remainder = loot - share * n
                payments = [(m.id, share + (remainder if m.id == lobby.starter.id else 0)) for m in crew]
                res = economy.disburse(guild_id, victim.id, payments)
                if res.get("ok"):
                    economy.kv_set(guild_id, victim.id, "heistins", "last_loss",
                                   f"{loot}:{int(time.time())}")
                    paid_lines = [f"💰 {m.mention} pockets **{amt:,}** coins."
                                  for m, (_, amt) in zip(crew, payments)]
                else:
                    loot = 0
            if loot > 0 and paid_lines:
                headline = random.choice(SUCCESS_MESSAGES).format(victim=victim.display_name, amount=loot)
                body = (f"✅ **{headline}**\n\n" + "\n".join(paid_lines) +
                        f"\n\n({int(round(steal_pct * 100))}% of the stash, {n}-way split. "
                        f"{victim.mention}, you just got crewed.)")
            else:
                body = (f"✅ The crew got in clean… and **{victim.display_name}**'s stash was already gone. "
                        "Somebody beat them to it. The van ride home was very quiet.")
            await self._edit(message, discord.Embed(
                title="🚐💰 THE JOB PAID", description=log + body, color=discord.Color.gold(),
            ))
        else:
            headline = random.choice(FAIL_MESSAGES).format(victim=victim.display_name)
            lines = [f"🚨 **{headline}**", ""]
            for m in crew:
                if random.random() < ESCAPE_RATE:
                    lines.append(random.choice(ESCAPE_LINES).format(member=m.mention))
                else:
                    seconds = random.randint(JAIL_MIN_SECONDS, JAIL_MAX_SECONDS)
                    economy.jail_user(
                        guild_id, m.id, seconds,
                        reason=f"Crew heist on {victim.display_name} went sideways",
                        bail_amount=BAIL_AMOUNT, channel_id=channel_id,
                    )
                    mins = max(1, seconds // 60)
                    lines.append(random.choice(CAUGHT_LINES).format(member=m.mention) +
                                 f" **{mins} minutes** in casino jail (bail {BAIL_AMOUNT:,}).")
            lines.append("")
            lines.append(f"The house keeps all **{n * CREW_BUYIN:,}** coins of buy-ins. Obviously.")
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
        """Recruit a crew (10k buy-in each) to hit another player's stash."""
        await self._start(ctx, victim)

    @app_commands.command(name="crewheist", description=f"Recruit a crew ({CREW_BUYIN:,}/head) to hit a player's stash — bigger crew, bigger take")
    @app_commands.describe(target="The player whose stash you're hitting (not the house)")
    async def crewheist_slash(self, interaction: discord.Interaction, target: discord.Member):
        await self._start(interaction, target)


async def setup(bot):
    await bot.add_cog(CrewHeist(bot))
