import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import logging
import time
import economy
from items import HEIST_SHIELD

logger = logging.getLogger(__name__)

# Heist outcomes when SOLO
SOLO_SUCCESS_RATE = 0.35  # 35% chance to succeed alone

SOLO_SUCCESS_MESSAGES = [
    "snuck in through the back door and grabbed {amount:,} coins from {victim}'s wallet!",
    "distracted {victim} with a meme and swiped {amount:,} coins!",
    "hacked into {victim}'s account and transferred {amount:,} coins!",
    "pickpocketed {amount:,} coins from {victim} while they were AFK!",
    "found {victim}'s password written on a sticky note and took {amount:,} coins!",
    "used social engineering to convince {victim}'s bank to wire {amount:,} coins!",
    "crawled through the ventilation ducts and escaped with {amount:,} coins from {victim}!",
    "deployed a trojan horse meme to siphon {amount:,} coins from {victim}!",
    "posed as {victim}'s therapist and billed {amount:,} coins per session (one session long)!",
    "slid a fake QR code into {victim}'s DMs. They scanned it during a Zoom meeting. {amount:,} coins richer.",
    "returned {victim}'s own delivery package back to Amazon for a refund. {amount:,} coins and zero shame.",
    "put on a high-vis vest and walked into {victim}'s house like they worked there. Out with {amount:,} coins.",
    "forged {victim}'s signature on a birthday card, said it was 'IOU'. It worked. {amount:,} coins.",
    "booked a fake wedding with {victim} as guest of honor. They RSVP'd 'YES (w/ gift)'. {amount:,} coins.",
    "convinced {victim} they owed back-HOA fees. Billed them {amount:,} coins. They paid. They always do.",
    "sold {victim}'s own laptop back to them at a discount. {amount:,} coins. Classic.",
    "impersonated {victim}'s dentist and 'charged' them {amount:,} for a fictional root canal.",
    "called {victim} posing as their own cousin Terry 'in a jam.' Terry does not exist. {amount:,} coins.",
    "swapped {victim}'s garage door opener with theirs. Took {amount:,} coins of stuff while {victim} was at work.",
    "set up a GoFundMe titled 'Help {victim} Through This Tough Time' — {victim} didn't know. {amount:,} coins raised.",
    "intercepted {victim}'s lottery ticket after it won. {amount:,} coins. Diabolical.",
    "enrolled {victim} in a Columbia House CD club circa 1997 with a forged signature. Pocketed {amount:,} coins.",
    "convinced {victim} their coins needed to be 'aired out.' Put them in the yard. Took them. {amount:,} coins.",
    "sold {victim} a timeshare to their own kitchen. {amount:,} coins later — confusing, but profitable.",
]

SOLO_FAIL_MESSAGES = [
    "tripped the alarm and got caught! Fined **{fine:,}** coins.",
    "got recognized by {victim}'s security cameras! Fined **{fine:,}** coins.",
    "accidentally robbed themselves somehow. Lost **{fine:,}** coins.",
    "slipped on a banana peel during the getaway. Fined **{fine:,}** coins.",
    "forgot to wear a mask. {victim} recognized them immediately. Fined **{fine:,}** coins.",
    "got distracted by a cat video mid-heist. Busted! Fined **{fine:,}** coins.",
    "left their ID at the crime scene. Amateur hour. Fined **{fine:,}** coins.",
    "was caught when their phone rang during the heist. Fined **{fine:,}** coins.",
    "tried to bribe a guard dog. The dog was not only incorruptible, it tipped off the feds. Fined **{fine:,}**.",
    "used 'password' as the password guess. {victim} uses '12345'. Close, but no. **{fine:,}** coins gone.",
    "fell into a koi pond during the getaway. Drenched. Busted. **{fine:,}** coins fined.",
    "dropped a crumpled CVS receipt with their name on it. Fined **{fine:,}** coins.",
    "accidentally filmed the entire heist on iPhone vertical mode and posted it to TikTok. Fined **{fine:,}** coins. 2.3M likes.",
    "stepped on a squeaky toy in {victim}'s hallway. Dog barked. SWAT arrived. **{fine:,}** fine.",
    "tried to rob a SmartHome. It called {victim}'s mother. She was worse than the cops. **{fine:,}** coins.",
    "misjudged the roof drop. Landed directly on {victim}'s Ring camera. It's on the news. **{fine:,}**.",
    "asked Siri how to commit a heist. Siri told a cop. **{fine:,}** coins.",
    "brought the wrong duffel bag. It's full of rejected fan mail. Lose **{fine:,}**.",
    "forgot to bring a bag. Lost everything carrying coins in their pants. Fined **{fine:,}**.",
    "tried to escape through a doggy door. Not a dog. Fined **{fine:,}** coins.",
    "left a trail of Hot Cheeto dust straight to their apartment. Fined **{fine:,}**.",
    "wore a mask that said their full name in Comic Sans across the forehead. Fined **{fine:,}**.",
    "lockpicked the wrong house. Neighbors were VERY welcoming. Fined **{fine:,}** in awkward conversation.",
    "triggered the panic room FROM INSIDE the panic room. Fined **{fine:,}**.",
]

# Heist outcomes with ACCOMPLICE
DUO_SUCCESS_RATE = 0.55  # 55% chance with a partner

