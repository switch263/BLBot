"""The house went bankrupt — emergency measures and the reset referendum.

There is no bet cap, so a big enough win can drain both house buckets and
still leave the winner short. When that happens economy.casino_payout logs a
bankruptcy event; this cog picks it up (30s poll) and:

  1. Covers the shortfall by seizing an equal percentage of EVERY player bank
     account (economy.cover_house_shortfall — the winner's own and the
     memorial player's excepted) and announces it in #game-spam:
     "<player> bankrupted the house, so we took X% of everyone's bank…"
  2. Opens a referendum (same channel): press the button to vote for a full
     economic wipe. BANKRUPTCY_VOTES_NEEDED votes inside
     BANKRUPTCY_VOTE_SECONDS and the reset happens on the spot — every wallet
     and bank wiped, everyone re-seeded at BANKRUPTCY_RESET_WALLET coins with
     BANKRUPTCY_RESET_LOAN of it fronted by Big Sal as a real loanshark loan
     (vig and all). Fewer votes when the window closes and BLBot decides
     itself: each vote cast is one part in BANKRUPTCY_VOTES_NEEDED of the odds
     the wipe happens anyway; otherwise the mint fires up
     (replenish_house_if_low) and the casino reopens like nothing happened.

The vote button is a persistent view (survives restarts); the poll loop
finalizes an expired vote even if the message is gone. All knobs live in
economy.py. State (cog_kv namespace "bankruptcy", guild-scoped user_id=0):
  pending — JSON list of unhandled bankruptcy events (written by economy.py)
  vote    — JSON {close_ts, votes, winner_id, owed, channel_id, message_id}
"""
import discord
from discord.ext import commands, tasks
import json
import logging
import random
import time

import economy
from config import ADMIN_CHANNEL_ID
from cogs.loanshark import NAMESPACE as LOAN_NS, VIG_PCT, TERM_SECONDS

logger = logging.getLogger(__name__)

_NS = "bankruptcy"
_VOTE_KEY = "vote"
VOTE_BUTTON_ID = "bankruptcy:vote_reset"


