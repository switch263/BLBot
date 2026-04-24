import discord
from discord.ext import commands
from discord import app_commands
import random
import logging
import economy

logger = logging.getLogger(__name__)

# Heist outcomes when SOLO
SOLO_SUCCESS_RATE = 0.35  # 35% chance to succeed alone

SOLO_SUCCESS_MESSAGES = [
    "snuck in through the back door and grabbed {amount} coins from {victim}'s wallet!",
    "distracted {victim} with a meme and swiped {amount} coins!",
    "hacked into {victim}'s account and transferred {amount} coins!",
    "pickpocketed {amount} coins from {victim} while they were AFK!",
    "found {victim}'s password written on a sticky note and took {amount} coins!",
    "used social engineering to convince {victim}'s bank to wire {amount} coins!",
    "crawled through the ventilation ducts and escaped with {amount} coins from {victim}!",
    "deployed a trojan horse meme to siphon {amount} coins from {victim}!",
    "posed as {victim}'s therapist and billed {amount} coins per session (one session long)!",
    "slid a fake QR code into {victim}'s DMs. They scanned it during a Zoom meeting. {amount} coins richer.",
    "returned {victim}'s own delivery package back to Amazon for a refund. {amount} coins and zero shame.",
    "put on a high-vis vest and walked into {victim}'s house like they worked there. Out with {amount} coins.",
    "forged {victim}'s signature on a birthday card, said it was 'IOU'. It worked. {amount} coins.",
    "booked a fake wedding with {victim} as guest of honor. They RSVP'd 'YES (w/ gift)'. {amount} coins.",
    "convinced {victim} they owed back-HOA fees. Billed them {amount} coins. They paid. They always do.",
    "sold {victim}'s own laptop back to them at a discount. {amount} coins. Classic.",
    "impersonated {victim}'s dentist and 'charged' them {amount} for a fictional root canal.",
    "called {victim} posing as their own cousin Terry 'in a jam.' Terry does not exist. {amount} coins.",
    "swapped {victim}'s garage door opener with theirs. Took {amount} coins of stuff while {victim} was at work.",
    "set up a GoFundMe titled 'Help {victim} Through This Tough Time' — {victim} didn't know. {amount} coins raised.",
    "intercepted {victim}'s lottery ticket after it won. {amount} coins. Diabolical.",
    "enrolled {victim} in a Columbia House CD club circa 1997 with a forged signature. Pocketed {amount} coins.",
    "convinced {victim} their coins needed to be 'aired out.' Put them in the yard. Took them. {amount} coins.",
    "sold {victim} a timeshare to their own kitchen. {amount} coins later — confusing, but profitable.",
]

SOLO_FAIL_MESSAGES = [
    "tripped the alarm and got caught! Fined **{fine}** coins.",
    "got recognized by {victim}'s security cameras! Fined **{fine}** coins.",
    "accidentally robbed themselves somehow. Lost **{fine}** coins.",
    "slipped on a banana peel during the getaway. Fined **{fine}** coins.",
    "forgot to wear a mask. {victim} recognized them immediately. Fined **{fine}** coins.",
    "got distracted by a cat video mid-heist. Busted! Fined **{fine}** coins.",
    "left their ID at the crime scene. Amateur hour. Fined **{fine}** coins.",
    "was caught when their phone rang during the heist. Fined **{fine}** coins.",
    "tried to bribe a guard dog. The dog was not only incorruptible, it tipped off the feds. Fined **{fine}**.",
    "used 'password' as the password guess. {victim} uses '12345'. Close, but no. **{fine}** coins gone.",
    "fell into a koi pond during the getaway. Drenched. Busted. **{fine}** coins fined.",
    "dropped a crumpled CVS receipt with their name on it. Fined **{fine}** coins.",
    "accidentally filmed the entire heist on iPhone vertical mode and posted it to TikTok. Fined **{fine}** coins. 2.3M likes.",
    "stepped on a squeaky toy in {victim}'s hallway. Dog barked. SWAT arrived. **{fine}** fine.",
    "tried to rob a SmartHome. It called {victim}'s mother. She was worse than the cops. **{fine}** coins.",
    "misjudged the roof drop. Landed directly on {victim}'s Ring camera. It's on the news. **{fine}**.",
    "asked Siri how to commit a heist. Siri told a cop. **{fine}** coins.",
    "brought the wrong duffel bag. It's full of rejected fan mail. Lose **{fine}**.",
    "forgot to bring a bag. Lost everything carrying coins in their pants. Fined **{fine}**.",
    "tried to escape through a doggy door. Not a dog. Fined **{fine}** coins.",
    "left a trail of Hot Cheeto dust straight to their apartment. Fined **{fine}**.",
    "wore a mask that said their full name in Comic Sans across the forehead. Fined **{fine}**.",
    "lockpicked the wrong house. Neighbors were VERY welcoming. Fined **{fine}** in awkward conversation.",
    "triggered the panic room FROM INSIDE the panic room. Fined **{fine}**.",
]