DUO_SUCCESS_MESSAGES = [
    "{thief} created a distraction while {accomplice} grabbed {amount:,} coins from {victim}!",
    "{thief} and {accomplice} pulled off a classic bait-and-switch on {victim} for {amount:,} coins!",
    "{thief} hacked the mainframe while {accomplice} downloaded {amount:,} coins from {victim}!",
    "{accomplice} drove the getaway car while {thief} snagged {amount:,} coins from {victim}!",
    "{thief} and {accomplice} executed a flawless Ocean's Two heist on {victim} for {amount:,} coins!",
    "{accomplice} cut the power while {thief} raided {victim}'s vault for {amount:,} coins!",
    "{thief} posed as IT support while {accomplice} cleaned out {victim}'s account for {amount:,} coins!",
    "{thief} and {accomplice} tunneled into {victim}'s vault and escaped with {amount:,} coins!",
    "{thief} dressed as a pizza guy. {accomplice} dressed as a second pizza guy. {victim} took both pizzas AND paid {amount:,}.",
    "{thief} and {accomplice} staged a fake flash mob outside {victim}'s window. Emptied the place. {amount:,} coins.",
    "{accomplice} faked a medical emergency outside {victim}'s door. {thief} walked out with {amount:,} under a lab coat.",
    "{thief} started a HOA meeting across town. {accomplice} looted {victim}'s place at leisure. {amount:,} coins.",
    "{thief} befriended {victim}'s dog. {accomplice} befriended {victim}. Took {amount:,} under no one's nose.",
    "{thief} did a Tom Cruise dangle. {accomplice} held the rope AND a burrito. {amount:,} coins.",
    "{thief} and {accomplice} staged a kids' lemonade stand outside {victim}'s house as a front. {amount:,} in 'donations.'",
    "{accomplice} impersonated {victim} at the bank. {thief} impersonated {victim}'s accountant. Wired out {amount:,}.",
    "{thief} hosted a surprise birthday party for {victim}. Half the neighbors showed up. {accomplice} robbed the house during cake. {amount:,} coins.",
    "{thief} replaced every clock in {victim}'s house with one 3 hours fast. {accomplice} helped clean up the confusion. {amount:,} coins.",
]

DUO_FAIL_MESSAGES = [
    "{thief} and {accomplice} couldn't agree on the plan and got caught! Both fined **{fine:,}** coins.",
    "{accomplice} sneezed during the heist, alerting {victim}. Both fined **{fine:,}** coins.",
    "{thief} accidentally texted the plan to {victim}. Busted! Both fined **{fine:,}** coins.",
    "{accomplice} locked the keys in the getaway car. Both fined **{fine:,}** coins.",
    "{thief} and {accomplice} showed up wearing matching outfits. Instantly suspicious. Both fined **{fine:,}** coins.",
    "{accomplice} livestreamed the heist by accident. Both fined **{fine:,}** coins.",
    "{thief} tried to high-five {accomplice} mid-heist and knocked over a shelf. Both fined **{fine:,}** coins.",
    "{accomplice} got hungry and stopped at the victim's fridge. Both caught! Fined **{fine:,}** coins.",
    "{thief} and {accomplice} started arguing about who should hold the flashlight. Got caught mid-argument. Fined **{fine:,}**.",
    "{accomplice} live-tweeted the heist 'for the memes.' Both fined **{fine:,}** coins.",
    "{thief} had earbuds in. Didn't hear the alarm. {accomplice} was trying to get their attention. Both fined **{fine:,}**.",
    "{accomplice} was allergic to {victim}'s cat. Sneezed 41 times in a row. Both fined **{fine:,}**.",
    "{thief} tried to vault over {victim}'s fence. It was chain link. It was ~2 feet tall. Both fined **{fine:,}**.",
    "{accomplice} accidentally voted in a local election during the heist. Left a paper trail. Both fined **{fine:,}**.",
    "{thief} and {accomplice} both went in through the same small window at the same time. Got stuck. Fined **{fine:,}**.",
    "{accomplice} brought their mom. {victim}'s mom happened to be home. They became friends. Heist abandoned. Fined **{fine:,}**.",
]

# Steal 5-15% of victim's coins on success, fine is 10-20% of thief's coins on fail
STEAL_MIN_PCT = 0.05
STEAL_MAX_PCT = 0.15
FINE_MIN_PCT = 0.10
FINE_MAX_PCT = 0.20

# Accomplice cut range
ACCOMPLICE_CUT_MIN = 0.10
ACCOMPLICE_CUT_MAX = 0.50

# Minimum coins the victim must have to be worth robbing
MIN_VICTIM_COINS = 50

# Cooldown in seconds (per user per guild)
HEIST_COOLDOWN = 300  # 5 minutes

# Rob-the-bot odds and punishment
BOT_HEIST_SUCCESS_RATE = 0.01  # 1% — 1-in-100 long shot
BOT_HEIST_JAIL_MIN_SECONDS = 1 * 60 * 60   # 1 hour
BOT_HEIST_JAIL_MAX_SECONDS = 36 * 60 * 60  # 36 hours
# Heist take is a uniform random fraction of on-hand within this band. Tune in
# economy.py so /pot can display the same range without a cross-cog import.
from economy import HOUSE_HEIST_MIN_PCT, HOUSE_HEIST_MAX_PCT

# Bail: someone ELSE pays a random share of the would-be loot to spring you.
# Multiplier grows with prior offenses, capped so it doesn't become unpayable.
BAIL_PCT_MIN = 0.25
BAIL_PCT_MAX = 1.00
BAIL_REPEAT_STEP = 0.25  # +25% per prior offense beyond the first
BAIL_REPEAT_CAP = 3.0    # 3× the base bail at most

# Hard ceiling — bail is capped at the LOWER of:
#   - BAIL_ECONOMY_CAP_PCT × the guild's total wallet coins (players + house), and
#   - BAIL_HARD_CAP (absolute ceiling).
# Stops repeat-offender bails from becoming unpayable in either a rich server
# (cap kicks in at 100M) or a small one (cap kicks in at 25% of all coins).
BAIL_ECONOMY_CAP_PCT = 0.25
BAIL_HARD_CAP = 100_000_000

# Accomplices are slippery — when a bot heist fails, the accomplice (NOT the
# thief) bolts and avoids jail with this probability. Encourages bringing one.
ACCOMPLICE_ESCAPE_RATE = 0.95

ACCOMPLICE_ESCAPE_FLAVOR = [
    "{accomplice} bolted through the kitchen and was out a side window before the bouncers turned the corner.",
    "{accomplice} ducked into a janitor closet, swapped jackets with a mop, and walked out whistling.",
    "{accomplice} blended into a passing bachelorette party and was three blocks away before anyone noticed.",
    "{accomplice} slipped a $20 to a cocktail waitress and got escorted out the staff entrance.",
    "{accomplice} climbed into a laundry cart and rolled to freedom. Smelled like towels for a week.",
    "{accomplice} simply walked. Calmly. Out the front door. Nobody questions confidence.",
    "{accomplice} faked a heart attack near the valet stand, hopped in their own car during the chaos, and peeled out.",
    "{accomplice} ghosted before security even hit the alarm. They were never even there. Allegedly.",
]

# How often the release-message loop scans for expired sentences.
RELEASE_SCAN_INTERVAL_SECONDS = 30

