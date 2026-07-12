"""The prison economy. Every other cog locks you OUT while jailed — this one
only works while you're IN. Jail stops being a mute button and becomes a place.

Currency is cigarettes (`cog_kv` namespace "prison", per-user "cigs" — they
persist between sentences, because a man's smokes are his own). You earn them
doing prison labor, gamble them at yard dice, stake them on shiv fights, and
fence them to a crooked guard for coins.

Sentence time is the other stake: the gym shaves minutes, shiv fights are
double-or-nothing on your freedom, and labor can backfire into extra time.
All sentence changes go through economy.adjust_jail_sentence (atomic; releases
the row when it hits zero).

Coin flow stays closed-loop: the guard's payouts come from the house via
refund_from_house (no stats bump — fencing smokes isn't a casino win). Cigs
themselves are minted by labor and burned by losses; they're a token, not
coins, so they don't touch the money supply.

Commands live under one group: `!prison` (alias `!yard`) / `/prison`. Bare
`!prison` shows your file. Dice and shiv fights record to game_stats
("prisondice" / "shivfight") and show on /wallet.
"""
import discord
from discord.ext import commands
from discord import app_commands
import logging
import random
import time

from economy import (
    kv_get, kv_set, kv_incr,
    jail_remaining, get_jail_info, adjust_jail_sentence,
    refund_from_house, record_game,
)
from amount import parse_amount, amount_error

logger = logging.getLogger(__name__)

NAMESPACE = "prison"

LABOR_COOLDOWN_SECONDS = 10 * 60
GYM_COOLDOWN_SECONDS = 30 * 60
SHIV_COOLDOWN_SECONDS = 60 * 60

SHIV_MIN_STAKE = 5
GUARD_RATE = 120          # coins per cigarette
GUARD_MIN_CIGS = 10

NOT_JAILED_MSG = ("🏛️ You're not in prison. This is yard business — come back "
                  "when you've been sentenced. (Knowing you, soon.)")

# (weight, cigs_delta, jail_delta_seconds, flavor)
LABOR_OUTCOMES = [
    (28, 2, 0, "You stamp license plates until your hands are numb. **+{cigs} cigs.**"),
    (20, 3, 0, "Laundry duty. You find things in these pockets you can't unsee. **+{cigs} cigs.**"),
    (15, 4, 0, "Kitchen shift — you slip extra dessert to the right people. **+{cigs} cigs.**"),
    (10, 6, 0, "You detail the warden's car and don't mention the smell in the trunk. **+{cigs} cigs.**"),
    (10, 1, 0, "You mop the same hallway four times. Nobody knows why. **+{cigs} cig.**"),
    (8, 0, 10 * 60, "Caught sleeping in the supply closet. **+10 minutes** on your sentence and no smokes."),
    (5, 2, -8 * 60, "The warden watches you work and nods slowly. **+{cigs} cigs** and **8 minutes off** your stretch."),
    (2, 10, 0, "You find a full carton behind a loose brick. You tell no one. **+{cigs} cigs.**"),
]

# (weight, time_delta_seconds_min, max, flavor) — negative shaves the sentence
GYM_OUTCOMES = [
    (55, -8 * 60, -3 * 60, "You put in honest work on the bench. The guards respect it: **{mins} minutes off.**"),
    (28, -14 * 60, -8 * 60, "Personal best on deadlifts. The yard goes quiet. **{mins} minutes off.**"),
    (10, 0, 0, "You pull something in the first set and spend the hour pretending you meant to stretch. No change."),
    (7, 10 * 60, 10 * 60, "You drop the bar so loud the guards call it a fight. **+{mins} minutes.**"),
]

DICE_WIN_PCT = 0.46
DICE_CHEAT_PCT = 0.08     # Rico cheats openly; everyone saw it; nobody says anything

INMATE_NAMES = [
    "Tiny (7 feet tall)", "The Accountant", "Spoons", "Old Gary",
    "The Guy From Cell Block D", "Whispers", "Two-Left-Feet Tony", "The Dentist",
]

SHIV_WIN_PCT = 0.45
SHIV_BUST_PCT = 0.10


