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
`!prison` shows your file. The games record to game_stats and show on /wallet:
dice ("prisondice"), shiv fights ("shivfight"), three-card monte
("prisoncards"), contraband runs ("smuggle"), the tunnel ("tunnel") and
snitching ("snitch").

The yard, by stake:
  cigs only ....... dice (coin-flip odds), cards (a multiplier table)
  cigs + time ..... shiv (fight), smuggle (a contraband run)
  time only ....... gym (grind), snitch (gamble), tunnel (persistent progress
                    toward an outright escape — dig on a cooldown, risk a
                    cave-in or a guard sweep, walk out at 100%)
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

# --- Three-card monte with The Accountant -----------------------------------
# (weight, multiplier on the stake, flavor). Pays stake * mult back (0 = lost).
CARDS_MIN_STAKE = 1
CARDS_OUTCOMES = [
    (46, 0.0, "You pick the left card. It's a joker with your face drawn on it. The Accountant pockets **{stake}** cigs."),
    (16, 1.0, "You hesitate so long he gets bored and calls it a push. Your **{stake}** cigs come back."),
    (26, 2.0, "The queen. You actually found the queen. He pays **{win}** cigs and adjusts his glasses."),
    (8, 3.0, "You call the switch before he makes it. The whole yard goes *ooooh*. **{win}** cigs."),
    (3, 0.0, "Mid-shuffle he sneezes, all three cards fall in a puddle, and he declares the house wins on a technicality. **{stake}** cigs gone."),
    (1, 6.0, "You flip the card, the queen, AND the two cigs he'd hidden under it. He pays **{win}** and asks you never to come back."),
]

# --- Contraband run ----------------------------------------------------------
# Stake cigs on smuggling a package across the yard. A clean run doubles the
# stake, a bust loses it AND adds time, and the rare warden job pays 6x.
# (weight, mult, jail_delta_seconds, flavor)
SMUGGLE_COOLDOWN_SECONDS = 45 * 60
SMUGGLE_MIN_STAKE = 5
SMUGGLE_OUTCOMES = [
    (28, 2.0, 0, "Clean run. The package changes hands behind the chapel and nobody blinks. **{win}** cigs."),
    (10, 1.5, 0, "The buyer short-changes you but you don't argue with a man that size. **{win}** cigs."),
    (14, 1.0, 5 * 60, "A guard eyeballs you the whole way and you dump it in a planter. Stake returned, **+5 minutes** for loitering."),
    (40, 0.0, 20 * 60, "Random cell toss. They find the package and your **{stake}** cigs are gone with it. **+20 minutes.**"),
    (6, 0.0, 35 * 60, "The buyer was a CO in a borrowed jumpsuit. Stake confiscated, **+35 minutes**, and everyone saw."),
    (2, 6.0, 0, "The package was the warden's. He pays you personally, in cartons, and you never speak of it. **{win}** cigs."),
]

# --- The tunnel --------------------------------------------------------------
# Persistent per-user progress (kv "tunnel", 0-100) across digs and even
# across sentences. Each dig (on a cooldown) rolls one outcome; reaching
# TUNNEL_GOAL springs you outright. (weight, progress_lo, progress_hi,
# reset, jail_delta_seconds, cig_delta, flavor)
TUNNEL_COOLDOWN_SECONDS = 15 * 60
TUNNEL_GOAL = 100
TUNNEL_OUTCOMES = [
    (48, 8, 16, False, 0, 0, "You dig with a sharpened spoon until your arms give out. **+{gain}%** — the tunnel's at **{progress}%**."),
    (20, 18, 28, False, 0, 0, "Soft dirt tonight. Real progress: **+{gain}%**, tunnel at **{progress}%**."),
    (12, 0, 0, False, 0, 0, "You hit a pipe. You spend the whole shift deciding whether to go around it. No progress."),
    (10, 0, 0, True, 10 * 60, 0, "🚨 Cave-in. Weeks of work fill with dirt and the noise earns you **+10 minutes**. Tunnel reset."),
    (7, 0, 0, True, 25 * 60, -10, "🚨 Cell sweep. They find the hole behind the poster, fill it with concrete, and take your smokes. **+25 minutes**, tunnel reset, **-{cigs} cigs**."),
    (3, 30, 45, False, 0, 0, "You break into an old maintenance shaft. Somebody dug this before you. **+{gain}%**, tunnel at **{progress}%**."),
]