# Extend-jail: three preset purchase tiers. Capped at +24h total per sentence.
# Keyed by hours added, value is the cost. Non-linear by design.
EXTEND_OPTIONS = {
    1: 100_000_000,
    12: 1_000_000_000,
    24: 4_000_000_000,
}
EXTEND_MAX_TOTAL_SECONDS = 24 * 60 * 60

BOT_SUCCESS_MESSAGES = [
    "**{thief} ROBBED THE HOUSE.** They cracked **{pct}%** of the bot's vault and walked off with **{amount} coins**. The rest stayed bolted down.",
    "**{thief} SOMEHOW DID IT.** They cleared **{amount} coins** ({pct}% of on-hand) before the silent alarm tripped. The bot is rattled but solvent.",
    "**{thief} PULLED OFF A MIRACLE HEIST.** The bot stared blankly as **{amount} coins** — **{pct}%** of the vault — walked out the door.",
]

BOT_FAIL_MESSAGES = [
    "🚨 **{thief} tried to rob the casino.** The bot saw it coming from a mile away. Security dragged them off to **{hours} hours of casino jail**.",
    "🚨 **{thief} got caught robbing the HOUSE.** Every bouncer in the casino stomped them flat. **Jailed for {hours} hours.** No bets, no gambling.",
    "🚨 **{thief} thought they could out-bot the bot.** They could not. Straight to **casino jail, {hours} hours.**",
    "🚨 **The bot's security mainframe flagged {thief} mid-heist.** Trapped by a thousand dancing emojis. **Jailed for {hours} hours.**",
]

# Posted by the release-message loop when a sentence runs out and no one paid bail.
TIME_SERVED_MESSAGES = [
    "🔓 **{user}** served their entire sentence. No friends, no lawyer, no bail. Just time.",
    "🔓 **{user}** walked out of casino jail. Nobody came. Nobody posted. Cold.",
    "🔓 **{user}** did the full stretch. The casino has new respect for them. Maybe.",
    "🔓 **{user}** has been released. They counted every ceiling tile. Twice.",
    "🔓 **{user}** is back on the floor after doing the full bid. Welcome back.",
    "🔓 The casino doors open. **{user}** shuffles out, blinking. Their cellmate was a stack of dice.",
    "🔓 **{user}**'s sentence is up. They learned nothing. They're already eyeing the vault.",
    "🔓 **{user}** has been released. Their phone has 0 missed calls. Brutal.",
]

# Posted in-channel when someone pays bail.
BAIL_RELEASE_MESSAGES = [
    "💼 **{user}** has a good lawyer — out on bail, courtesy of **{payer}** ({amount} coins).",
    "💼 **{payer}** posted **{amount} coins** to bail **{user}** out of casino jail. Friendship has a price.",
    "💼 Bail set, bail paid. **{user}** walks free thanks to **{payer}**'s {amount}-coin generosity.",
    "💼 **{payer}** slid the bondsman **{amount} coins**. **{user}** is back on the floor. Owe them one.",
    "💼 **{user}** sweet-talked **{payer}** into covering **{amount} coins** of bail. Released.",
    "💼 The cell door clangs open. **{user}** thanks **{payer}** for the **{amount}-coin** wire. Suspiciously fast paperwork.",
]


