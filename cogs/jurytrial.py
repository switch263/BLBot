"""Jury trials — a jailed player puts their fate in chat's hands.

`!trial` / `/trial` (defendant only, from jail): pay court fees to the house,
and a public vote opens for VOTE_SECONDS with GUILTY / NOT GUILTY buttons.
Secret ballot — the message shows how many jurors have voted, never which way,
and you can change your vote until the gavel drops.

Verdicts:
  NOT GUILTY majority -> released on the spot (release_from_jail — which means
                         a no_release sentence can't be sprung; we refuse those
                         cases up front: no court will touch them).
  GUILTY majority     -> the jury didn't buy it: +50% of the remaining sentence.
  Tie                 -> hung jury; nothing changes, and the filing is spent.
  Under MIN_JURORS    -> mistrial; fee refunded, filing NOT spent — try again
                         when chat is awake.

One filing per sentence (keyed to the jail row's jailed_at in cog_kv namespace
"jurytrial"), so you can't spam the docket. Jurors who voted with the majority
split civic-duty pay from the house — small and bounded, but it gets people to
click. The defendant can't vote. Outcome records to game_stats as "jurytrial"
(win = acquitted).
"""
import discord
from discord.ext import commands
from discord import app_commands
import logging

from economy import (
    kv_get, kv_set, kv_delete,
    jail_remaining, get_jail_info, release_from_jail, adjust_jail_sentence,
    transfer_to_house, refund_from_house, record_game, get_coins,
)

logger = logging.getLogger(__name__)

NAMESPACE = "jurytrial"
TRIAL_FEE = 2_500
JUROR_FEE = 250
MIN_JURORS = 2
VOTE_SECONDS = 120
GUILTY_EXTENSION_PCT = 0.50
MAX_PAID_JURORS = 12


class TrialView(discord.ui.View):
    def __init__(self, cog, guild, defendant, message=None):
        super().__init__(timeout=VOTE_SECONDS)
        self.cog = cog
        self.guild = guild
        self.defendant = defendant
        self.message = message
        self.votes: dict[int, bool] = {}  # user_id -> True means guilty
        self.closed = False

    async def _cast(self, interaction: discord.Interaction, guilty: bool):
        if interaction.user.id == self.defendant.id:
            await interaction.response.send_message(
                "You don't get a vote at your own trial. That's the whole point.", ephemeral=True)
            return
        changed = interaction.user.id in self.votes
        self.votes[interaction.user.id] = guilty
        word = "GUILTY" if guilty else "NOT GUILTY"
        note = "Vote changed to" if changed else "Ballot cast:"
        await interaction.response.send_message(
            f"🗳️ {note} **{word}**. The ballot is secret — nobody saw that but you.", ephemeral=True)
        try:
            await self.message.edit(embed=self.cog.trial_embed(self.guild, self.defendant, len(self.votes)))
        except discord.HTTPException:
            pass

    @discord.ui.button(label="GUILTY", style=discord.ButtonStyle.danger, emoji="🔨")
    async def guilty_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._cast(interaction, True)

    @discord.ui.button(label="NOT GUILTY", style=discord.ButtonStyle.success, emoji="🕊️")
    async def not_guilty_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._cast(interaction, False)

    async def on_timeout(self):
        if self.closed:
            return
        self.closed = True
        for child in self.children:
            child.disabled = True
        try:
            await self.cog.deliver_verdict(self)
        except Exception:
            logger.exception("jurytrial: verdict delivery failed")