# Heist outcomes with ACCOMPLICE
DUO_SUCCESS_RATE = 0.55  # 55% chance with a partner

DUO_SUCCESS_MESSAGES = [
    "{thief} created a distraction while {accomplice} grabbed {amount} coins from {victim}!",
    "{thief} and {accomplice} pulled off a classic bait-and-switch on {victim} for {amount} coins!",
    "{thief} hacked the mainframe while {accomplice} downloaded {amount} coins from {victim}!",
    "{accomplice} drove the getaway car while {thief} snagged {amount} coins from {victim}!",
    "{thief} and {accomplice} executed a flawless Ocean's Two heist on {victim} for {amount} coins!",
    "{accomplice} cut the power while {thief} raided {victim}'s vault for {amount} coins!",
    "{thief} posed as IT support while {accomplice} cleaned out {victim}'s account for {amount} coins!",
    "{thief} and {accomplice} tunneled into {victim}'s vault and escaped with {amount} coins!",
    "{thief} dressed as a pizza guy. {accomplice} dressed as a second pizza guy. {victim} took both pizzas AND paid {amount}.",
    "{thief} and {accomplice} staged a fake flash mob outside {victim}'s window. Emptied the place. {amount} coins.",
    "{accomplice} faked a medical emergency outside {victim}'s door. {thief} walked out with {amount} under a lab coat.",
    "{thief} started a HOA meeting across town. {accomplice} looted {victim}'s place at leisure. {amount} coins.",
    "{thief} befriended {victim}'s dog. {accomplice} befriended {victim}. Took {amount} under no one's nose.",
    "{thief} did a Tom Cruise dangle. {accomplice} held the rope AND a burrito. {amount} coins.",
    "{thief} and {accomplice} staged a kids' lemonade stand outside {victim}'s house as a front. {amount} in 'donations.'",
    "{accomplice} impersonated {victim} at the bank. {thief} impersonated {victim}'s accountant. Wired out {amount}.",
    "{thief} hosted a surprise birthday party for {victim}. Half the neighbors showed up. {accomplice} robbed the house during cake. {amount} coins.",
    "{thief} replaced every clock in {victim}'s house with one 3 hours fast. {accomplice} helped clean up the confusion. {amount} coins.",
]