class BotHeistConfirmView(discord.ui.View):
    """Confirmation prompt for robbing the house. Makes the risk explicit before any coins move."""

    def __init__(self, cog, guild_id: int, thief: discord.Member, victim: discord.Member, accomplice: discord.Member | None):
        super().__init__(timeout=30)
        self.cog = cog
        self.guild_id = guild_id
        self.thief = thief
        self.victim = victim
        self.accomplice = accomplice
        self.message: discord.Message | None = None
        self.resolved = False

    async def on_timeout(self):
        if self.resolved:
            return
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(content="⌛ Heist call timed out. {} backed away from the vault.".format(self.thief.display_name), embed=None, view=self)
            except discord.HTTPException:
                pass

    async def _reject_if_not_thief(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.thief.id:
            await interaction.response.send_message("Not your heist.", ephemeral=True)
            return True
        return False

    @discord.ui.button(label="Pull the heist", style=discord.ButtonStyle.danger, emoji="🎰")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._reject_if_not_thief(interaction):
            return
        self.resolved = True
        for child in self.children:
            child.disabled = True
        channel_id = interaction.channel_id or 0
        embed, jail_view = await self.cog._execute_bot_heist(self.guild_id, self.thief, self.victim, self.accomplice, channel_id)
        # On failure, the result embed gets its own action view (bail / extend).
        # The confirm view is now spent either way.
        if jail_view is not None:
            await interaction.response.edit_message(content=None, embed=embed, view=jail_view)
        else:
            await interaction.response.edit_message(content=None, embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="Back out", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._reject_if_not_thief(interaction):
            return
        self.resolved = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content=f"🚪 {self.thief.display_name} walked away from the vault. Wise choice.", embed=None, view=self)
        self.stop()


class _BailButton(discord.ui.Button):
    """Sits on the jail message. Anyone (other than the jailed user) can click."""

    def __init__(self, cog, target_id: int, target_name: str, bail_amount: int, row: int):
        super().__init__(
            label=f"Bail {target_name} ({bail_amount:,})",
            style=discord.ButtonStyle.success,
            emoji="💼",
            row=row,
            custom_id=f"heist:bail:{target_id}",
        )
        self.cog = cog
        self.target_id = target_id

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        target = guild.get_member(self.target_id)
        if target is None:
            try:
                target = await guild.fetch_member(self.target_id)
            except (discord.NotFound, discord.HTTPException):
                await interaction.response.send_message("Couldn't find the jailed user anymore.", ephemeral=True)
                return
        text = await self.cog._do_bail(guild, interaction.user, target)
        await interaction.response.send_message(text)
        # If bail succeeded, retire this user's row of buttons on the original message.
        if economy.jail_remaining(guild.id, self.target_id) == 0 and isinstance(self.view, JailActionView):
            self.view.disable_target(self.target_id)
            try:
                await interaction.message.edit(view=self.view)
            except (discord.HTTPException, discord.NotFound):
                pass


class _ExtendOpenButton(discord.ui.Button):
    """Opens an ephemeral picker for extension tiers."""

    def __init__(self, cog, target_id: int, target_name: str, row: int):
        super().__init__(
            label=f"Extend {target_name}",
            style=discord.ButtonStyle.danger,
            emoji="⛓️",
            row=row,
            custom_id=f"heist:extend:{target_id}",
        )
        self.cog = cog
        self.target_id = target_id

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        target = guild.get_member(self.target_id)
        if target is None:
            try:
                target = await guild.fetch_member(self.target_id)
            except (discord.NotFound, discord.HTTPException):
                await interaction.response.send_message("Couldn't find the jailed user anymore.", ephemeral=True)
                return
        if target.id == interaction.user.id:
            await interaction.response.send_message("🚫 You can't extend your own sentence.", ephemeral=True)
            return
        view = ExtendOptionsView(self.cog, guild.id, interaction.user.id, target)
        await interaction.response.send_message(
            f"How long do you want to keep **{target.display_name}** locked up? Pick a tier:",
            view=view, ephemeral=True,
        )


class JailActionView(discord.ui.View):
    """Sits on the failure-embed message. Lets anyone bail or extend one of the jailed users."""

    def __init__(self, cog, guild_id: int, thief: discord.Member, thief_bail: int,
                 accomplice: discord.Member | None = None, accomplice_bail: int = 0):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.thief_id = thief.id
        self.accomplice_id = accomplice.id if accomplice else None
        self.add_item(_BailButton(cog, thief.id, thief.display_name, thief_bail, row=0))
        self.add_item(_ExtendOpenButton(cog, thief.id, thief.display_name, row=0))
        if accomplice and accomplice_bail > 0:
            self.add_item(_BailButton(cog, accomplice.id, accomplice.display_name, accomplice_bail, row=1))
            self.add_item(_ExtendOpenButton(cog, accomplice.id, accomplice.display_name, row=1))

    def disable_target(self, target_id: int):
        for child in list(self.children):
            cid = getattr(child, "custom_id", "") or ""
            if cid.endswith(f":{target_id}"):
                child.disabled = True


class _ExtendTierButton(discord.ui.Button):
    def __init__(self, cog, guild_id: int, payer_id: int, target: discord.Member, hours: int, cost: int):
        super().__init__(
            label=f"+{hours}h — {cost:,} coins",
            style=discord.ButtonStyle.primary,
        )
        self.cog = cog
        self.guild_id = guild_id
        self.payer_id = payer_id
        self.target = target
        self.hours = hours

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.payer_id:
            await interaction.response.send_message("This picker isn't for you.", ephemeral=True)
            return
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        ok, text = await self.cog._do_extend_jail(guild, interaction.user, self.target, self.hours)
        for child in self.view.children:
            child.disabled = True
        # Successful extensions need a public announcement so the target (and channel)
        # see what happened — the picker itself is ephemeral, hidden from everyone else.
        # Failures stay ephemeral to avoid leaking "X is broke" to the whole channel.
        if ok:
            await interaction.response.edit_message(content="✅ Extension applied — see the channel.", view=self.view)
            try:
                await interaction.followup.send(text)
            except discord.HTTPException:
                pass
        else:
            await interaction.response.edit_message(content=text, view=self.view)
        self.view.stop()


class ExtendOptionsView(discord.ui.View):
    def __init__(self, cog, guild_id: int, payer_id: int, target: discord.Member):
        super().__init__(timeout=60)
        for hours, cost in sorted(EXTEND_OPTIONS.items()):
            self.add_item(_ExtendTierButton(cog, guild_id, payer_id, target, hours, cost))


class Heist(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._cooldowns = {}  # (guild_id, user_id) -> timestamp

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Heist module has been loaded")

    def _check_cooldown(self, guild_id: int, user_id: int) -> int | None:
        """Returns seconds remaining if on cooldown, None if ready."""
        import time
        key = (guild_id, user_id)
        last = self._cooldowns.get(key, 0)
        now = time.time()
        remaining = int(HEIST_COOLDOWN - (now - last))
        if remaining > 0:
            return remaining
        return None

    def _set_cooldown(self, guild_id: int, user_id: int):
        import time
        self._cooldowns[(guild_id, user_id)] = time.time()

    def _build_bot_heist_warning(self, thief: discord.Member, victim: discord.Member, accomplice: discord.Member | None) -> discord.Embed:
        win_pct = BOT_HEIST_SUCCESS_RATE * 100
        min_h = BOT_HEIST_JAIL_MIN_SECONDS // 3600
        max_h = BOT_HEIST_JAIL_MAX_SECONDS // 3600
        desc = (
            f"⚠️ {thief.mention}, you're about to **rob the house**.\n\n"
            f"• **Win odds:** ~**{win_pct:.0f}%** (1 in 100). Win and you roll **{int(HOUSE_HEIST_MIN_PCT*100)}–{int(HOUSE_HEIST_MAX_PCT*100)}%** of the vault (uniform random — could be a scratch, could be a fortune).\n"
            f"• **Lose odds:** ~**{100 - win_pct:.0f}%**. Caught means **casino jail for a random {min_h}–{max_h} hours** — no bets, no gambling.\n"
            f"• A friend can **`/bail`** you out (once per week). Bail scales with the vault — and gets steeper every time you re-offend.\n"
        )
        if accomplice:
            esc_pct = int(ACCOMPLICE_ESCAPE_RATE * 100)
            desc += (
                f"• Your accomplice {accomplice.mention} has a **{esc_pct}% chance to slip the bust** if it goes south — "
                f"the remaining {100 - esc_pct}% they catch their own random sentence and bail.\n"
            )
        desc += "\nThe house almost always wins. Are you sure?"
        return discord.Embed(title="🏦 Robbing the House — Are You Sure?", description=desc, color=discord.Color.orange())

    def _bail_multiplier(self, offenses: int) -> float:
        """Repeat offenders pay more. Capped so it stays remotely payable."""
        if offenses <= 1:
            return 1.0
        return min(BAIL_REPEAT_CAP, 1.0 + BAIL_REPEAT_STEP * (offenses - 1))

    def _roll_bail(self, guild_id: int, vault_size: int, offenses: int) -> int:
        """Bail = random 25-100% of the vault × repeat multiplier, then capped at
        the LOWER of BAIL_HARD_CAP and BAIL_ECONOMY_CAP_PCT × total guild economy."""
        pct = random.uniform(BAIL_PCT_MIN, BAIL_PCT_MAX)
        rolled = int(vault_size * pct * self._bail_multiplier(offenses))
        econ_cap = int(economy.get_total_economy(guild_id) * BAIL_ECONOMY_CAP_PCT)
        effective_cap = BAIL_HARD_CAP
        if econ_cap > 0:
            effective_cap = min(effective_cap, econ_cap)
        return max(1, min(rolled, effective_cap))

    def _roll_jail_seconds(self) -> int:
        return random.randint(BOT_HEIST_JAIL_MIN_SECONDS, BOT_HEIST_JAIL_MAX_SECONDS)

    async def _execute_bot_heist(self, guild_id: int, thief: discord.Member, victim: discord.Member, accomplice: discord.Member | None, channel_id: int):
        """Run the bot heist after the player has confirmed. Returns (embed, view_or_none).
        On failure the view carries bail/extend buttons for the channel message."""
        victim_coins = economy.get_coins(guild_id, victim.id)
        success = random.random() < BOT_HEIST_SUCCESS_RATE

        self._set_cooldown(guild_id, thief.id)
        if accomplice:
            self._set_cooldown(guild_id, accomplice.id)
        economy.record_heist(guild_id, thief.id, success)
        if accomplice:
            economy.record_heist(guild_id, accomplice.id, success)

        if success:
            heist_pct = random.uniform(HOUSE_HEIST_MIN_PCT, HOUSE_HEIST_MAX_PCT)
            loot = max(1, int(victim_coins * heist_pct))
            economy.transfer_coins(guild_id, victim.id, thief.id, loot)
            msg = random.choice(BOT_SUCCESS_MESSAGES).format(
                thief=thief.mention, amount=f"{loot:,}", pct=int(round(heist_pct * 100)),
            )
            return discord.Embed(title="🏦 HOUSE ROBBED", description=msg, color=discord.Color.gold()), None

        # Failure: each participant gets their own random sentence + bail amount,
        # both scaled by their own prior bot-heist offenses.
        thief_offenses = economy.increment_bot_heist_offenses(guild_id, thief.id)
        thief_seconds = self._roll_jail_seconds()
        thief_bail = self._roll_bail(guild_id, victim_coins, thief_offenses)
        economy.jail_user(
            guild_id, thief.id, thief_seconds,
            reason="Attempted to rob the house",
            bail_amount=thief_bail, channel_id=channel_id,
        )

        thief_hours = max(1, round(thief_seconds / 3600))
        msg = random.choice(BOT_FAIL_MESSAGES).format(thief=thief.mention, hours=thief_hours)
        msg += f"\n\n💰 Bail set at **{thief_bail:,} coins** (offense #{thief_offenses}). Use the buttons below — or `/bail` — once per week, per inmate."

        # Accomplice: 95% chance to slip out of the bust entirely — no jail, no
        # offense bump, no bail. Only the thief eats the full consequence in that case.
        accomplice_jailed = False
        accomplice_bail = 0
        if accomplice:
            if random.random() < ACCOMPLICE_ESCAPE_RATE:
                escape_line = random.choice(ACCOMPLICE_ESCAPE_FLAVOR).format(accomplice=accomplice.mention)
                msg += f"\n\n🏃 {escape_line} **{accomplice.display_name}** walks free."
            else:
                acc_offenses = economy.increment_bot_heist_offenses(guild_id, accomplice.id)
                acc_seconds = self._roll_jail_seconds()
                accomplice_bail = self._roll_bail(guild_id, victim_coins, acc_offenses)
                economy.jail_user(
                    guild_id, accomplice.id, acc_seconds,
                    reason="Accomplice in house robbery",
                    bail_amount=accomplice_bail, channel_id=channel_id,
                )
                accomplice_jailed = True
                acc_hours = max(1, round(acc_seconds / 3600))
                msg += (
                    f"\n\n{accomplice.mention} caught their own **{acc_hours}-hour** sentence "
                    f"(offense #{acc_offenses}). Bail: **{accomplice_bail:,} coins**."
                )
        embed = discord.Embed(title="🚔 CAUGHT ROBBING THE HOUSE", description=msg, color=discord.Color.dark_red())
        # Only attach an accomplice row of bail/extend buttons if the accomplice
        # actually got jailed; otherwise there's no one to bail.
        view_accomplice = accomplice if accomplice_jailed else None
        view = JailActionView(self, guild_id, thief, thief_bail, view_accomplice, accomplice_bail)
        return embed, view

    async def _run_heist(self, guild_id: int, thief: discord.Member, victim: discord.Member, accomplice: discord.Member = None) -> tuple[discord.Embed, discord.ui.View | None]:
        """Validate and run a heist. Returns (embed, view). View is non-None when the caller must show a confirmation prompt before the heist resolves."""

        # Validation
        if thief.id == victim.id:
            return discord.Embed(description="You can't rob yourself!", color=discord.Color.red()), None

        if accomplice and accomplice.id == victim.id:
            return discord.Embed(description="Your accomplice can't be the victim!", color=discord.Color.red()), None

        if accomplice and accomplice.id == thief.id:
            return discord.Embed(description="You can't be your own accomplice!", color=discord.Color.red()), None

        # Rob-the-bot is allowed (victim.bot == True with victim == this bot).
        # Other bots are still off-limits — they don't have wallets you can touch.
        targeting_house = victim.id == self.bot.user.id if self.bot.user else False
        if victim.bot and not targeting_house:
            return discord.Embed(description="You can't rob that bot. No wallet, no dice.", color=discord.Color.red()), None

        # kev2tall is a memorial player. Trying to heist him doesn't rob him —
        # it backfires: the would-be thief's entire wallet is emptied into his
        # balance as penance. Framed as a "logic error" for flavor.
        if economy.is_memorial(victim.id):
            bal = economy.get_coins(guild_id, thief.id)
            if bal > 0:
                economy.transfer_coins(guild_id, thief.id, economy.MEMORIAL_USER_ID, bal)
            return discord.Embed(
                description=(
                    "There was a logic error trying to complete the heist against kev2tall. "
                    "I've gone ahead and taken care of your wallet. 🕊️"
                ),
                color=discord.Color.red(),
            ), None
        if economy.is_memorial(thief.id) or (accomplice and economy.is_memorial(accomplice.id)):
            return discord.Embed(description="kev2tall doesn't run heists anymore. Rest easy, brother. 🕊️", color=discord.Color.red()), None

        # Jail check (can't rob while jailed)
        jmsg = economy.jail_message(guild_id, thief.id)
        if jmsg:
            return discord.Embed(description=jmsg, color=discord.Color.red()), None
        if accomplice:
            jmsg = economy.jail_message(guild_id, accomplice.id)
            if jmsg:
                return discord.Embed(description=f"{accomplice.display_name} is in jail: {jmsg}", color=discord.Color.red()), None

        # Cooldown check
        remaining = self._check_cooldown(guild_id, thief.id)
        if remaining:
            minutes, seconds = divmod(remaining, 60)
            return discord.Embed(description=f"You're laying low after your last heist. Try again in **{minutes}m {seconds}s**.", color=discord.Color.red()), None

        if accomplice:
            remaining = self._check_cooldown(guild_id, accomplice.id)
            if remaining:
                minutes, seconds = divmod(remaining, 60)
                return discord.Embed(description=f"{accomplice.display_name} is laying low after their last heist. Try again in **{minutes}m {seconds}s**.", color=discord.Color.red()), None

        # Check balances
        victim_coins = economy.get_coins(guild_id, victim.id)
        thief_coins = economy.get_coins(guild_id, thief.id)

        if victim_coins < MIN_VICTIM_COINS:
            return discord.Embed(description=f"{victim.display_name} only has **{victim_coins:,}** coins. Not worth the risk!", color=discord.Color.red()), None

        # --- Robbing the house (the bot itself) ---
        # Don't auto-execute — surface the risk and require confirmation. The view will call _execute_bot_heist on confirm.
        if targeting_house:
            warning = self._build_bot_heist_warning(thief, victim, accomplice)
            view = BotHeistConfirmView(self, guild_id, thief, victim, accomplice)
            return warning, view

        # Heist Shield: a victim's shield auto-blocks one heist, then is spent.
        # Checked only here — after every other validation passed and a real
        # heist is about to resolve — so a shield is never wasted on a heist
        # that would have been rejected anyway.
        if economy.consume_item(guild_id, victim.id, HEIST_SHIELD):
            embed = discord.Embed(
                title="🛡️ Heist Blocked!",
                description=(
                    f"{thief.mention} crept up on **{victim.display_name}** — and walked "
                    f"straight into a **Heist Shield**. The attempt fizzles and the shield "
                    f"is spent."
                ),
                color=discord.Color.blue(),
            )
            self._set_cooldown(guild_id, thief.id)
            if accomplice is not None:
                self._set_cooldown(guild_id, accomplice.id)
            return embed, None

        is_duo = accomplice is not None
        success_rate = DUO_SUCCESS_RATE if is_duo else SOLO_SUCCESS_RATE
        success = random.random() < success_rate

        if success:
            # Calculate stolen amount
            steal_pct = random.uniform(STEAL_MIN_PCT, STEAL_MAX_PCT)
            stolen = max(1, int(victim_coins * steal_pct))

            economy.transfer_coins(guild_id, victim.id, thief.id, stolen)

            if is_duo:
                # Accomplice gets a cut
                cut_pct = random.uniform(ACCOMPLICE_CUT_MIN, ACCOMPLICE_CUT_MAX)
                cut = max(1, int(stolen * cut_pct))
                economy.transfer_coins(guild_id, thief.id, accomplice.id, cut)
                thief_take = stolen - cut

                msg_template = random.choice(DUO_SUCCESS_MESSAGES)
                msg = msg_template.format(thief=thief.mention, accomplice=accomplice.mention, victim=victim.display_name, amount=stolen)
                msg += f"\n\n{thief.display_name} keeps **{thief_take:,}** coins, {accomplice.display_name} gets a **{cut:,}** coin cut ({int(cut_pct * 100)}%)."
            else:
                msg_template = random.choice(SOLO_SUCCESS_MESSAGES)
                msg = f"{thief.mention} " + msg_template.format(victim=victim.display_name, amount=stolen)

            embed = discord.Embed(title="Heist Successful!", description=msg, color=discord.Color.green())

        else:
            # Calculate fine
            fine_pct = random.uniform(FINE_MIN_PCT, FINE_MAX_PCT)
            fine = max(1, int(thief_coins * fine_pct))

            economy.fine_user(guild_id, thief.id, fine)

            if is_duo:
                accomplice_coins = economy.get_coins(guild_id, accomplice.id)
                accomplice_fine = max(1, int(accomplice_coins * fine_pct))
                economy.fine_user(guild_id, accomplice.id, accomplice_fine)

                msg_template = random.choice(DUO_FAIL_MESSAGES)
                msg = msg_template.format(thief=thief.mention, accomplice=accomplice.mention, victim=victim.display_name, fine=fine)
                msg += f"\n\n{accomplice.display_name} was also fined **{accomplice_fine:,}** coins."
            else:
                msg_template = random.choice(SOLO_FAIL_MESSAGES)
                msg = f"{thief.mention} " + msg_template.format(victim=victim.display_name, fine=fine)

            embed = discord.Embed(title="Heist Failed!", description=msg, color=discord.Color.red())

        # Set cooldowns
        self._set_cooldown(guild_id, thief.id)
        if is_duo:
            self._set_cooldown(guild_id, accomplice.id)

        # Track stats
        economy.record_heist(guild_id, thief.id, success)
        if is_duo:
            economy.record_heist(guild_id, accomplice.id, success)

        return embed, None

    @commands.command(aliases=['rob', 'steal'])
    async def heist(self, ctx, victim: discord.Member = None, accomplice: discord.Member = None):
        """Rob another user's coins! Optionally bring an accomplice for better odds."""
        if victim is None:
            await ctx.send("Usage: `!heist @victim` or `!heist @victim @accomplice`")
            return
        embed, view = await self._run_heist(ctx.guild.id, ctx.author, victim, accomplice)
        if view is not None:
            msg = await ctx.send(embed=embed, view=view)
            view.message = msg
        else:
            await ctx.send(embed=embed)

    @app_commands.command(name="heist", description="Attempt to steal coins from another user")
    @app_commands.describe(
        victim="The person to rob",
        accomplice="Optional partner in crime (gets 10-50% cut, improves odds)"
    )
    async def heist_slash(self, interaction: discord.Interaction, victim: discord.Member, accomplice: discord.Member = None):
        embed, view = await self._run_heist(interaction.guild_id, interaction.user, victim, accomplice)
        if view is not None:
            await interaction.response.send_message(embed=embed, view=view)
            view.message = await interaction.original_response()
        else:
            await interaction.response.send_message(embed=embed)

    def _format_duration(self, seconds: int) -> str:
        h, rem = divmod(max(0, seconds), 3600)
        m, s = divmod(rem, 60)
        parts = []
        if h:
            parts.append(f"{h}h")
        if m:
            parts.append(f"{m}m")
        parts.append(f"{s}s")
        return " ".join(parts)

    def _format_jail_status(self, member: discord.Member) -> str:
        remaining = economy.jail_remaining(member.guild.id, member.id)
        if remaining <= 0:
            return f"✅ **{member.display_name}** is not in jail. Free to gamble."
        info = economy.get_jail_info(member.guild.id, member.id) or {}
        bail = info.get("bail_amount", 0)
        line = f"🚔 **{member.display_name}** is in casino jail for **{self._format_duration(remaining)}**."
        if bail and bail > 0:
            cd = economy.bail_cooldown_remaining(member.guild.id, member.id)
            if cd > 0:
                line += f"\n💰 Bail is **{bail:,} coins**, but they were already bailed recently — eligible again in **{self._format_duration(cd)}**."
            else:
                line += f"\n💰 Bail is **{bail:,} coins**. A friend can `/bail @{member.display_name}`."
        return line

    @commands.command(name="jail")
    @commands.guild_only()
    async def jail_prefix(self, ctx, member: discord.Member = None):
        """Check whether you (or someone else) is in casino jail."""
        target = member or ctx.author
        await ctx.send(self._format_jail_status(target))

    @app_commands.command(name="jail", description="Check casino jail status")
    @app_commands.describe(member="User to check (defaults to you)")
    async def jail_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        await interaction.response.send_message(self._format_jail_status(target))

    # ---- Inmate roster ---------------------------------------------------

    def _resolve_display_name(self, guild: discord.Guild, user_id: int) -> str:
        member = guild.get_member(user_id)
        if member:
            return member.display_name
        return f"User {user_id}"

    def _build_inmates_embed(self, guild: discord.Guild) -> discord.Embed:
        rows = economy.get_active_jails(guild.id)
        if not rows:
            return discord.Embed(
                title="🏛️ Casino Jail",
                description="✅ The cells are empty. Everyone's law-abiding right now.",
                color=discord.Color.green(),
            )

        embed = discord.Embed(
            title=f"🏛️ Casino Jail — {len(rows)} inmate{'s' if len(rows) != 1 else ''}",
            description="Sorted by soonest release.",
            color=discord.Color.dark_red(),
        )
        # Discord caps embeds at 25 fields. If we somehow get more inmates than
        # that, show the first 24 and note the overflow.
        display_rows = rows[:24]
        now = time.time()
        for row in display_rows:
            name = self._resolve_display_name(guild, row["user_id"])
            remaining = max(0, int(row["until_ts"] - now))
            reason = row["reason"] or "—"
            bail = row["bail_amount"]
            extended = row["extended_seconds"]
            value_lines = [
                f"**Crime:** {reason}",
                f"**Released in:** {self._format_duration(remaining)}",
            ]
            if bail and bail > 0:
                value_lines.append(f"**Bail:** {bail:,} coins")
            else:
                value_lines.append("**Bail:** _not available_")
            if extended and extended > 0:
                value_lines.append(f"**Sentence extended by:** {self._format_duration(extended)}")
            embed.add_field(name=name, value="\n".join(value_lines), inline=False)
        if len(rows) > len(display_rows):
            embed.set_footer(text=f"+ {len(rows) - len(display_rows)} more inmate(s) not shown")
        return embed

    @commands.command(name="inmates", aliases=["jailroster", "lockdown"])
    @commands.guild_only()
    async def inmates_prefix(self, ctx):
        """List every user currently sitting in casino jail."""
        await ctx.send(embed=self._build_inmates_embed(ctx.guild))

    @app_commands.command(name="inmates", description="List every user currently in casino jail")
    async def inmates_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self._build_inmates_embed(interaction.guild))

    # ---- Bail ------------------------------------------------------------

    async def _do_bail(self, guild: discord.Guild, payer: discord.Member, jailed: discord.Member) -> str:
        if jailed is None:
            return "Usage: `!bail @user` — pay someone's bail to spring them out of casino jail. If you're jailed, you can only bail yourself."
        if jailed.bot:
            return "The house doesn't accept bail for itself or its bouncers."
        # Rule: a jailed user may bail ONLY themselves out, not anyone else.
        payer_jailed = economy.jail_remaining(guild.id, payer.id) > 0
        is_self = jailed.id == payer.id
        if payer_jailed and not is_self:
            return "🚫 You're in jail. You can only bail **yourself** out — not anyone else. Make some calls."

        result = economy.pay_bail(guild.id, jailed.id, payer.id)
        if result["ok"]:
            amount = result["amount"]
            msg = random.choice(BAIL_RELEASE_MESSAGES).format(
                user=jailed.display_name, payer=payer.display_name, amount=f"{amount:,}",
            )
            return msg

        err = result.get("error")
        if err == "not_jailed":
            return f"✅ **{jailed.display_name}** isn't in casino jail. Save your coins."
        if err == "sentence_done":
            return f"✅ **{jailed.display_name}**'s sentence is already up. Hang tight — the doors will open momentarily."
        if err == "no_bail":
            return f"⛔ **{jailed.display_name}** doesn't have a bail set. They have to serve it out."
        if err == "cooldown":
            cd = result.get("cooldown_remaining", 0)
            return f"⏳ **{jailed.display_name}** was bailed out too recently. They're eligible again in **{self._format_duration(cd)}**."
        if err == "broke":
            return f"💸 You'd need **{result.get('need', 0):,} coins** to post bail. You have **{result.get('have', 0):,}**."
        return "⚠️ Bail attempt failed (database error). Try again in a moment."

    @commands.command(name="bail")
    @commands.guild_only()
    async def bail_prefix(self, ctx, member: discord.Member = None):
        """Pay another user's bail to release them from casino jail."""
        msg = await self._do_bail(ctx.guild, ctx.author, member)
        await ctx.send(msg)

    @app_commands.command(name="bail", description="Pay someone else's bail to release them from casino jail")
    @app_commands.describe(member="The jailed user you're bailing out")
    async def bail_slash(self, interaction: discord.Interaction, member: discord.Member):
        msg = await self._do_bail(interaction.guild, interaction.user, member)
        await interaction.response.send_message(msg)

    # ---- Extend jail ------------------------------------------------------

    def _extend_options_summary(self) -> str:
        return ", ".join(f"+{h}h = **{c:,}**" for h, c in sorted(EXTEND_OPTIONS.items()))

    async def _do_extend_jail(self, guild: discord.Guild, payer: discord.Member, target: discord.Member, hours: int) -> tuple[bool, str]:
        """Run an extension attempt. Returns (succeeded, message)."""
        if target is None:
            return False, f"Usage: `!extendjail @user <hours>` — options: {self._extend_options_summary()}."
        if target.bot:
            return False, "You can't extend a bot's sentence. They have nothing but time anyway."
        if target.id == payer.id:
            return False, "🚫 You can't extend your own sentence. Even Houdini didn't try that."
        if hours not in EXTEND_OPTIONS:
            return False, f"Pick one of the preset tiers: {self._extend_options_summary()}."

        additional_seconds = hours * 3600
        cost = EXTEND_OPTIONS[hours]
        result = economy.extend_jail(
            guild.id, target.id, payer.id,
            additional_seconds=additional_seconds, cost=cost,
            max_total_extension_seconds=EXTEND_MAX_TOTAL_SECONDS,
        )
        if result["ok"]:
            new_extended = result["extended_seconds"]
            return True, (
                f"⛓️ **{payer.display_name}** slipped the warden **{cost:,} coins** to keep "
                f"**{target.mention}** in their cell **+{hours}h** longer. "
                f"Total extension on this sentence: **{self._format_duration(new_extended)}** / "
                f"**{self._format_duration(EXTEND_MAX_TOTAL_SECONDS)}** cap."
            )

        err = result.get("error")
        if err == "not_jailed":
            return False, f"✅ **{target.display_name}** isn't in casino jail. Nothing to extend."
        if err == "sentence_done":
            return False, f"✅ **{target.display_name}**'s sentence is already over. The doors are opening."
        if err == "cap":
            already = result.get("already_extended", 0)
            return False, (
                f"⛓️ **{target.display_name}**'s sentence has already been extended "
                f"**{self._format_duration(already)}** of the **{self._format_duration(EXTEND_MAX_TOTAL_SECONDS)}** cap. "
                f"Adding {hours}h would blow past it."
            )
        if err == "broke":
            return False, f"💸 Extending **{target.display_name}** by **{hours}h** costs **{result.get('need', cost):,} coins**. You have **{result.get('have', 0):,}**."
        if err == "self":
            return False, "🚫 You can't extend your own sentence."
        if err == "memorial":
            return False, "🕊️ kev2tall doesn't do time. Leave the memorial be."
        if err == "invalid_amount":
            return False, "Pick a valid extension tier."
        return False, "⚠️ Extension failed (database error). Try again in a moment."

    @commands.command(name="extendjail", aliases=["lockup"])
    @commands.guild_only()
    async def extendjail_prefix(self, ctx, member: discord.Member = None, hours: int = 0):
        """Pay coins to keep someone in casino jail longer (preset tiers only)."""
        _ok, msg = await self._do_extend_jail(ctx.guild, ctx.author, member, hours)
        await ctx.send(msg)

    @app_commands.command(name="extendjail", description="Pay coins to keep someone in casino jail longer")
    @app_commands.describe(
        member="The jailed user whose sentence you want to extend",
        hours="Extension tier",
    )
    @app_commands.choices(hours=[
        app_commands.Choice(name="+1 hour — 100,000,000 coins", value=1),
        app_commands.Choice(name="+12 hours — 1,000,000,000 coins", value=12),
        app_commands.Choice(name="+24 hours — 4,000,000,000 coins", value=24),
    ])
    async def extendjail_slash(self, interaction: discord.Interaction, member: discord.Member, hours: app_commands.Choice[int]):
        _ok, msg = await self._do_extend_jail(interaction.guild, interaction.user, member, hours.value)
        await interaction.response.send_message(msg)

    # ---- Release-message loop --------------------------------------------

    async def cog_load(self):
        if not self._release_loop.is_running():
            self._release_loop.start()

    async def cog_unload(self):
        if self._release_loop.is_running():
            self._release_loop.cancel()

    @tasks.loop(seconds=RELEASE_SCAN_INTERVAL_SECONDS)
    async def _release_loop(self):
        try:
            expired = economy.get_expired_jails()
        except Exception:
            logger.exception("release loop: failed to scan expired jails")
            return
        for row in expired:
            guild_id = row["guild_id"]
            user_id = row["user_id"]
            channel_id = row["channel_id"]
            # Always clear the row, even if we can't announce — otherwise it lingers forever.
            try:
                if not channel_id:
                    economy.clear_expired_jail(guild_id, user_id)
                    continue
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        economy.clear_expired_jail(guild_id, user_id)
                        continue
                # Resolve a display name. Fall back to a mention if member isn't cached.
                display = None
                guild = self.bot.get_guild(guild_id)
                if guild:
                    member = guild.get_member(user_id)
                    if member:
                        display = member.display_name
                if display is None:
                    display = f"<@{user_id}>"
                text = random.choice(TIME_SERVED_MESSAGES).format(user=display)
                try:
                    await channel.send(text)
                except (discord.Forbidden, discord.HTTPException):
                    logger.warning(f"release loop: couldn't post release for user {user_id} in channel {channel_id}")
                economy.clear_expired_jail(guild_id, user_id)
            except Exception:
                logger.exception(f"release loop: error processing jail row guild={guild_id} user={user_id}")
                # Best-effort cleanup so the row doesn't keep failing.
                try:
                    economy.clear_expired_jail(guild_id, user_id)
                except Exception:
                    pass

    @_release_loop.before_loop
    async def _before_release_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Heist(bot))