class Prison(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Prison economy loaded.")

    # ---- shared plumbing ------------------------------------------------------

    def _cigs(self, guild_id: int, user_id: int) -> int:
        return int(kv_get(guild_id, user_id, NAMESPACE, "cigs", 0) or 0)

    def _spend_cigs(self, guild_id: int, user_id: int, amount: int) -> bool:
        """Atomically take cigs; refunds and refuses if the balance would go
        negative (kv_incr is the atomic op, so a double-click can't double-spend)."""
        if amount <= 0:
            return False
        new = kv_incr(guild_id, user_id, NAMESPACE, "cigs", -amount)
        if new < 0:
            kv_incr(guild_id, user_id, NAMESPACE, "cigs", amount)
            return False
        return True

    def _cooldown_left(self, guild_id: int, user_id: int, key: str, seconds: int) -> int:
        last = float(kv_get(guild_id, user_id, NAMESPACE, key, 0) or 0)
        return max(0, int(last + seconds - time.time()))

    def _stamp(self, guild_id: int, user_id: int, key: str):
        kv_set(guild_id, user_id, NAMESPACE, key, int(time.time()))

    async def _require_jailed(self, guild, user, reply) -> bool:
        if jail_remaining(guild.id, user.id) <= 0:
            await reply(NOT_JAILED_MSG)
            return False
        return True

    def _time_result(self, guild_id: int, user_id: int, delta_seconds: int) -> str:
        """Apply a sentence change and describe what happened."""
        res = adjust_jail_sentence(guild_id, user_id, delta_seconds)
        if not res.get("ok"):
            return ""
        if res.get("released"):
            return "\n🎉 **That was the last of your sentence — you're a free man. Walk out slow.**"
        mins, secs = divmod(res.get("remaining", 0), 60)
        return f"\n⏳ Sentence now: **{mins}m {secs}s**."

    # ---- the yard --------------------------------------------------------------

    async def _profile(self, guild, user, reply):
        cigs = self._cigs(guild.id, user.id)
        remaining = jail_remaining(guild.id, user.id)
        if remaining <= 0:
            await reply(f"🏛️ **Your file:** currently a free citizen (somehow). "
                        f"Stash from previous stints: **{cigs} cigs** — they'll be "
                        f"waiting for you. You'll be back.")
            return
        info = get_jail_info(guild.id, user.id) or {}
        reason = info.get("reason") or "unspecified crimes"
        mins = remaining // 60
        lines = [
            f"🏛️ **Your file:** in for *{reason}*, **{mins} minutes** left.",
            f"🚬 Cigs: **{cigs}**",
        ]
        for label, key, cd in (("labor", "labor_ts", LABOR_COOLDOWN_SECONDS),
                               ("gym", "gym_ts", GYM_COOLDOWN_SECONDS),
                               ("shiv", "shiv_ts", SHIV_COOLDOWN_SECONDS)):
            left = self._cooldown_left(guild.id, user.id, key, cd)
            lines.append(f"• `{label}` — {'ready' if left == 0 else f'ready in {left // 60}m {left % 60}s'}")
        lines.append("-# `!prison labor` earn · `!prison dice <cigs>` gamble · `!prison gym` "
                     "shave time · `!prison shiv <cigs>` fight for freedom · `!prison guard <cigs>` fence for coins")
        await reply("\n".join(lines))

    async def _labor(self, guild, user, reply):
        if not await self._require_jailed(guild, user, reply):
            return
        left = self._cooldown_left(guild.id, user.id, "labor_ts", LABOR_COOLDOWN_SECONDS)
        if left > 0:
            await reply(f"🧹 You're still on your break. Next shift in **{left // 60}m {left % 60}s**.")
            return
        self._stamp(guild.id, user.id, "labor_ts")
        weights = [o[0] for o in LABOR_OUTCOMES]
        _w, cigs, jail_delta, flavor = random.choices(LABOR_OUTCOMES, weights=weights)[0]
        if cigs:
            kv_incr(guild.id, user.id, NAMESPACE, "cigs", cigs)
        tail = self._time_result(guild.id, user.id, jail_delta) if jail_delta else ""
        total = self._cigs(guild.id, user.id)
        await reply(f"🧹 {flavor.format(cigs=cigs)} (stash: **{total}**){tail}")

    async def _dice(self, guild, user, raw_amount, reply):
        if not await self._require_jailed(guild, user, reply):
            return
        stash = self._cigs(guild.id, user.id)
        bet = parse_amount(raw_amount, available=stash)
        if bet is None:
            await reply(amount_error(raw_amount, contextual=True))
            return
        if bet <= 0:
            await reply("🎲 Rico doesn't roll for zero. Put smokes on the blanket.")
            return
        if not self._spend_cigs(guild.id, user.id, bet):
            await reply(f"🎲 You're short — you've got **{stash}** cigs and tried to bet **{bet:,}**.")
            return
        roll = random.random()
        if roll < DICE_CHEAT_PCT:
            won = False
            text = (f"🎲 Rico switches the dice in plain view of everyone. Nobody says a word. "
                    f"Your **{bet}** cigs slide into his sock. That's just Rico.")
        elif roll < DICE_CHEAT_PCT + DICE_WIN_PCT:
            won = True
            kv_incr(guild.id, user.id, NAMESPACE, "cigs", bet * 2)
            text = f"🎲 Sevens. Rico pays out **{bet}** cigs and mutters something in a language you don't know."
        else:
            won = False
            text = f"🎲 Craps. Rico sweeps your **{bet}** cigs off the blanket without making eye contact."
        record_game(guild.id, user.id, "prisondice", won)
        await reply(f"{text} (stash: **{self._cigs(guild.id, user.id)}**)")

    async def _gym(self, guild, user, reply):
        if not await self._require_jailed(guild, user, reply):
            return
        left = self._cooldown_left(guild.id, user.id, "gym_ts", GYM_COOLDOWN_SECONDS)
        if left > 0:
            await reply(f"🏋️ Rest day. Muscles grow between sets — back in **{left // 60}m {left % 60}s**.")
            return
        self._stamp(guild.id, user.id, "gym_ts")
        weights = [o[0] for o in GYM_OUTCOMES]
        _w, lo, hi, flavor = random.choices(GYM_OUTCOMES, weights=weights)[0]
        delta = random.randint(min(lo, hi), max(lo, hi)) if lo != hi else lo
        tail = self._time_result(guild.id, user.id, delta) if delta else ""
        await reply(f"🏋️ {flavor.format(mins=abs(delta) // 60)}{tail}")

    async def _shiv(self, guild, user, raw_amount, reply):
        if not await self._require_jailed(guild, user, reply):
            return
        left = self._cooldown_left(guild.id, user.id, "shiv_ts", SHIV_COOLDOWN_SECONDS)
        if left > 0:
            await reply(f"🔪 The yard's still talking about your last fight. Lay low for **{left // 60}m {left % 60}s**.")
            return
        stash = self._cigs(guild.id, user.id)
        stake = parse_amount(raw_amount, available=stash)
        if stake is None:
            await reply(amount_error(raw_amount, contextual=True))
            return
        if stake < SHIV_MIN_STAKE:
            await reply(f"🔪 Nobody bleeds for less than **{SHIV_MIN_STAKE}** cigs.")
            return
        if not self._spend_cigs(guild.id, user.id, stake):
            await reply(f"🔪 You've only got **{stash}** cigs. The stake comes up front.")
            return
        self._stamp(guild.id, user.id, "shiv_ts")
        opponent = random.choice(INMATE_NAMES)
        roll = random.random()
        if roll < SHIV_BUST_PCT:
            won = False
            tail = self._time_result(guild.id, user.id, 15 * 60)
            text = (f"🔪🚨 The guards break it up before the first swing. Your **{stake}** cig stake is "
                    f"confiscated and you eat **+15 minutes** for the sharpened toothbrush.{tail}")
        elif roll < SHIV_BUST_PCT + SHIV_WIN_PCT:
            won = True
            kv_incr(guild.id, user.id, NAMESPACE, "cigs", stake * 2)
            shave = -random.randint(15 * 60, 40 * 60)
            tail = self._time_result(guild.id, user.id, shave)
            text = (f"🔪 You beat **{opponent}** behind the commissary. His **{stake}** cigs are yours, and "
                    f"the yard's respect is worth **{abs(shave) // 60} minutes** off your stretch.{tail}")
        else:
            won = False
            extra = random.randint(10 * 60, 25 * 60)
            tail = self._time_result(guild.id, user.id, extra)
            text = (f"🔪 **{opponent}** folds you like a lawn chair and takes your **{stake}** cigs. The "
                    f"guards add **{extra // 60} minutes** for your trouble.{tail}")
        record_game(guild.id, user.id, "shivfight", won)
        await reply(f"{text}\n(stash: **{self._cigs(guild.id, user.id)}**)")

    async def _guard(self, guild, user, raw_amount, reply):
        if not await self._require_jailed(guild, user, reply):
            return
        stash = self._cigs(guild.id, user.id)
        cigs = parse_amount(raw_amount, available=stash)
        if cigs is None:
            await reply(amount_error(raw_amount, contextual=True))
            return
        if cigs < GUARD_MIN_CIGS:
            await reply(f"🧢 The guard doesn't even slow his walk for less than **{GUARD_MIN_CIGS}** cigs.")
            return
        if not self._spend_cigs(guild.id, user.id, cigs):
            await reply(f"🧢 You've got **{stash}** cigs. Don't waste the guard's time.")
            return
        paid = refund_from_house(guild.id, user.id, cigs * GUARD_RATE)
        if paid <= 0:
            kv_incr(guild.id, user.id, NAMESPACE, "cigs", cigs)
            await reply("🧢 The guard pats his empty pockets and shrugs. Even the house is dry. Keep your smokes.")
            return
        # House could be short — only charge the cigs the coins actually covered.
        covered = -(-paid // GUARD_RATE)  # ceil
        if covered < cigs:
            kv_incr(guild.id, user.id, NAMESPACE, "cigs", cigs - covered)
        await reply(f"🧢 The guard takes **{covered}** cigs without breaking stride and **{paid:,}** coins "
                    f"appear in your account. You've seen nothing, he's seen nothing. "
                    f"(stash: **{self._cigs(guild.id, user.id)}**)")

    # ---- commands: everything under !prison / /prison ---------------------------

    @commands.group(name="prison", aliases=["yard"], invoke_without_command=True)
    @commands.guild_only()
    async def prison_prefix(self, ctx):
        """Bare `!prison` shows your file — sentence, cigs, what's ready."""
        await self._profile(ctx.guild, ctx.author, ctx.send)

    @prison_prefix.command(name="labor", aliases=["work", "plates"])
    async def labor_prefix(self, ctx):
        await self._labor(ctx.guild, ctx.author, ctx.send)

    @prison_prefix.command(name="dice")
    async def dice_prefix(self, ctx, cigs: str):
        await self._dice(ctx.guild, ctx.author, cigs, ctx.send)

    @prison_prefix.command(name="gym")
    async def gym_prefix(self, ctx):
        await self._gym(ctx.guild, ctx.author, ctx.send)

    @prison_prefix.command(name="shiv", aliases=["fightout"])
    async def shiv_prefix(self, ctx, cigs: str):
        await self._shiv(ctx.guild, ctx.author, cigs, ctx.send)

    @prison_prefix.command(name="guard", aliases=["fence", "sell"])
    async def guard_prefix(self, ctx, cigs: str):
        await self._guard(ctx.guild, ctx.author, cigs, ctx.send)

    @dice_prefix.error
    @shiv_prefix.error
    @guard_prefix.error
    async def _amount_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("How many cigs? e.g. `!prison dice 10`, or `all` / `half`.")
        else:
            raise error

    prison_group = app_commands.Group(name="prison",
                                      description="The prison economy — only works while you're locked up",
                                      guild_only=True)

    @prison_group.command(name="file", description="Your prison file: sentence, cig stash, cooldowns")
    async def profile_slash(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        async def reply(msg):
            await interaction.response.send_message(msg, ephemeral=True)
        await self._profile(interaction.guild, interaction.user, reply)

    @prison_group.command(name="labor", description="Work a prison job for cigarettes (10 min cooldown)")
    async def labor_slash(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        await self._labor(interaction.guild, interaction.user, interaction.response.send_message)

    @prison_group.command(name="dice", description="Roll dice with Rico — double or nothing on your cigs")
    @app_commands.describe(cigs="Cigarettes to bet — a number, or all/half")
    async def dice_slash(self, interaction: discord.Interaction, cigs: str):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        await self._dice(interaction.guild, interaction.user, cigs, interaction.response.send_message)

    @prison_group.command(name="gym", description="Hit the yard gym to shave time off your sentence (30 min cooldown)")
    async def gym_slash(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        await self._gym(interaction.guild, interaction.user, interaction.response.send_message)

    @prison_group.command(name="shiv", description="Stake cigs on a shiv fight — win time off, lose time on (1h cooldown)")
    @app_commands.describe(cigs=f"Cigarettes to stake — at least {SHIV_MIN_STAKE}")
    async def shiv_slash(self, interaction: discord.Interaction, cigs: str):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        await self._shiv(interaction.guild, interaction.user, cigs, interaction.response.send_message)

    @prison_group.command(name="guard", description=f"Fence cigs to a crooked guard — {GUARD_RATE} coins each")
    @app_commands.describe(cigs=f"Cigarettes to sell — at least {GUARD_MIN_CIGS}")
    async def guard_slash(self, interaction: discord.Interaction, cigs: str):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        await self._guard(interaction.guild, interaction.user, cigs, interaction.response.send_message)


async def setup(bot):
    await bot.add_cog(Prison(bot))
