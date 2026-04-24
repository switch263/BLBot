import discord
from discord.ext import commands
from discord import app_commands
import random
import sys
import os
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from economy import get_coins, add_coins, deduct_coins, jail_message

logger = logging.getLogger(__name__)

MIN_BET = 50

# Each outcome is a dict:
#   weight: int
#   kind:   "flat" (get `value` coins), "mult" (get bet*value), "zero" (lose bet), "fine" (lose bet + bet*value)
#   value:  number, or None for "zero"
#   flavor: f-string with optional {name} placeholder
OUTCOMES = [
    # --- BIG WINS ---
    {"weight": 4, "kind": "flat", "value": 300,
     "flavor": "🐱 **Bubbles rescues a kitten from a tree.** 'THAT'S MY KITTY, BOYS!' He hands {name} 300 coins as a reward for moral support."},
    {"weight": 3, "kind": "flat", "value": 500,
     "flavor": "💰 You find **Julian's rum-stained cash stash** under the porch. He is currently asleep. You take 500."},
    {"weight": 3, "kind": "flat", "value": 400,
     "flavor": "🌿 **Ricky's hash garden pays off.** The harvest is bountiful and the Mounties are on vacation. +400."},
    {"weight": 5, "kind": "mult", "value": 3,
     "flavor": "🚗 **Julian's car scheme works.** 'That's just the way she goes sometimes, boys.' ×3 your bet."},
    {"weight": 2, "kind": "mult", "value": 5,
     "flavor": "📺 **Cable scam pays off.** J-Roc hooks up the whole park. Protection money rolls in. ×5."},
    {"weight": 7, "kind": "mult", "value": 2,
     "flavor": "🍔 **Randy's Dirty Burger delivery run** goes smooth. You get a 2× cut. His shirt stays off."},
    {"weight": 1, "kind": "mult", "value": 10,
     "flavor": "🤼 **Greasy Jim wins the title match.** You had him at ×10 odds. You are rich and slightly oily."},

    # --- FLAT MEDIUM WINS ---
    {"weight": 6, "kind": "flat", "value": 150,
     "flavor": "🛒 **Bubbles builds a shopping cart.** He sells it to {name} for cost. Nets you 150."},
    {"weight": 6, "kind": "flat", "value": 100,
     "flavor": "🎤 **J-Roc drops a verse about you.** 'Yo, {name}, you know how it is, know'mean?' You get 100 in royalties."},
    {"weight": 5, "kind": "flat", "value": 200,
     "flavor": "🍻 **Sam Losco buys you a round.** Then another. Then pays you 200 to leave. Fair."},

    # --- NEUTRAL ---
    {"weight": 10, "kind": "mult", "value": 1,
     "flavor": "🏚️ **Just another day in Sunnyvale.** A shopping cart rolls by. You ponder. Break even."},

    # --- LOSSES (bet only) ---
    {"weight": 8, "kind": "zero", "value": None,
     "flavor": "🚔 **Ricky gets arrested** for 'drivin' without a lesbian' (license). You were in the car. Lose bet."},
    {"weight": 6, "kind": "zero", "value": None,
     "flavor": "🍺 **You spent all your coins on rum & coke** trying to console Julian. He does not remember you. Lose bet."},
    {"weight": 5, "kind": "zero", "value": None,
     "flavor": "🐦 **The shit hawks circle.** You know what's coming. You take shelter and drop your coins. Lose bet."},

    # --- LOSSES (bet + fine) ---
    {"weight": 6, "kind": "fine", "value": 0.5,
     "flavor": "🥴 **Mr. Lahey stumbles up, drunk as a shit skunk.** 'The *hic* shit IS, the shit, IS, the shit — ' Surprise inspection. Fine."},
    {"weight": 3, "kind": "fine", "value": 1.0,
     "flavor": "💩 **THE SHIT BLIZZARD ARRIVES.** 'BUBBLES, WE'RE IN A SHIT BLIZZARD.' Double loss."},
    {"weight": 3, "kind": "fine", "value": 0.75,
     "flavor": "🚜 **Corey and Trevor crash your car** into the Lot 3 mailbox again. Body shop bill on top of bet. Ouch."},

    # --- FLAT LOSSES (absurd) ---
    {"weight": 5, "kind": "flat", "value": -200,
     "flavor": "🧾 **Julian hands {name} his rum tab.** It is itemized. It is dated back to 2004. Lose bet + 200."},
    {"weight": 3, "kind": "flat", "value": -300,
     "flavor": "🏠 **Randy has moved into your trailer.** He ate everything. Lose bet + 300 in grocery damages."},
    {"weight": 2, "kind": "flat", "value": -400,
     "flavor": "⛪ **Pastor Dave showed up for a 'friendly chat.'** You are now tithing. Lose bet + 400."},
]