class ResetVoteView(discord.ui.View):
    """Persistent (timeout=None + custom_id) so votes survive restarts."""

    def __init__(self, cog: "Bankruptcy"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="VOTE: WIPE IT ALL", style=discord.ButtonStyle.danger,
                       emoji="🔥", custom_id=VOTE_BUTTON_ID)
    async def vote(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._handle_vote(interaction)


class Bankruptcy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(ResetVoteView(self))
        if not self._watch_loop.is_running():
            self._watch_loop.start()

    async def cog_unload(self):
        if self._watch_loop.is_running():
            self._watch_loop.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Bankruptcy watch loaded.")

    # --- state / plumbing ---------------------------------------------------

    def _find_channel(self, guild: discord.Guild):
        """Same resolution as taxes: #game-spam, then admin, then system."""
        ch = discord.utils.get(guild.text_channels, name=economy.TAX_CHANNEL_NAME)
        if ch:
            return ch
        ch = guild.get_channel(ADMIN_CHANNEL_ID)
        if isinstance(ch, discord.TextChannel):
            return ch
        return guild.system_channel

    def _get_vote(self, guild_id: int) -> dict | None:
        raw = economy.kv_get(guild_id, 0, _NS, _VOTE_KEY)
        if raw is None:
            return None
        try:
            vote = json.loads(raw)
            if isinstance(vote, dict):
                return vote
        except (json.JSONDecodeError, TypeError):
            pass
        logger.warning(f"bankruptcy: dropping malformed vote row in guild {guild_id}")
        economy.kv_delete(guild_id, 0, _NS, _VOTE_KEY)
        return None

    # --- the watch loop -----------------------------------------------------

    @tasks.loop(seconds=30)
    async def _watch_loop(self):
        now = time.time()
        for guild in list(self.bot.guilds):
            try:
                for ev in economy.pop_bankruptcy_events(guild.id):
                    await self._handle_bankruptcy(guild, ev)
                vote = self._get_vote(guild.id)
                if vote and now >= float(vote.get("close_ts", 0)):
                    await self._finalize(guild)
            except Exception:
                logger.exception(f"bankruptcy loop failed for guild {guild.id}")

    @_watch_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    # --- bankruptcy handling ------------------------------------------------

    async def _handle_bankruptcy(self, guild: discord.Guild, ev: dict):
        winner_id = int(ev.get("user_id", 0))
        owed = int(ev.get("owed", 0))
        paid = int(ev.get("paid", 0))
        shortfall = max(0, owed - paid)
        cover = economy.cover_house_shortfall(guild.id, winner_id, shortfall)
        ch = self._find_channel(guild)
        if ch is not None:
            pct = f"{cover['pct'] * 100:.1f}%"
            if cover["seized"] > 0:
                lines = [
                    f"<@{winner_id}> bankrupted the house, so we took **{pct}** of "
                    f"everyone's bank to cover losses.",
                    "",
                    f"House owed **{owed:,}**, had **{paid:,}**. "
                    f"**{cover['seized']:,}** seized from **{cover['accounts']}** "
                    f"account(s); **{cover['paid']:,}** paid out.",
                ]
                if cover["still_short"] > 0:
                    lines.append(f"Even that wasn't enough — **{cover['still_short']:,}** "
                                 f"of the debt just evaporated.")
            else:
                lines = [
                    f"<@{winner_id}> bankrupted the house — it owed **{owed:,}** and "
                    f"had **{paid:,}**. The safe-deposit boxes were empty too, so "
                    f"**{cover['still_short']:,}** of the debt just evaporated.",
                ]
            embed = discord.Embed(
                title="🏚️ THE HOUSE IS BANKRUPT",
                description="\n".join(lines),
                color=discord.Color.dark_red(),
            )
            try:
                await ch.send(content=f"💥 <@{winner_id}> broke the bank!", embed=embed)
            except discord.HTTPException as e:
                logger.error(f"bankruptcy: couldn't announce in guild {guild.id}: {e}")
        if self._get_vote(guild.id) is None:
            await self._open_vote(guild, ch, winner_id, owed)

    async def _open_vote(self, guild: discord.Guild, ch, winner_id: int, owed: int):
        if ch is None:
            logger.warning(f"bankruptcy: no channel in guild {guild.id}; vote not opened.")
            return
        needed = economy.BANKRUPTCY_VOTES_NEEDED
        close_ts = int(time.time() + economy.BANKRUPTCY_VOTE_SECONDS)
        sal_owes = int(economy.BANKRUPTCY_RESET_LOAN * (1 + VIG_PCT))
        embed = discord.Embed(
            title="🗳️ EMERGENCY REFERENDUM: WIPE THE ECONOMY?",
            description=(
                f"The casino is insolvent. Two roads out:\n\n"
                f"🔥 **Total reset** — every wallet and bank wiped. Everyone restarts "
                f"with **{economy.BANKRUPTCY_RESET_WALLET:,}** coins, "
                f"**{economy.BANKRUPTCY_RESET_LOAN:,}** of it fronted by Big Sal — "
                f"a real loan, so you'll owe him **{sal_owes:,}** within "
                f"{TERM_SECONDS // 3600} hours.\n"
                f"🖨️ **The money printer** — BLBot mints fresh coins for the house "
                f"and everyone keeps their fortunes (and their debts).\n\n"
                f"Press the button to vote for the reset. **{needed} votes** and it "
                f"happens on the spot. Voting closes <t:{close_ts}:R> "
                f"(<t:{close_ts}:f>). Fewer than {needed} votes and **BLBot decides "
                f"the economy's fate itself** — every vote cast tips the odds "
                f"toward the wipe."
            ),
            color=discord.Color.orange(),
        )
        try:
            msg = await ch.send(content=f"🗳️ Reset votes: **0/{needed}**",
                                embed=embed, view=ResetVoteView(self))
        except discord.HTTPException as e:
            logger.error(f"bankruptcy: couldn't open vote in guild {guild.id}: {e}")
            return
        economy.kv_set(guild.id, 0, _NS, _VOTE_KEY, json.dumps({
            "close_ts": close_ts,
            "votes": [],
            "winner_id": winner_id,
            "owed": owed,
            "channel_id": ch.id,
            "message_id": msg.id,
        }))

    # --- voting -------------------------------------------------------------

    async def _handle_vote(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            return
        vote = self._get_vote(guild.id)
        if vote is None or time.time() >= float(vote.get("close_ts", 0)):
            await interaction.response.send_message(
                "The referendum is closed.", ephemeral=True)
            return
        uid = interaction.user.id
        votes = [int(v) for v in vote.get("votes", [])]
        if uid in votes:
            await interaction.response.send_message(
                "Your vote is already counted. The button doesn't get more "
                "democratic the harder you press it.", ephemeral=True)
            return
        votes.append(uid)
        vote["votes"] = votes
        economy.kv_set(guild.id, 0, _NS, _VOTE_KEY, json.dumps(vote))
        needed = economy.BANKRUPTCY_VOTES_NEEDED
        try:
            await interaction.response.edit_message(
                content=f"🗳️ Reset votes: **{len(votes)}/{needed}**")
        except discord.HTTPException:
            pass
        if len(votes) >= needed:
            await self._finalize(guild)

    # --- finalization ---------------------------------------------------------

    async def _finalize(self, guild: discord.Guild):
        """Close the referendum and act on it. Re-reads and deletes the vote row
        first, so the loop and a third button press can't both finalize."""
        vote = self._get_vote(guild.id)
        if vote is None:
            return
        economy.kv_delete(guild.id, 0, _NS, _VOTE_KEY)
        await self._disable_vote_message(vote)
        votes = [int(v) for v in vote.get("votes", [])]
        needed = economy.BANKRUPTCY_VOTES_NEEDED
        ch = self._find_channel(guild)
        if len(votes) >= needed:
            await self._do_reset(
                guild, ch,
                f"**{len(votes)}** of you pressed the button. Democracy is a hell of a drug.")
            return
        # Not enough votes — BLBot decides. Every vote cast is one part in
        # `needed` of the odds the wipe happens anyway.
        if random.random() < len(votes) / needed:
            await self._do_reset(
                guild, ch,
                f"Only **{len(votes)}/{needed}** voted, so the decision fell to BLBot. "
                f"BLBot looked at the books, lit a cigarette, and chose **chaos**.")
        else:
            await self._do_bailout(guild, ch, len(votes))

    async def _disable_vote_message(self, vote: dict):
        """Best-effort: kill the button on the referendum message."""
        channel = self.bot.get_channel(int(vote.get("channel_id", 0) or 0))
        if channel is None:
            return
        try:
            msg = await channel.fetch_message(int(vote.get("message_id", 0) or 0))
            await msg.edit(view=None)
        except (discord.HTTPException, discord.NotFound, ValueError):
            pass

    async def _do_bailout(self, guild: discord.Guild, ch, num_votes: int):
        res = economy.replenish_house_if_low(guild.id)
        if ch is None:
            return
        needed = economy.BANKRUPTCY_VOTES_NEEDED
        if res["added"] > 0:
            body = (f"BLBot minted **{res['added']:,}** fresh coins to bail out the "
                    f"house. Your fortunes are safe. The coin's purchasing power? "
                    f"Don't ask.")
        else:
            body = ("By the time the vote closed the house had already gambled its "
                    "way back to solvency. No mint needed. The casino never even "
                    "closed.")
        embed = discord.Embed(
            title="🖨️ THE MONEY PRINTER GOES BRRR",
            description=(
                f"The referendum closed at **{num_votes}/{needed}** votes — not "
                f"enough for the wipe, so BLBot made the call: keep it going.\n\n{body}"
            ),
            color=discord.Color.green(),
        )
        try:
            await ch.send(embed=embed)
        except discord.HTTPException as e:
            logger.error(f"bankruptcy: couldn't announce bailout in guild {guild.id}: {e}")

    async def _do_reset(self, guild: discord.Guild, ch, reason_line: str):
        res = economy.bankruptcy_reset(guild.id)
        now = int(time.time())
        principal = economy.BANKRUPTCY_RESET_LOAN
        owed = int(principal * (1 + VIG_PCT))
        due = now + TERM_SECONDS
        channel_id = ch.id if ch else 0
        for uid in res["players"]:
            if economy.is_memorial(uid):
                continue  # Sal doesn't hold paper on the memorial player
            economy.kv_set(guild.id, uid, LOAN_NS, "loan", json.dumps({
                "principal": principal,
                "owed": owed,
                "taken_ts": now,
                "due_ts": due,
                "stage": 0,
                "channel_id": channel_id,
            }))
        logger.info("bankruptcy: reset guild %s — %d players re-seeded.",
                    guild.id, len(res["players"]))
        if ch is None:
            return
        embed = discord.Embed(
            title="💥 TOTAL ECONOMIC RESET",
            description=(
                f"{reason_line}\n\n"
                f"Every wallet, bank account, jail sentence, debt, and trinket is "
                f"**gone**. All **{len(res['players'])}** of you start over with "
                f"**{economy.BANKRUPTCY_RESET_WALLET:,}** coins — and "
                f"**{principal:,}** of that is Big Sal's money. He wants "
                f"**{owed:,}** back by <t:{due}:f> (<t:{due}:R>). "
                f"`!loan repay` early, `!loan tab` often.\n\n"
                f"Leaderboards and game stats survive. Your dignity did not."
            ),
            color=discord.Color.dark_red(),
        )
        try:
            await ch.send(embed=embed)
        except discord.HTTPException as e:
            logger.error(f"bankruptcy: couldn't announce reset in guild {guild.id}: {e}")


async def setup(bot):
    await bot.add_cog(Bankruptcy(bot))