class JuryTrial(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._active: set[tuple[int, int]] = set()  # (guild_id, user_id) mid-vote

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Jury Trial loaded.")

    def trial_embed(self, guild, defendant, ballots: int) -> discord.Embed:
        info = get_jail_info(guild.id, defendant.id) or {}
        reason = info.get("reason") or "unspecified crimes"
        remaining = jail_remaining(guild.id, defendant.id)
        return discord.Embed(
            title="🏛️ THE PEOPLE vs. " + defendant.display_name.upper(),
            description=(
                f"{defendant.mention} stands accused of *{reason}* "
                f"({remaining // 60} minutes left on the sentence) and demands a jury.\n\n"
                f"**Vote below.** Secret ballot, {VOTE_SECONDS}s on the clock, majority rules.\n"
                f"🕊️ Acquittal walks them out today. 🔨 Conviction adds "
                f"**{int(GUILTY_EXTENSION_PCT * 100)}%** to the sentence.\n"
                f"Jurors on the winning side split civic-duty pay "
                f"(**{JUROR_FEE:,}** each, house money).\n\n"
                f"🗳️ Ballots cast: **{ballots}**"
            ),
            color=discord.Color.dark_gold(),
        )

    # ---- filing ----------------------------------------------------------------

    async def _file(self, guild, defendant, channel, reply):
        key = (guild.id, defendant.id)
        if key in self._active:
            await reply("🏛️ Your trial is already in session. Look up.")
            return
        remaining = jail_remaining(guild.id, defendant.id)
        if remaining <= 0:
            await reply("🏛️ You're not in jail. The court has better things to do — allegedly.")
            return
        info = get_jail_info(guild.id, defendant.id) or {}
        if info.get("no_release"):
            await reply("🏛️ No court in the land will touch your case. You're doing "
                        "every minute of that one.")
            return
        jailed_at = float(info.get("jailed_at") or 0)
        tried = kv_get(guild.id, defendant.id, NAMESPACE, "tried_at")
        if tried is not None and float(tried) == jailed_at:
            await reply("🏛️ You've had your day in court for this sentence. Double "
                        "jeopardy works in your favor exactly never.")
            return
        fee = transfer_to_house(guild.id, defendant.id, TRIAL_FEE, is_bet=False)
        if not fee.get("ok"):
            have = get_coins(guild.id, defendant.id)
            await reply(f"🏛️ Court fees are **{TRIAL_FEE:,}** and you're holding **{have:,}**. "
                        f"The public defender is a raccoon. Motion denied.")
            return
        kv_set(guild.id, defendant.id, NAMESPACE, "tried_at", jailed_at)
        self._active.add(key)
        try:
            view = TrialView(self, guild, defendant)
            embed = self.trial_embed(guild, defendant, 0)
            msg = await channel.send(content=f"🏛️ **Court is in session!** {defendant.mention} "
                                             f"demands a jury of their peers. 🔨🕊️",
                                     embed=embed, view=view)
            view.message = msg
        except Exception:
            # Couldn't seat the court — undo everything.
            self._active.discard(key)
            kv_delete(guild.id, defendant.id, NAMESPACE, "tried_at")
            refund_from_house(guild.id, defendant.id, TRIAL_FEE)
            raise

    # ---- verdict ----------------------------------------------------------------

    async def deliver_verdict(self, view: TrialView):
        guild, defendant = view.guild, view.defendant
        self._active.discard((guild.id, defendant.id))
        votes = view.votes
        guilty = sum(1 for g in votes.values() if g)
        innocent = len(votes) - guilty

        if jail_remaining(guild.id, defendant.id) <= 0:
            verdict = (f"🏛️ Case dismissed — {defendant.mention} is already out (bail, a card, "
                       f"or time served). The court keeps the fee. Obviously.")
            await self._close(view, verdict)
            return

        if len(votes) < MIN_JURORS:
            kv_delete(guild.id, defendant.id, NAMESPACE, "tried_at")
            refund_from_house(guild.id, defendant.id, TRIAL_FEE)
            verdict = (f"🏛️ **MISTRIAL.** Couldn't seat {MIN_JURORS} jurors — this town has no "
                       f"civic spirit. Fees refunded; {defendant.mention} may refile when "
                       f"someone's awake.")
            await self._close(view, verdict)
            return

        if innocent > guilty:
            release_from_jail(guild.id, defendant.id)
            record_game(guild.id, defendant.id, "jurytrial", True)
            self._pay_jury(guild.id, votes, winning_guilty=False)
            verdict = (f"🏛️🕊️ **NOT GUILTY** ({innocent}–{guilty}). {defendant.mention} walks! "
                       f"The jury believes you, which says more about them than you. "
                       f"Majority jurors collect **{JUROR_FEE:,}** each.")
        elif guilty > innocent:
            remaining = jail_remaining(guild.id, defendant.id)
            extension = max(60, int(remaining * GUILTY_EXTENSION_PCT))
            res = adjust_jail_sentence(guild.id, defendant.id, extension)
            record_game(guild.id, defendant.id, "jurytrial", False)
            self._pay_jury(guild.id, votes, winning_guilty=True)
            mins = res.get("remaining", remaining + extension) // 60
            verdict = (f"🏛️🔨 **GUILTY** ({guilty}–{innocent}). The jury took one look at "
                       f"{defendant.mention} and added **{extension // 60} minutes** "
                       f"(now {mins}m total). Should've taken the plea deal that "
                       f"didn't exist. Majority jurors collect **{JUROR_FEE:,}** each.")
        else:
            record_game(guild.id, defendant.id, "jurytrial", False)
            verdict = (f"🏛️ **HUNG JURY** ({guilty}–{innocent}). No verdict, no refund, no "
                       f"justice. {defendant.mention} serves out the sentence like everyone "
                       f"else. The system works.")
        await self._close(view, verdict)

    def _pay_jury(self, guild_id: int, votes: dict[int, bool], winning_guilty: bool):
        winners = [uid for uid, g in votes.items() if g == winning_guilty]
        for uid in winners[:MAX_PAID_JURORS]:
            refund_from_house(guild_id, uid, JUROR_FEE)

    async def _close(self, view: TrialView, verdict: str):
        try:
            await view.message.edit(view=view)
            await view.message.reply(verdict)
        except discord.HTTPException:
            logger.warning("jurytrial: couldn't post verdict")

    # ---- commands ----------------------------------------------------------------

    @commands.command(name="trial", aliases=["jury", "objection"])
    @commands.guild_only()
    async def trial_prefix(self, ctx):
        """Demand a jury trial for your current sentence."""
        await self._file(ctx.guild, ctx.author, ctx.channel, ctx.send)

    @app_commands.command(name="trial", description=f"Demand a jury trial — {TRIAL_FEE:,} in court fees, chat decides your fate")
    async def trial_slash(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        member = interaction.guild.get_member(interaction.user.id) or interaction.user
        async def reply(msg):
            await interaction.response.send_message(msg, ephemeral=True)
        # The trial itself posts publicly to the channel; only refusals are ephemeral.
        await self._file(interaction.guild, member, interaction.channel, reply)
        if not interaction.response.is_done():
            await interaction.response.send_message("🏛️ Court is in session — see the docket below.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(JuryTrial(bot))