class Sunnyvale(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Sunnyvale Chronicles loaded.")

    def _pick(self):
        total = sum(o["weight"] for o in OUTCOMES)
        roll = random.uniform(0, total)
        running = 0.0
        for o in OUTCOMES:
            running += o["weight"]
            if roll <= running:
                return o
        return OUTCOMES[-1]

    async def _do_day(self, ctx_or_interaction, bet: int):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild
        user = ctx_or_interaction.user if is_slash else ctx_or_interaction.author

        async def reply(content, **kwargs):
            if is_slash:
                await ctx_or_interaction.response.send_message(content, **kwargs)
                return await ctx_or_interaction.original_response()
            return await ctx_or_interaction.send(content, **kwargs)

        if not guild:
            await reply("Server only, decent.")
            return
        jmsg = jail_message(guild.id, user.id)
        if jmsg:
            await reply(jmsg)
            return
        if bet < MIN_BET:
            await reply(f"Bet at least **{MIN_BET}** or Julian will find out, boys.")
            return
        if get_coins(guild.id, user.id) < bet:
            await reply(f"You're broke as frig. Balance: **{get_coins(guild.id, user.id)}**")
            return

        deduct_coins(guild.id, user.id, bet)
        outcome = self._pick()
        flavor = outcome["flavor"].format(name=user.display_name)

        kind = outcome["kind"]
        if kind == "flat":
            value = outcome["value"]
            if value >= 0:
                add_coins(guild.id, user.id, value)
                net = value - bet
                line = f"**{'+'if net >= 0 else ''}{net}** coins _(flat payout of {value} minus {bet} bet)_"
            else:
                # Flat penalty: lose bet AND the extra
                extra = min(get_coins(guild.id, user.id), abs(value))
                if extra > 0:
                    deduct_coins(guild.id, user.id, extra)
                line = f"**Lost {bet}** + extra **{extra}** in damages."
        elif kind == "mult":
            m = outcome["value"]
            payout = int(bet * m)
            add_coins(guild.id, user.id, payout)
            net = payout - bet
            line = f"**{'+'if net >= 0 else ''}{net}** coins _(×{m} on {bet} bet)_"
        elif kind == "zero":
            line = f"**Lost {bet}** coins."
        elif kind == "fine":
            m = outcome["value"]
            extra = min(get_coins(guild.id, user.id), int(bet * m))
            if extra > 0:
                deduct_coins(guild.id, user.id, extra)
                line = f"**Lost {bet}** + **{extra}** fine."
            else:
                line = f"**Lost {bet}**. Tried to fine you more but you're already tapped."
        else:
            line = "???"

        text = (
            f"🏚️ **{user.display_name}** rolls through Sunnyvale Trailer Park for **{bet}** coins.\n\n"
            f"{flavor}\n\n"
            f"{line}\n"
            f"Balance: **{get_coins(guild.id, user.id)}**"
        )
        await reply(text)

    @commands.command(name="sunnyvale", aliases=["tpb", "trailerparkboys"])
    @commands.guild_only()
    async def sunnyvale_prefix(self, ctx, bet: int):
        await self._do_day(ctx, bet)

    @app_commands.command(name="sunnyvale", description="Spend a day in Sunnyvale Trailer Park. Anything can happen. It usually does.")
    @app_commands.describe(bet=f"Coins to risk (min {MIN_BET})")
    async def sunnyvale_slash(self, interaction: discord.Interaction, bet: int):
        await self._do_day(interaction, bet)


async def setup(bot):
    await bot.add_cog(Sunnyvale(bot))
