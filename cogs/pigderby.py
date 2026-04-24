import discord
from discord.ext import commands
from discord import app_commands
import random
import sys
import os
import logging
import asyncio
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from economy import get_coins, add_coins, deduct_coins, jail_message

logger = logging.getLogger(__name__)

LOBBY_SECONDS = 30
TRACK_LENGTH = 20
TICK_SECONDS = 1.5
MAX_TICKS = 40  # safety cap

# Each pig: (emoji, name, step_weights[0..3], payout_multiplier)
# step_weights bias how fast they move each tick; payout is inversely related.
PIGS = [
    ("🐖", "Bacon Supreme",       [0, 1, 3, 6],  2),   # fastest, lowest payout
    ("🐷", "Little Miss Sausage", [0, 2, 4, 4],  3),
    ("🐽", "Sir Oinks-a-lot",     [1, 3, 4, 2],  5),
    ("🥓", "Porky Von Trapp",     [3, 4, 2, 1],  8),
    ("🧻", "Slop Bucket Jr.",     [5, 3, 2, 0], 15),   # slowest, biggest payout
]

RACE_START_QUIPS = [
    "The gate creaks open. The pigs look confused.",
    "A child somewhere is crying. The race begins.",
    "Someone fires a pistol into the sky. The pigs do not care.",
    "A commentator clears his throat. Nobody is listening.",
    "The track smells like regret.",
]

WIN_QUIPS = [
    "thundered across the finish like a wet sack of glory",
    "slipped, recovered, and still won",
    "was allegedly on performance enhancers",
    "won in a photo finish against nobody in particular",
    "crossed the line eating a hot dog",
]


class Bet:
    def __init__(self, user: discord.Member, pig_idx: int, amount: int):
        self.user = user
        self.pig_idx = pig_idx
        self.amount = amount


class Derby:
    LOBBY = "lobby"
    RACING = "racing"
    DONE = "done"

    def __init__(self, guild_id: int, channel_id: int, host_id: int, buy_in: int):
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.host_id = host_id
        self.buy_in = buy_in
        self.bets: list[Bet] = []
        self.bettors: set[int] = set()  # user_ids that have locked in
        self.phase = Derby.LOBBY
        self.lobby_deadline = 0.0
        self.message: discord.Message | None = None
        self.timer_task: asyncio.Task | None = None
        self.positions = [0] * len(PIGS)


class PigButton(discord.ui.Button):
    def __init__(self, idx: int, row: int):
        emoji, name, _, payout = PIGS[idx]
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=f"{name} ({payout}×)",
            emoji=emoji,
            row=row,
        )
        self.idx = idx

    async def callback(self, interaction: discord.Interaction):
        view: "LobbyView" = self.view  # type: ignore
        d = view.derby
        if d.phase != Derby.LOBBY:
            await interaction.response.send_message("Race already started.", ephemeral=True)
            return
        if interaction.user.id in d.bettors:
            await interaction.response.send_message("You've already picked a pig.", ephemeral=True)
            return
        jmsg = jail_message(d.guild_id, interaction.user.id)
        if jmsg:
            await interaction.response.send_message(jmsg, ephemeral=True)
            return
        balance = get_coins(d.guild_id, interaction.user.id)
        if balance < d.buy_in:
            await interaction.response.send_message(
                f"Too broke for the buy-in **{d.buy_in}**. Balance: **{balance}**", ephemeral=True)
            return
        deduct_coins(d.guild_id, interaction.user.id, d.buy_in)
        d.bets.append(Bet(interaction.user, self.idx, d.buy_in))
        d.bettors.add(interaction.user.id)
        await interaction.response.edit_message(content=view.cog._render_lobby(d), view=view)


class StartButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Start Race", emoji="🏁", row=2)

    async def callback(self, interaction: discord.Interaction):
        view: "LobbyView" = self.view  # type: ignore
        d = view.derby
        if interaction.user.id != d.host_id:
            await interaction.response.send_message("Only the host can start early.", ephemeral=True)
            return
        if d.phase != Derby.LOBBY:
            await interaction.response.send_message("Already started.", ephemeral=True)
            return
        if not d.bets:
            await interaction.response.send_message("No bettors yet.", ephemeral=True)
            return
        await interaction.response.defer()
        if d.timer_task:
            d.timer_task.cancel()
        await view.cog._run_race(d)


class CancelButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.danger, label="Cancel", emoji="❌", row=2)

    async def callback(self, interaction: discord.Interaction):
        view: "LobbyView" = self.view  # type: ignore
        d = view.derby
        if interaction.user.id != d.host_id:
            await interaction.response.send_message("Only the host can cancel.", ephemeral=True)
            return
        if d.phase != Derby.LOBBY:
            await interaction.response.send_message("Already started.", ephemeral=True)
            return
        # refund all bettors
        for b in d.bets:
            add_coins(d.guild_id, b.user.id, b.amount)
        d.phase = Derby.DONE
        if d.timer_task:
            d.timer_task.cancel()
        view.cog.derbies.pop(d.channel_id, None)
        for item in view.children:
            item.disabled = True
        await interaction.response.edit_message(content="🛑 Pig Derby cancelled. Buy-ins refunded.", view=view)


class LobbyView(discord.ui.View):
    def __init__(self, cog, derby: Derby):
        super().__init__(timeout=LOBBY_SECONDS + 10)
        self.cog = cog
        self.derby = derby
        for i in range(len(PIGS)):
            self.add_item(PigButton(i, row=i // 3))  # rows 0 and 1
        self.add_item(StartButton())
        self.add_item(CancelButton())


class PigDerby(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.derbies: dict[int, Derby] = {}

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Pig Derby loaded.")

    # ---------- Rendering ----------

    def _render_lobby(self, d: Derby) -> str:
        lines = [
            f"🏁 **Pig Derby** — buy-in **{d.buy_in}** per player",
            f"Race starts <t:{int(d.lobby_deadline)}:R>. Pick a pig:",
        ]
        # Summary of bets per pig
        by_pig: dict[int, list[Bet]] = {}
        for b in d.bets:
            by_pig.setdefault(b.pig_idx, []).append(b)
        for i, (emoji, name, _, payout) in enumerate(PIGS):
            backers = by_pig.get(i, [])
            if backers:
                names = ", ".join(b.user.display_name for b in backers)
                lines.append(f"{emoji} **{name}** — {payout}× payout  _(backed by: {names})_")
            else:
                lines.append(f"{emoji} **{name}** — {payout}× payout")
        lines.append("")
        lines.append(f"Host can **Start Race** now or **Cancel** to refund.")
        return "\n".join(lines)

    def _render_track(self, d: Derby, header: str = "🏁 **The race is on!**") -> str:
        lines = [header, ""]
        for i, (emoji, name, _, payout) in enumerate(PIGS):
            pos = min(d.positions[i], TRACK_LENGTH)
            before = "━" * pos
            after = "━" * (TRACK_LENGTH - pos)
            finish = "🏁" if pos >= TRACK_LENGTH else ""
            lines.append(f"{emoji} {name:<22} │{before}{emoji}{after}│{finish}  ({pos}/{TRACK_LENGTH})")
        return "```\n" + "\n".join(lines) + "\n```"

    def _render_final(self, d: Derby, winner_idx: int, payouts: list[tuple[Bet, int]]) -> str:
        emoji, name, _, payout = PIGS[winner_idx]
        quip = random.choice(WIN_QUIPS)
        lines = [
            f"🏆 **{emoji} {name}** wins at **{payout}×**! ({quip})",
            self._render_track(d, header=""),
        ]
        winners = [p for p in payouts if p[1] > 0]
        losers = [p for p in payouts if p[1] == 0]
        if winners:
            lines.append("**Payouts:**")
            for b, pay in winners:
                lines.append(f"• {b.user.display_name}: bet **{b.amount}** → **+{pay - b.amount}** (total **{pay}**)")
        if losers:
            loser_names = ", ".join(b.user.display_name for b, _ in losers)
            lines.append(f"**Lost:** {loser_names}")
        return "\n".join(lines)

    # ---------- Flow ----------

    async def _start_derby(self, ctx_or_interaction, bet: int):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild
        channel = ctx_or_interaction.channel
        user = ctx_or_interaction.user if is_slash else ctx_or_interaction.author

        async def reply(content, **kwargs):
            if is_slash:
                await ctx_or_interaction.response.send_message(content, **kwargs)
                return await ctx_or_interaction.original_response()
            return await ctx_or_interaction.send(content, **kwargs)

        if not guild:
            await reply("Server only.")
            return
        jmsg = jail_message(guild.id, user.id)
        if jmsg:
            await reply(jmsg)
            return
        if bet <= 0:
            await reply("Buy-in must be > 0.")
            return
        if channel.id in self.derbies:
            await reply("A pig derby is already running in this channel.")
            return
        if get_coins(guild.id, user.id) < bet:
            await reply(f"You're too broke. Balance: **{get_coins(guild.id, user.id)}**")
            return

        d = Derby(guild.id, channel.id, user.id, bet)
        d.lobby_deadline = time.time() + LOBBY_SECONDS
        self.derbies[channel.id] = d

        view = LobbyView(self, d)
        msg = await reply(self._render_lobby(d), view=view)
        d.message = msg
        d.timer_task = asyncio.create_task(self._lobby_timer(d))

    async def _lobby_timer(self, d: Derby):
        try:
            delay = d.lobby_deadline - time.time()
            if delay > 0:
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        if d.phase == Derby.LOBBY:
            await self._run_race(d)

    async def _run_race(self, d: Derby):
        if not d.bets:
            d.phase = Derby.DONE
            self.derbies.pop(d.channel_id, None)
            if d.message:
                try:
                    await d.message.edit(content="🛑 Pig Derby cancelled — no bettors.", view=None)
                except discord.HTTPException:
                    pass
            return

        d.phase = Derby.RACING
        try:
            await d.message.edit(content=self._render_track(d, header=f"🏁 **Race begins!** _{random.choice(RACE_START_QUIPS)}_"), view=None)
        except discord.HTTPException:
            pass
        await asyncio.sleep(TICK_SECONDS)

        winner_idx = None
        for _ in range(MAX_TICKS):
            # step each pig
            for i, (_, _, weights, _) in enumerate(PIGS):
                step = random.choices([0, 1, 2, 3], weights=weights, k=1)[0]
                d.positions[i] += step

            # check for finish
            finished = [i for i, p in enumerate(d.positions) if p >= TRACK_LENGTH]
            if finished:
                # pick leader (highest position), break ties randomly
                max_pos = max(d.positions[i] for i in finished)
                leaders = [i for i in finished if d.positions[i] == max_pos]
                winner_idx = random.choice(leaders)
                break

            try:
                await d.message.edit(content=self._render_track(d))
            except discord.HTTPException:
                pass
            await asyncio.sleep(TICK_SECONDS)

        if winner_idx is None:
            # no one crossed; pick whoever is furthest
            max_pos = max(d.positions)
            winner_idx = d.positions.index(max_pos)

        # settle
        payouts: list[tuple[Bet, int]] = []
        for b in d.bets:
            if b.pig_idx == winner_idx:
                payout = b.amount * PIGS[winner_idx][3]
                add_coins(d.guild_id, b.user.id, payout)
                payouts.append((b, payout))
            else:
                payouts.append((b, 0))

        d.phase = Derby.DONE
        self.derbies.pop(d.channel_id, None)
        try:
            await d.message.edit(content=self._render_final(d, winner_idx, payouts))
        except discord.HTTPException as e:
            logger.error(f"Failed to finalize pig derby: {e}")

    @commands.command(name="pigderby", aliases=["pigs", "derby"])
    @commands.guild_only()
    async def derby_prefix(self, ctx, bet: int):
        await self._start_derby(ctx, bet)

    @app_commands.command(name="pigderby", description="Start a multi-player pig race with fixed-odds betting")
    @app_commands.describe(bet="Buy-in amount every bettor locks in")
    async def derby_slash(self, interaction: discord.Interaction, bet: int):
        await self._start_derby(interaction, bet)


async def setup(bot):
    await bot.add_cog(PigDerby(bot))