# --- Snitching ---------------------------------------------------------------
# Time-only gamble. (weight, time_lo, time_hi, cig_pct_lost, flavor)
SNITCH_COOLDOWN_SECONDS = 60 * 60
SNITCH_OUTCOMES = [
    (50, -45 * 60, -20 * 60, 0.0, "The warden listens, nods, writes a name down. **{mins} minutes off** for your cooperation."),
    (22, 0, 0, 0.0, "The warden already knew. He thanks you for wasting his afternoon. No change."),
    (18, 15 * 60, 30 * 60, 0.5, "Word gets out before you're back at your cell. The yard takes **half your cigs** and the guards add **+{mins} minutes** to keep you *safe*."),
    (10, -60 * 60, -60 * 60, 0.0, "You give up something big. The warden shakes your hand in front of everyone, which is its own problem. **{mins} minutes off.**"),
]


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
        progress = self._tunnel_progress(guild.id, user.id)
        if progress > 0:
            lines.append(f"⛏️ Tunnel: **{progress}%**")
        for label, key, cd in (("labor", "labor_ts", LABOR_COOLDOWN_SECONDS),
                               ("gym", "gym_ts", GYM_COOLDOWN_SECONDS),
                               ("shiv", "shiv_ts", SHIV_COOLDOWN_SECONDS),
                               ("smuggle", "smuggle_ts", SMUGGLE_COOLDOWN_SECONDS),
                               ("tunnel", "tunnel_ts", TUNNEL_COOLDOWN_SECONDS),
                               ("snitch", "snitch_ts", SNITCH_COOLDOWN_SECONDS)):
            left = self._cooldown_left(guild.id, user.id, key, cd)
            lines.append(f"• `{label}` — {'ready' if left == 0 else f'ready in {left // 60}m {left % 60}s'}")
        lines.append("-# `!prison labor` earn · `!prison dice <cigs>` / `!prison cards <cigs>` gamble · "
                     "`!prison gym` shave time · `!prison shiv <cigs>` fight · `!prison smuggle <cigs>` run contraband · "
                     "`!prison tunnel` dig out · `!prison snitch` talk to the warden · `!prison guard <cigs>` fence for coins")
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

    async def _cards(self, guild, user, raw_amount, reply):
        if not await self._require_jailed(guild, user, reply):
            return
        stash = self._cigs(guild.id, user.id)
        stake = parse_amount(raw_amount, available=stash)
        if stake is None:
            await reply(amount_error(raw_amount, contextual=True))
            return
        if stake < CARDS_MIN_STAKE:
            await reply("🃏 The Accountant doesn't deal for free. Put smokes on the crate.")
            return
        if not self._spend_cigs(guild.id, user.id, stake):
            await reply(f"🃏 You've got **{stash}** cigs and tried to stake **{stake:,}**. He counts better than you.")
            return
        weights = [o[0] for o in CARDS_OUTCOMES]
        _w, mult, flavor = random.choices(CARDS_OUTCOMES, weights=weights)[0]
        win = int(stake * mult)
        if win > 0:
            kv_incr(guild.id, user.id, NAMESPACE, "cigs", win)
        record_game(guild.id, user.id, "prisoncards", win > stake)
        await reply(f"🃏 {flavor.format(stake=stake, win=win)} (stash: **{self._cigs(guild.id, user.id)}**)")

    async def _smuggle(self, guild, user, raw_amount, reply):
        if not await self._require_jailed(guild, user, reply):
            return
        left = self._cooldown_left(guild.id, user.id, "smuggle_ts", SMUGGLE_COOLDOWN_SECONDS)
        if left > 0:
            await reply(f"📦 The yard's too hot after your last run. Wait **{left // 60}m {left % 60}s**.")
            return
        stash = self._cigs(guild.id, user.id)
        stake = parse_amount(raw_amount, available=stash)
        if stake is None:
            await reply(amount_error(raw_amount, contextual=True))
            return
        if stake < SMUGGLE_MIN_STAKE:
            await reply(f"📦 Nobody fronts a package for less than **{SMUGGLE_MIN_STAKE}** cigs.")
            return
        if not self._spend_cigs(guild.id, user.id, stake):
            await reply(f"📦 You've got **{stash}** cigs. The package costs up front.")
            return
        self._stamp(guild.id, user.id, "smuggle_ts")
        weights = [o[0] for o in SMUGGLE_OUTCOMES]
        _w, mult, jail_delta, flavor = random.choices(SMUGGLE_OUTCOMES, weights=weights)[0]
        win = int(stake * mult)
        if win > 0:
            kv_incr(guild.id, user.id, NAMESPACE, "cigs", win)
        tail = self._time_result(guild.id, user.id, jail_delta) if jail_delta else ""
        record_game(guild.id, user.id, "smuggle", win > stake)
        await reply(f"📦 {flavor.format(stake=stake, win=win)}{tail}\n(stash: **{self._cigs(guild.id, user.id)}**)")

    def _tunnel_progress(self, guild_id: int, user_id: int) -> int:
        return max(0, min(TUNNEL_GOAL, int(kv_get(guild_id, user_id, NAMESPACE, "tunnel", 0) or 0)))

    async def _tunnel(self, guild, user, reply):
        if not await self._require_jailed(guild, user, reply):
            return
        left = self._cooldown_left(guild.id, user.id, "tunnel_ts", TUNNEL_COOLDOWN_SECONDS)
        if left > 0:
            await reply(f"⛏️ Too many guards on the tier. Dig again in **{left // 60}m {left % 60}s**.")
            return
        self._stamp(guild.id, user.id, "tunnel_ts")
        progress = self._tunnel_progress(guild.id, user.id)
        weights = [o[0] for o in TUNNEL_OUTCOMES]
        _w, lo, hi, reset, jail_delta, cig_delta, flavor = random.choices(TUNNEL_OUTCOMES, weights=weights)[0]
        gain = random.randint(lo, hi) if hi > 0 else 0
        cigs_lost = 0
        if cig_delta < 0:
            cigs_lost = min(self._cigs(guild.id, user.id), -cig_delta)
            if cigs_lost:
                kv_incr(guild.id, user.id, NAMESPACE, "cigs", -cigs_lost)
        progress = 0 if reset else min(TUNNEL_GOAL, progress + gain)
        kv_set(guild.id, user.id, NAMESPACE, "tunnel", progress)
        if progress >= TUNNEL_GOAL:
            # Out. The sentence ends now, whatever was left of it.
            kv_set(guild.id, user.id, NAMESPACE, "tunnel", 0)
            remaining = jail_remaining(guild.id, user.id)
            adjust_jail_sentence(guild.id, user.id, -(remaining + 1))
            record_game(guild.id, user.id, "tunnel", True)
            await reply(f"⛏️ {flavor.format(gain=gain, progress=TUNNEL_GOAL, cigs=cigs_lost)}\n"
                        f"🌙 **You break through into the field behind the laundry.** Nobody's looking. "
                        f"You walk until the sirens are a rumor. **Free.**")
            return
        tail = self._time_result(guild.id, user.id, jail_delta) if jail_delta else ""
        record_game(guild.id, user.id, "tunnel", False)
        await reply(f"⛏️ {flavor.format(gain=gain, progress=progress, cigs=cigs_lost)}{tail}")

    async def _snitch(self, guild, user, reply):
        if not await self._require_jailed(guild, user, reply):
            return
        left = self._cooldown_left(guild.id, user.id, "snitch_ts", SNITCH_COOLDOWN_SECONDS)
        if left > 0:
            await reply(f"🗣️ The warden's door is closed. Try again in **{left // 60}m {left % 60}s**.")
            return
        self._stamp(guild.id, user.id, "snitch_ts")
        weights = [o[0] for o in SNITCH_OUTCOMES]
        _w, lo, hi, cig_pct, flavor = random.choices(SNITCH_OUTCOMES, weights=weights)[0]
        delta = random.randint(min(lo, hi), max(lo, hi)) if lo != hi else lo
        if cig_pct > 0:
            lost = int(self._cigs(guild.id, user.id) * cig_pct)
            if lost:
                kv_incr(guild.id, user.id, NAMESPACE, "cigs", -lost)
        tail = self._time_result(guild.id, user.id, delta) if delta else ""
        record_game(guild.id, user.id, "snitch", delta < 0)
        await reply(f"🗣️ {flavor.format(mins=abs(delta) // 60)}{tail}"
                    + (f"\n(stash: **{self._cigs(guild.id, user.id)}**)" if cig_pct > 0 else ""))

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

    @prison_prefix.command(name="cards", aliases=["monte", "queen"])
    async def cards_prefix(self, ctx, cigs: str):
        await self._cards(ctx.guild, ctx.author, cigs, ctx.send)

    @prison_prefix.command(name="smuggle", aliases=["run", "contraband"])
    async def smuggle_prefix(self, ctx, cigs: str):
        await self._smuggle(ctx.guild, ctx.author, cigs, ctx.send)

    @prison_prefix.command(name="tunnel", aliases=["dig", "escape"])
    async def tunnel_prefix(self, ctx):
        await self._tunnel(ctx.guild, ctx.author, ctx.send)

    @prison_prefix.command(name="snitch", aliases=["rat", "warden"])
    async def snitch_prefix(self, ctx):
        await self._snitch(ctx.guild, ctx.author, ctx.send)

    @dice_prefix.error
    @shiv_prefix.error
    @guard_prefix.error
    @cards_prefix.error
    @smuggle_prefix.error
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

    @prison_group.command(name="cards", description="Three-card monte with The Accountant — find the queen, up to 6x your cigs")
    @app_commands.describe(cigs="Cigarettes to stake — a number, or all/half")
    async def cards_slash(self, interaction: discord.Interaction, cigs: str):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        await self._cards(interaction.guild, interaction.user, cigs, interaction.response.send_message)

    @prison_group.command(name="smuggle", description="Stake cigs on a contraband run — 2x if it lands, time added if it doesn't (45 min cooldown)")
    @app_commands.describe(cigs=f"Cigarettes to stake — at least {SMUGGLE_MIN_STAKE}")
    async def smuggle_slash(self, interaction: discord.Interaction, cigs: str):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        await self._smuggle(interaction.guild, interaction.user, cigs, interaction.response.send_message)

    @prison_group.command(name="tunnel", description="Dig the escape tunnel — progress persists; reach 100% and walk out (15 min cooldown)")
    async def tunnel_slash(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        await self._tunnel(interaction.guild, interaction.user, interaction.response.send_message)

    @prison_group.command(name="snitch", description="Talk to the warden — usually time off, sometimes the yard finds out (1h cooldown)")
    async def snitch_slash(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        await self._snitch(interaction.guild, interaction.user, interaction.response.send_message)


async def setup(bot):
    await bot.add_cog(Prison(bot))
