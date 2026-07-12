"""Big Sal, the loanshark. Borrow against the house pot, pay the vig, or find
out what happens to people who don't.

Money flow is a closed loop: the principal comes OUT of the house
(refund_from_house — no total_won/net_won bump, so loans aren't taxed as
winnings) and every repayment, juice payment, and seizure flows back in via
transfer_to_house(is_bet=False). Nothing is minted or burned; the vig is house
profit.

The debt escalates in stages once the due date passes (one per 12h, tracked in
the loan row so each fires exactly once even across restarts):

  stage 1 — the phone call:   juice added, public warning.
  stage 2 — the goons:        juice added, wallet shaken down for what's owed.
  stage 3 — the beating:      juice added, wallet AND bank cleaned out; still
                              short -> 12h in the hospital ward (jail, no bail).
  stage 4 — the harsh stuff:  everything you have is swept, the rest of the
                              debt is settled in blood: 48h jail that no Get
                              Out of Jail Free card can spring, and Sal won't
                              lend to you again for a week.

Juice is capped at MAX_OWED_MULT x principal, so a forgotten loan can't
compound into an unpayable number — per the house rule that no mechanic gets
an unbounded drain.

State lives in cog_kv namespace "loanshark": per-user "loan" (JSON row) and
"blacklist_until" (epoch). Borrowing is deliberately NOT jail-gated — Sal will
absolutely front bail money to a guy in a cell. The memorial player is refused
service and never enforced on.
"""
import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import logging
import math
import time

import random

import economy
from economy import (
    kv_get, kv_set, kv_delete,
    refund_from_house, transfer_to_house, bank_seize_to_house,
    get_coins, jail_user, jail_remaining, is_memorial,
)
from amount import parse_amount, amount_error

logger = logging.getLogger(__name__)

NAMESPACE = "loanshark"
SCAN_INTERVAL_MINUTES = 5

MIN_LOAN = 1_000
MAX_LOAN = 250_000
VIG_PCT = 0.30                    # borrow 100k, owe 130k
TERM_SECONDS = 48 * 3600          # pay within 2 days
JUICE_PCT = 0.10                  # +10% of the outstanding debt per stage missed
MAX_OWED_MULT = 3.0               # debt hard-capped at 3x principal
STAGE_GAP_SECONDS = 12 * 3600     # one escalation stage per 12h overdue
FINAL_STAGE = 4

BEATING_JAIL_SECONDS = 12 * 3600
KNEECAP_JAIL_SECONDS = 48 * 3600
BLACKLIST_SETTLED_SECONDS = 3 * 86400   # goons had to collect
BLACKLIST_BLOOD_SECONDS = 7 * 86400     # it went all the way

JOB_COOLDOWN_SECONDS = 6 * 3600
# (weight, cut_min, cut_max, jail_seconds, flavor) — cut is the fraction of the
# outstanding debt forgiven (negative = Sal adds to the tab). Forgiveness moves
# no coins; the vig was house profit that never existed yet.
JOB_OUTCOMES = [
    (16, 0.20, 0.35, 0,
     "You drive an unmarked van across three counties and ask zero questions. "
     "Sal knocks **{cut:,}** off the tab."),
    (12, 0.15, 0.30, 0,
     "You stand behind Sal at a meeting with your arms crossed for two hours. "
     "Didn't say a word. **{cut:,}** off the tab."),
    (10, 0.20, 0.35, 0,
     "You collect an envelope from a guy at the bowling alley who cries a "
     "little. **{cut:,}** off the tab."),
    (7, 0.35, 0.50, 0,
     "You talk a *different* debtor into paying Sal everything. He's so "
     "pleased he takes **{cut:,}** off your tab and calls you 'kid'."),
    (12, 0.0, 0.0, 0,
     "The job falls through — the guy you were supposed to lean on already "
     "skipped town. No harm done, but the tab doesn't move."),
    (6, -0.10, -0.10, 0,
     "You back the van into a fire hydrant with the merchandise inside. Sal "
     "adds **{cut:,}** to the tab and tells you to walk home."),
    (5, 0.0, 0.0, 45 * 60,
     "The cops roll up while you're casing the drop. You say nothing — Sal "
     "appreciates that — but you're doing 45 minutes in a cell and the tab "
     "doesn't move."),
]