DUO_FAIL_MESSAGES = [
    "{thief} and {accomplice} couldn't agree on the plan and got caught! Both fined **{fine}** coins.",
    "{accomplice} sneezed during the heist, alerting {victim}. Both fined **{fine}** coins.",
    "{thief} accidentally texted the plan to {victim}. Busted! Both fined **{fine}** coins.",
    "{accomplice} locked the keys in the getaway car. Both fined **{fine}** coins.",
    "{thief} and {accomplice} showed up wearing matching outfits. Instantly suspicious. Both fined **{fine}** coins.",
    "{accomplice} livestreamed the heist by accident. Both fined **{fine}** coins.",
    "{thief} tried to high-five {accomplice} mid-heist and knocked over a shelf. Both fined **{fine}** coins.",
    "{accomplice} got hungry and stopped at the victim's fridge. Both caught! Fined **{fine}** coins.",
    "{thief} and {accomplice} started arguing about who should hold the flashlight. Got caught mid-argument. Fined **{fine}**.",
    "{accomplice} live-tweeted the heist 'for the memes.' Both fined **{fine}** coins.",
    "{thief} had earbuds in. Didn't hear the alarm. {accomplice} was trying to get their attention. Both fined **{fine}**.",
    "{accomplice} was allergic to {victim}'s cat. Sneezed 41 times in a row. Both fined **{fine}**.",
    "{thief} tried to vault over {victim}'s fence. It was chain link. It was ~2 feet tall. Both fined **{fine}**.",
    "{accomplice} accidentally voted in a local election during the heist. Left a paper trail. Both fined **{fine}**.",
    "{thief} and {accomplice} both went in through the same small window at the same time. Got stuck. Fined **{fine}**.",
    "{accomplice} brought their mom. {victim}'s mom happened to be home. They became friends. Heist abandoned. Fined **{fine}**.",
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
BOT_HEIST_SUCCESS_RATE = 0.00001  # 0.001% — effectively a lottery ticket
BOT_HEIST_JAIL_SECONDS = 24 * 60 * 60  # 24 hours

BOT_SUCCESS_MESSAGES = [
    "**{thief} ROBBED THE HOUSE.** They cracked the bot's vault and walked off with the **entire pot of {amount} coins**. The casino is in ruins.",
    "**{thief} SOMEHOW DID IT.** The bot's wallet has been cleaned out. **{amount} coins.** Nobody saw this coming. Including the bot.",
    "**{thief} PULLED OFF A MIRACLE HEIST.** The bot stared blankly as **{amount} coins** walked out the door.",
]

BOT_FAIL_MESSAGES = [
    "🚨 **{thief} tried to rob the casino.** The bot saw it coming from a mile away. Security dragged them off to **24-hour casino jail**.",
    "🚨 **{thief} got caught robbing the HOUSE.** Every bouncer in the casino stomped them flat. **Jailed for 24 hours.** No bets, no gambling.",
    "🚨 **{thief} thought they could out-bot the bot.** They could not. Straight to **casino jail, 24 hours.**",
    "🚨 **The bot's security mainframe flagged {thief} mid-heist.** Trapped by a thousand dancing emojis. **Jailed for 24 hours.**",
]


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

    async def _run_heist(self, guild_id: int, thief: discord.Member, victim: discord.Member, accomplice: discord.Member = None) -> discord.Embed:
        """Execute a heist. Returns result embed."""

        # Validation
        if thief.id == victim.id:
            return discord.Embed(description="You can't rob yourself!", color=discord.Color.red())

        if accomplice and accomplice.id == victim.id:
            return discord.Embed(description="Your accomplice can't be the victim!", color=discord.Color.red())

        if accomplice and accomplice.id == thief.id:
            return discord.Embed(description="You can't be your own accomplice!", color=discord.Color.red())

        # Rob-the-bot is allowed (victim.bot == True with victim == this bot).
        # Other bots are still off-limits — they don't have wallets you can touch.
        targeting_house = victim.id == self.bot.user.id if self.bot.user else False
        if victim.bot and not targeting_house:
            return discord.Embed(description="You can't rob that bot. No wallet, no dice.", color=discord.Color.red())

        # Jail check (can't rob while jailed)
        jmsg = economy.jail_message(guild_id, thief.id)
        if jmsg:
            return discord.Embed(description=jmsg, color=discord.Color.red())
        if accomplice:
            jmsg = economy.jail_message(guild_id, accomplice.id)
            if jmsg:
                return discord.Embed(description=f"{accomplice.display_name} is in jail: {jmsg}", color=discord.Color.red())

        # Cooldown check
        remaining = self._check_cooldown(guild_id, thief.id)
        if remaining:
            minutes, seconds = divmod(remaining, 60)
            return discord.Embed(description=f"You're laying low after your last heist. Try again in **{minutes}m {seconds}s**.", color=discord.Color.red())

        if accomplice:
            remaining = self._check_cooldown(guild_id, accomplice.id)
            if remaining:
                minutes, seconds = divmod(remaining, 60)
                return discord.Embed(description=f"{accomplice.display_name} is laying low after their last heist. Try again in **{minutes}m {seconds}s**.", color=discord.Color.red())

        # Check balances
        victim_coins = economy.get_coins(guild_id, victim.id)
        thief_coins = economy.get_coins(guild_id, thief.id)

        if victim_coins < MIN_VICTIM_COINS:
            return discord.Embed(description=f"{victim.display_name} only has **{victim_coins}** coins. Not worth the risk!", color=discord.Color.red())

        # --- Robbing the house (the bot itself) ---
        if targeting_house:
            success = random.random() < BOT_HEIST_SUCCESS_RATE
            self._set_cooldown(guild_id, thief.id)
            if accomplice:
                self._set_cooldown(guild_id, accomplice.id)
            economy.record_heist(guild_id, thief.id, success)
            if accomplice:
                economy.record_heist(guild_id, accomplice.id, success)

            if success:
                loot = victim_coins  # take the whole vault
                economy.transfer_coins(guild_id, victim.id, thief.id, loot)
                msg = random.choice(BOT_SUCCESS_MESSAGES).format(
                    thief=thief.mention, amount=loot,
                )
                return discord.Embed(title="🏦 HOUSE ROBBED", description=msg, color=discord.Color.gold())

            # Failure: straight to jail
            economy.jail_user(guild_id, thief.id, BOT_HEIST_JAIL_SECONDS, reason="Attempted to rob the house")
            if accomplice:
                economy.jail_user(guild_id, accomplice.id, BOT_HEIST_JAIL_SECONDS, reason="Accomplice in house robbery")
            msg = random.choice(BOT_FAIL_MESSAGES).format(thief=thief.mention)
            if accomplice:
                msg += f"\n\n{accomplice.mention} was also dragged to jail for 24 hours."
            return discord.Embed(title="🚔 CAUGHT ROBBING THE HOUSE", description=msg, color=discord.Color.dark_red())

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
                msg += f"\n\n{thief.display_name} keeps **{thief_take}** coins, {accomplice.display_name} gets a **{cut}** coin cut ({int(cut_pct * 100)}%)."
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
                msg += f"\n\n{accomplice.display_name} was also fined **{accomplice_fine}** coins."
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

        return embed

    @commands.command(aliases=['rob', 'steal'])
    async def heist(self, ctx, victim: discord.Member = None, accomplice: discord.Member = None):
        """Rob another user's coins! Optionally bring an accomplice for better odds."""
        if victim is None:
            await ctx.send("Usage: `!heist @victim` or `!heist @victim @accomplice`")
            return
        embed = await self._run_heist(ctx.guild.id, ctx.author, victim, accomplice)
        await ctx.send(embed=embed)

    @app_commands.command(name="heist", description="Attempt to steal coins from another user")
    @app_commands.describe(
        victim="The person to rob",
        accomplice="Optional partner in crime (gets 10-50% cut, improves odds)"
    )
    async def heist_slash(self, interaction: discord.Interaction, victim: discord.Member, accomplice: discord.Member = None):
        embed = await self._run_heist(interaction.guild_id, interaction.user, victim, accomplice)
        await interaction.response.send_message(embed=embed)

    def _format_jail_status(self, member: discord.Member) -> str:
        remaining = economy.jail_remaining(member.guild.id, member.id)
        if remaining <= 0:
            return f"✅ **{member.display_name}** is not in jail. Free to gamble."
        h, rem = divmod(remaining, 3600)
        m, s = divmod(rem, 60)
        parts = []
        if h:
            parts.append(f"{h}h")
        if m:
            parts.append(f"{m}m")
        parts.append(f"{s}s")
        return f"🚔 **{member.display_name}** is in casino jail for **{' '.join(parts)}**."

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


async def setup(bot):
    await bot.add_cog(Heist(bot))
