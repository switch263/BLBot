import discord
from discord.ext import commands
from discord import app_commands
import random
import time
import logging

from economy import (
    get_coins, jail_remaining, release_from_jail, adjust_jail_sentence,
    transfer_to_house, record_game, kv_get, kv_set, get_jail_info,
)

logger = logging.getLogger(__name__)

# Cooldown between attempts (seconds). The stake on a jailbreak is your TIME,
# not coins — this throttle stops you spamming the dice until you walk free.
COOLDOWN_SECONDS = 90
_CD_NS = "jailbreak"

# Outcome kinds.
ESCAPE = "escape"      # full release
SHORTEN = "shorten"    # shave time off the remaining sentence
NOTHING = "nothing"    # no change — you bottled it
EXTEND = "extend"      # caught — more time
FINE = "fine"          # caught but bribe your way out of a report — lose coins
DISASTER = "disaster"  # caught badly — a LOT more time

# (weight, kind, flavor). Weights are relative; _pick normalizes.
OUTCOMES = [
    (26, ESCAPE,
     "🕳️ You wriggle through a vent the guards swore they'd welded shut and stroll into the daylight. **You're free.**"),
    (12, SHORTEN,
     "🔧 You saw most of the way through a bar before footsteps scatter you back to your bunk — but you shaved real time off your stretch."),
    (16, NOTHING,
     "🥶 You lose your nerve at the last gate and slink back to your cot. No harm done, no progress made."),
    (22, EXTEND,
     "🚨 Floodlights. Sirens. One very tired guard. Back inside you go — and they tacked extra time onto your sentence."),
    (14, FINE,
     "💸 A guard catches you mid-crawl and decides he never saw a thing... for the right price. Your stash takes the hit."),
    (10, DISASTER,
     "💥 The tunnel caves in, every alarm in the block trips, and the warden takes it *personally*. Your sentence balloons."),
]


class JailBreak(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Jailbreak module loaded.")

    def _pick(self):
        total = sum(w for w, *_ in OUTCOMES)
        roll = random.uniform(0, total)
        running = 0.0
        for weight, kind, flavor in OUTCOMES:
            running += weight
            if roll <= running:
                return kind, flavor
        return OUTCOMES[-1][1], OUTCOMES[-1][2]

    @staticmethod
    def _fmt(seconds: int) -> str:
        seconds = max(0, int(seconds))
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h > 0:
            return f"{h}h {m}m"
        if m > 0:
            return f"{m}m {s}s"
        return f"{s}s"

    async def _attempt(self, ctx_or_interaction):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild
        user = ctx_or_interaction.user if is_slash else ctx_or_interaction.author

        async def reply(content, **kwargs):
            if is_slash:
                await ctx_or_interaction.response.send_message(content, **kwargs)
                return await ctx_or_interaction.original_response()
            return await ctx_or_interaction.send(content, **kwargs)

        if not guild:
            await reply("Server only.")
            return

        remaining = jail_remaining(guild.id, user.id)
        if remaining <= 0:
            await reply("🔓 You're not in jail. Nothing to break out of — go gamble.")
            return

        # Repeat tax-evasion sentences are card-proof AND break-proof: no early
        # out by any route. Serve every second.
        info = get_jail_info(guild.id, user.id)
        if info and info.get("no_release"):
            await reply(
                "🔒 This is a **tax-evasion** hold — no jailbreak, no bribe, no "
                "card. Serve every second. Pay your taxes next time."
            )
            return

        # Attempt cooldown.
        now = time.time()
        until = kv_get(guild.id, user.id, _CD_NS, "until", 0) or 0
        wait = int(until - now)
        if wait > 0:
            await reply(
                f"🫨 Still catching your breath after the last attempt. "
                f"Lay low for **{self._fmt(wait)}**."
            )
            return
        kv_set(guild.id, user.id, _CD_NS, "until", now + COOLDOWN_SECONDS)

        kind, flavor = self._pick()
        result_line = ""
        escaped = False

        if kind == ESCAPE:
            release_from_jail(guild.id, user.id)
            escaped = True
            result_line = "🟢 **Sentence cleared.** Walk it off."
        elif kind == SHORTEN:
            shave = max(60, int(remaining * 0.35))
            res = adjust_jail_sentence(guild.id, user.id, -shave)
            if res.get("released"):
                escaped = True
                result_line = "🟢 That shave was enough — **you're out!**"
            else:
                result_line = (
                    f"🟡 Knocked **{self._fmt(shave)}** off. "
                    f"**{self._fmt(res.get('remaining', remaining))}** left to serve."
                )
        elif kind == NOTHING:
            result_line = f"⚪ No change. Still **{self._fmt(remaining)}** to go."
        elif kind == EXTEND:
            add = max(300, int(remaining * 0.30))
            res = adjust_jail_sentence(guild.id, user.id, add)
            result_line = (
                f"🔴 **+{self._fmt(add)}** added. "
                f"Now **{self._fmt(res.get('remaining', remaining + add))}** left."
            )
        elif kind == FINE:
            wallet = get_coins(guild.id, user.id)
            fine = min(wallet, max(1_000, int(wallet * 0.15)))
            if fine > 0:
                transfer_to_house(guild.id, user.id, fine, is_bet=False)
                result_line = (
                    f"🔴 The bribe cost you **{fine:,}** coins, but your sentence stands at "
                    f"**{self._fmt(remaining)}**. Balance: **{get_coins(guild.id, user.id):,}**."
                )
            else:
                # Dead broke — nothing to shake down, so they just walk you back.
                result_line = (
                    f"🔴 The guard goes for your stash and finds... lint. Sentence unchanged: "
                    f"**{self._fmt(remaining)}**."
                )
        else:  # DISASTER
            add = max(600, int(remaining * 0.80))
            res = adjust_jail_sentence(guild.id, user.id, add)
            result_line = (
                f"🔴🔴 **+{self._fmt(add)}** added. "
                f"The warden will remember this. **{self._fmt(res.get('remaining', remaining + add))}** left."
            )

        record_game(guild.id, user.id, "jailbreak", escaped)

        text = (
            f"🚓 **{user.display_name} attempts a jailbreak...**\n\n"
            f"_{flavor}_\n\n"
            f"{result_line}"
        )
        if not escaped:
            text += f"\n\n*Cooldown: {self._fmt(COOLDOWN_SECONDS)} before your next try.*"
        await reply(text)

    @commands.command(name="jailbreak", aliases=["breakout", "escape"])
    @commands.guild_only()
    async def jailbreak_prefix(self, ctx):
        await self._attempt(ctx)

    @app_commands.command(name="jailbreak", description="Risk it for early release — or make your sentence worse.")
    async def jailbreak_slash(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        await self._attempt(interaction)


async def setup(bot):
    await bot.add_cog(JailBreak(bot))