def stage_for(now: float, due_ts: float) -> int:
    """Which escalation stage a loan should be at: 0 while current, then one
    stage per STAGE_GAP_SECONDS overdue, capped at FINAL_STAGE."""
    if now < due_ts:
        return 0
    return min(FINAL_STAGE, 1 + int((now - due_ts) // STAGE_GAP_SECONDS))


def apply_juice(owed: int, principal: int, stages: int) -> int:
    """Compound JUICE_PCT per stage crossed, capped at MAX_OWED_MULT x principal."""
    cap = int(principal * MAX_OWED_MULT)
    for _ in range(max(0, stages)):
        owed = math.ceil(owed * (1 + JUICE_PCT))
    return min(owed, cap)


class LoanShark(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        if not self._collection_loop.is_running():
            self._collection_loop.start()

    async def cog_unload(self):
        if self._collection_loop.is_running():
            self._collection_loop.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Loan Shark loaded.")

    # ---- state ------------------------------------------------------------

    def _get_loan(self, guild_id: int, user_id: int) -> dict | None:
        raw = kv_get(guild_id, user_id, NAMESPACE, "loan")
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"loanshark: dropping malformed loan row for user {user_id}")
            kv_delete(guild_id, user_id, NAMESPACE, "loan")
            return None

    def _save_loan(self, guild_id: int, user_id: int, loan: dict):
        kv_set(guild_id, user_id, NAMESPACE, "loan", json.dumps(loan))

    def _blacklist_until(self, guild_id: int, user_id: int) -> int:
        return int(kv_get(guild_id, user_id, NAMESPACE, "blacklist_until", 0) or 0)

    # ---- borrow -----------------------------------------------------------

    async def _borrow(self, guild, user, channel_id, raw_amount, reply):
        if is_memorial(user.id):
            await reply("🦈 Sal tips his hat and says this one's on the house. No loan needed.")
            return
        now = time.time()
        until = self._blacklist_until(guild.id, user.id)
        if until > now:
            await reply(f"🦈 Sal doesn't do business with you anymore. Come back <t:{int(until)}:R> — *maybe* he's forgotten.")
            return
        if self._get_loan(guild.id, user.id) is not None:
            await reply("🦈 One tab at a time. Pay what you owe (`!loan repay`) before you come sniffing for more.")
            return
        amount = parse_amount(raw_amount, available=MAX_LOAN)
        if amount is None:
            await reply(amount_error(raw_amount, contextual=True))
            return
        if amount < MIN_LOAN:
            await reply(f"🦈 Sal laughs in your face. He doesn't get out of his chair for less than **{MIN_LOAN:,}**.")
            return
        if amount > MAX_LOAN:
            await reply(f"🦈 Sal whistles. **{MAX_LOAN:,}** is the ceiling — he's a loanshark, not a bank.")
            return
        principal = refund_from_house(guild.id, user.id, amount)
        if principal <= 0:
            await reply("🦈 Sal turns his pockets out. Even the house is dry right now. Come back later.")
            return
        owed = int(principal * (1 + VIG_PCT))
        due = int(now + TERM_SECONDS)
        self._save_loan(guild.id, user.id, {
            "principal": principal,
            "owed": owed,
            "taken_ts": int(now),
            "due_ts": due,
            "stage": 0,
            "channel_id": channel_id,
        })
        short_note = "" if principal == amount else f"\n-# (House could only front {principal:,} of the {amount:,} you asked for.)"
        await reply(
            f"🦈 Sal counts out **{principal:,}** coins into your hand and doesn't blink.\n"
            f"You owe **{owed:,}** (that's the vig, {int(VIG_PCT * 100)}%, don't ask questions) "
            f"by <t:{due}:f> — <t:{due}:R>.\n"
            f"Pay with `!loan repay <amount>`. Miss the date and the number grows. "
            f"Keep missing it and... don't keep missing it.{short_note}"
        )

    # ---- repay ------------------------------------------------------------

    async def _repay(self, guild, user, raw_amount, reply):
        loan = self._get_loan(guild.id, user.id)
        if loan is None:
            await reply("🦈 You don't owe Sal anything. He finds that suspicious, but fine.")
            return
        owed = int(loan["owed"])
        wallet = get_coins(guild.id, user.id)
        amount = parse_amount(raw_amount, available=min(owed, wallet))
        if amount is None:
            await reply(amount_error(raw_amount, contextual=True))
            return
        amount = min(amount, owed)
        if amount <= 0:
            await reply("🦈 Sal stares at the empty envelope. Bring actual coins.")
            return
        res = transfer_to_house(guild.id, user.id, amount, is_bet=False)
        if not res.get("ok"):
            have = res.get("have", wallet)
            await reply(f"🦈 You're short — you owe a payment of **{amount:,}** but you're holding **{have:,}**. "
                        f"Sal suggests you go win some. Quickly.")
            return
        owed -= amount
        if owed <= 0:
            kv_delete(guild.id, user.id, NAMESPACE, "loan")
            on_time = time.time() < loan["due_ts"]
            if on_time:
                await reply(f"🦈 Paid in full — **{amount:,}** on the table. Sal nods once. "
                            f"You're good for it. Door's open next time.")
            else:
                await reply(f"🦈 Paid in full — **{amount:,}**, late, but paid. Sal pockets it "
                            f"and lets whatever was about to happen... not happen.")
            return
        loan["owed"] = owed
        self._save_loan(guild.id, user.id, loan)
        await reply(f"🦈 Sal takes your **{amount:,}** and marks the book. Still on the tab: "
                    f"**{owed:,}**, due <t:{int(loan['due_ts'])}:R>.")

    # ---- work off the debt ---------------------------------------------------

    async def _job(self, guild, user, channel_id, reply):
        loan = self._get_loan(guild.id, user.id)
        if loan is None:
            await reply("🦈 Sal looks you up and down. \"You don't owe me nothing. I don't hire "
                        "volunteers.\" Take a loan first (`!loan borrow`).")
            return
        if jail_remaining(guild.id, user.id) > 0:
            await reply("🦈 Sal's jobs happen on the *outside*. Finish your sentence first.")
            return
        now = time.time()
        last = float(kv_get(guild.id, user.id, NAMESPACE, "job_ts", 0) or 0)
        ready = last + JOB_COOLDOWN_SECONDS
        if now < ready:
            await reply(f"🦈 Sal's got nothing for you right now. Check back <t:{int(ready)}:R> — "
                        f"and don't call him, he calls you.")
            return
        kv_set(guild.id, user.id, NAMESPACE, "job_ts", int(now))

        weights = [o[0] for o in JOB_OUTCOMES]
        _w, cut_min, cut_max, jail_seconds, flavor = random.choices(JOB_OUTCOMES, weights=weights)[0]
        owed = int(loan["owed"])
        principal = int(loan["principal"])
        pct = random.uniform(cut_min, cut_max)
        if pct > 0:
            cut = max(1, int(owed * pct))
            loan["owed"] = owed - cut
            self._save_loan(guild.id, user.id, loan)
            await reply(f"🦈💼 {flavor.format(cut=cut)}\nStill on the book: **{loan['owed']:,}**, "
                        f"due <t:{int(loan['due_ts'])}:R>.")
        elif pct < 0:
            added = int(owed * -pct)
            loan["owed"] = min(owed + added, int(principal * MAX_OWED_MULT))
            self._save_loan(guild.id, user.id, loan)
            await reply(f"🦈💼 {flavor.format(cut=added)}\nThe book now says **{loan['owed']:,}**.")
        elif jail_seconds > 0:
            jail_user(guild.id, user.id, jail_seconds,
                      reason="Caught doing Sal's dirty work",
                      bail_amount=max(500, owed // 10), channel_id=channel_id)
            await reply(f"🦈🚔 {flavor}")
        else:
            await reply(f"🦈💼 {flavor}")

    # ---- check the tab ------------------------------------------------------

    _STAGE_MOOD = {
        0: "Sal is calm. For now.",
        1: "Sal has called twice. He doesn't call three times.",
        2: "The goons have your address.",
        3: "You've had the beating. There's one stage left. Pay.",
    }

    async def _tab(self, guild, user, reply):
        loan = self._get_loan(guild.id, user.id)
        if loan is None:
            until = self._blacklist_until(guild.id, user.id)
            if until > time.time():
                await reply(f"🦈 No tab — and no service. Sal remembers what you did. Blacklisted until <t:{int(until)}:f>.")
            else:
                await reply(f"🦈 Clean slate. Sal can front you up to **{MAX_LOAN:,}** — `!loan borrow <amount>`, "
                            f"{int(VIG_PCT * 100)}% vig, 48 hours. Simple terms. Serious consequences.")
            return
        due = int(loan["due_ts"])
        mood = self._STAGE_MOOD.get(int(loan.get("stage", 0)), "It's gone very badly.")
        overdue = " ⚠️ **OVERDUE**" if time.time() >= due else ""
        await reply(
            f"🦈 **The book on you:** borrowed **{int(loan['principal']):,}**, "
            f"owe **{int(loan['owed']):,}**, due <t:{due}:f> (<t:{due}:R>).{overdue}\n{mood}\n"
            f"-# Pay with `!loan repay <amount>`, or work it off — `!loan job` (one every "
            f"{JOB_COOLDOWN_SECONDS // 3600}h)."
        )

    # ---- commands: everything under !loan / /loan --------------------------

    @commands.group(name="loan", aliases=["loanshark", "shark", "debt"],
                    invoke_without_command=True)
    @commands.guild_only()
    async def loan_prefix(self, ctx):
        """Bare `!loan` shows the tab; `!loan borrow` / `!loan repay` do business."""
        await self._tab(ctx.guild, ctx.author, ctx.send)

    @loan_prefix.command(name="borrow")
    async def borrow_prefix(self, ctx, amount: str):
        await self._borrow(ctx.guild, ctx.author, ctx.channel.id, amount, ctx.send)

    @borrow_prefix.error
    async def borrow_prefix_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Usage: `!loan borrow <amount>` — up to {MAX_LOAN:,}, vig is {int(VIG_PCT * 100)}%, due in 48h. Sal takes `10k`, `1.5m`-style amounts and `max`.")
        else:
            raise error

    @loan_prefix.command(name="repay", aliases=["pay"])
    async def repay_prefix(self, ctx, amount: str):
        await self._repay(ctx.guild, ctx.author, amount, ctx.send)

    @repay_prefix.error
    async def repay_prefix_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Usage: `!loan repay <amount>` — or `!loan repay all` to clear the tab.")
        else:
            raise error

    @loan_prefix.command(name="job", aliases=["work"])
    async def job_prefix(self, ctx):
        await self._job(ctx.guild, ctx.author, ctx.channel.id, ctx.send)

    loan_group = app_commands.Group(name="loan",
                                    description="Big Sal's loan business — borrow, repay, check the tab",
                                    guild_only=True)

    @loan_group.command(name="borrow", description="Borrow coins from Big Sal. The vig is not negotiable.")
    @app_commands.describe(amount=f"Coins to borrow — up to {MAX_LOAN:,}; supports 10k, 250k, max")
    async def borrow_slash(self, interaction: discord.Interaction, amount: str):
        if not interaction.guild:
            await interaction.response.send_message("Sal only works the casino floor. Server only.", ephemeral=True)
            return
        await self._borrow(interaction.guild, interaction.user, interaction.channel_id,
                           amount, interaction.response.send_message)

    @loan_group.command(name="repay", description="Pay down your tab before it pays you a visit")
    @app_commands.describe(amount="Coins to pay — supports 10k, all, half, 50%")
    async def repay_slash(self, interaction: discord.Interaction, amount: str):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        await self._repay(interaction.guild, interaction.user, amount,
                          interaction.response.send_message)

    @loan_group.command(name="job", description="Do a job for Sal to work off part of your debt. No questions.")
    async def job_slash(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        await self._job(interaction.guild, interaction.user, interaction.channel_id,
                        interaction.response.send_message)

    @loan_group.command(name="tab", description="Check what you owe the loanshark — and how mad he is")
    async def tab_slash(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        async def reply(msg):
            await interaction.response.send_message(msg, ephemeral=True)
        await self._tab(interaction.guild, interaction.user, reply)

    # ---- collections ---------------------------------------------------------

    def _seize(self, guild_id: int, user_id: int, amount: int, include_bank: bool) -> int:
        """Shake a debtor down for up to `amount`, wallet first and optionally
        the bank after — same closed-loop pattern as tax enforcement."""
        seized = 0
        take = min(amount, get_coins(guild_id, user_id))
        if take > 0 and transfer_to_house(guild_id, user_id, take, is_bet=False).get("ok"):
            seized = take
        if include_bank and seized < amount:
            seized += bank_seize_to_house(guild_id, user_id, amount - seized)
        return seized

    @tasks.loop(minutes=SCAN_INTERVAL_MINUTES)
    async def _collection_loop(self):
        now = time.time()
        for guild in list(self.bot.guilds):
            try:
                rows = economy.kv_all_in_namespace(guild.id, NAMESPACE)
            except Exception:
                logger.exception(f"loanshark: kv scan failed for guild {guild.id}")
                continue
            for user_id, keys in rows.items():
                if user_id == 0 or "loan" not in keys:
                    continue
                try:
                    loan = json.loads(keys["loan"])
                    target = stage_for(now, float(loan["due_ts"]))
                    current = int(loan.get("stage", 0))
                except (json.JSONDecodeError, TypeError, KeyError, ValueError):
                    logger.warning(f"loanshark: dropping malformed loan for user {user_id}")
                    kv_delete(guild.id, user_id, NAMESPACE, "loan")
                    continue
                if target <= current:
                    continue
                try:
                    await self._escalate(guild, user_id, loan, current, target)
                except Exception:
                    logger.exception(f"loanshark: escalation failed guild={guild.id} user={user_id}")

    async def _escalate(self, guild, user_id, loan, current: int, target: int):
        """Advance a loan to `target` stage: juice for every stage crossed,
        then the enforcement action for the stage we landed on."""
        principal = int(loan["principal"])
        owed = apply_juice(int(loan["owed"]), principal, target - current)
        channel_id = int(loan.get("channel_id", 0) or 0)
        mention = f"<@{user_id}>"

        if target == 1:
            loan["owed"], loan["stage"] = owed, 1
            self._save_loan(guild.id, user_id, loan)
            await self._announce(guild, channel_id, user_id,
                f"🦈📞 {mention} — you missed the date. The tab just grew to **{owed:,}** "
                f"and it grows again every 12 hours. Sal doesn't call a third time. `!loan repay all`.")
            return

        if target == 2:
            seized = self._seize(guild.id, user_id, owed, include_bank=False)
            owed -= seized
            if owed <= 0:
                self._settle(guild.id, user_id, BLACKLIST_SETTLED_SECONDS)
                await self._announce(guild, channel_id, user_id,
                    f"🦈 {mention} — two guys in tracksuits just emptied **{seized:,}** out of your "
                    f"pockets. Tab's square. Sal won't be lending to you for a few days.")
            else:
                loan["owed"], loan["stage"] = owed, 2
                self._save_loan(guild.id, user_id, loan)
                await self._announce(guild, channel_id, user_id,
                    f"🦈 {mention} — the goons took **{seized:,}** off you and it *still* isn't enough. "
                    f"**{owed:,}** left on the book. The next visit isn't about money.")
            return

        if target == 3:
            seized = self._seize(guild.id, user_id, owed, include_bank=True)
            owed -= seized
            if owed <= 0:
                self._settle(guild.id, user_id, BLACKLIST_SETTLED_SECONDS)
                await self._announce(guild, channel_id, user_id,
                    f"🦈 {mention} — they found the bank account. **{seized:,}** collected, tab closed. "
                    f"You kept your kneecaps. Barely.")
            else:
                loan["owed"], loan["stage"] = owed, 3
                self._save_loan(guild.id, user_id, loan)
                jail_user(guild.id, user_id, BEATING_JAIL_SECONDS,
                          reason="Educational beating (loanshark)", bail_amount=0,
                          channel_id=channel_id)
                await self._announce(guild, channel_id, user_id,
                    f"🦈🏥 {mention} — wallet and bank cleaned out for **{seized:,}** and you're still "
                    f"**{owed:,}** short, so the boys gave you an education. Enjoy the hospital ward "
                    f"({BEATING_JAIL_SECONDS // 3600}h, nobody's posting bail). One stage left. Don't find out.")
            return

        # target == 4: you really made him mad.
        seized = self._seize(guild.id, user_id, owed, include_bank=True)
        self._settle(guild.id, user_id, BLACKLIST_BLOOD_SECONDS)
        jail_user(guild.id, user_id, KNEECAP_JAIL_SECONDS,
                  reason="Settled a debt in blood (loanshark)", bail_amount=0,
                  channel_id=channel_id, no_release=True)
        await self._announce(guild, channel_id, user_id,
            f"🦈🩸 {mention} — you really made Sal mad. Everything you had (**{seized:,}**) is gone, "
            f"the rest of the debt was settled in blood, and you're in a hole for "
            f"**{KNEECAP_JAIL_SECONDS // 3600} hours** — no bail, no cards, no calls. "
            f"Sal's book says you don't exist for a week.")

    def _settle(self, guild_id: int, user_id: int, blacklist_seconds: int):
        kv_delete(guild_id, user_id, NAMESPACE, "loan")
        kv_set(guild_id, user_id, NAMESPACE, "blacklist_until",
               int(time.time() + blacklist_seconds))

    async def _announce(self, guild, channel_id: int, user_id: int, text: str):
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if channel is None:
            channel = guild.system_channel
        if channel is None:
            logger.warning(f"loanshark: no channel to announce in guild {guild.id} for user {user_id}")
            return
        try:
            await channel.send(text)
        except (discord.Forbidden, discord.HTTPException):
            logger.warning(f"loanshark: couldn't announce in channel {channel.id} (guild {guild.id})")

    @_collection_loop.before_loop
    async def before_collection_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(LoanShark(bot))
