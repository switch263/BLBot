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

# (weight, multiplier, flavor)
# Multiplier is total payout multiplier on the bet (1.0 = break even, 0 = total loss).
SUSHI_MENU = [
    # Catastrophic (rare) — food poisoning loses bet + extra
    (3,  -1.0, "🍣 **Convenience Store Uni** — tasted like it crawled out of a tide pool. You are in the bathroom for 3 hours. Lose bet + fine."),
    (2,  -0.5, "🐟 **Bait Shop Nigiri** — it WAS bait two hours ago. Your stomach files a lawsuit. Lose bet + fine."),
    (2,  -0.75, "🦑 **Mystery Ikura (Neon Yellow Variant)** — wasn't roe. Was probably soap. Hospital is annoyed."),
    (2,  -0.5, "🐢 **'Turtle Roll' (legally not turtle)** — it WAS turtle. Lose bet + ethics fine."),
    # Plain losses (common)
    (12, 0.0,  "🍱 **Gas Station 'Sushi' Boat** — you took one bite and your tongue went numb. You waste the rest."),
    (10, 0.0,  "🍣 **Mystery Roll (Day 4)** — the rice is crunchy. Rice should not be crunchy. You pay and leave."),
    (8,  0.0,  "🥡 **Scotch-Taped Temaki** — it falls apart in your hand. You eat the seaweed dry."),
    (6,  0.0,  "🍢 **Dashboard-Aged Sashimi** — the Toyota was warm. The fish was warmer. You decline."),
    (5,  0.0,  "🧊 **Still-Partially-Frozen Hand Roll** — you chipped a tooth. No refund."),
    (5,  0.0,  "🍣 **Kirby's Cousin's 'Spicy' Tuna** — it's ketchup. It's just ketchup."),
    # Break-even
    (8,  1.0,  "🍙 **Forecourt Onigiri** — surprisingly edible. You neither won nor lost. Call that a win, actually."),
    (4,  1.0,  "🧋 **'Sushi Smoothie'** — an aberration. You paid. You lived. Break even."),
    # Small wins
    (10, 1.5,  "🍣 **Expired-Yesterday Tuna Roll** — lived dangerously, got away with it. +50%."),
    (8,  2.0,  "🍥 **Chef's Special (the chef is 17)** — somehow this slaps. ×2."),
    (5,  1.8,  "🌭 **Spam Musubi from the Register Heater** — unexpectedly delicious. ×1.8."),
    (5,  1.5,  "🐠 **'Salmon' (It's Tilapia)** — the price was right. ×1.5."),
    # Nice wins
    (5,  3.0,  "🍤 **Deep-Fried Everything Roll** — no notes. ×3."),
    (4,  4.0,  "🍱 **The 7-Eleven Omakase Experience™** — you'll remember this. ×4."),
    (3,  3.5,  "🍣 **The 'CEO Roll'** — somehow loaded with real wagyu and real caviar. ×3.5."),
    (3,  5.0,  "🥢 **The Broken-English Menu Special** — you pointed. The chef wept with pride. ×5."),
    # Big wins (rare)
    (2,  7.0,  "🌟 **A REAL SUSHI CHEF was stranded here** — you lucked into a ×7 meal."),
    (1,  9.0,  "👑 **Truffle-Foie Gras Nigiri (stolen from a cruise ship)** — quality is illegal. ×9."),
    (1,  15.0, "🏆 **LEGENDARY GAS STATION OMAKASE** — 15-star. The chef cries. You cry. ×15."),
    (1,  25.0, "💎 **THE JIRO DREAMS OF GAS STATION SUSHI ENCOUNTER** — a myth. You were chosen. ×25."),
]


class Sushi(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Gas Station Sushi loaded.")

    def _pick(self):
        total = sum(w for w, _, _ in SUSHI_MENU)
        roll = random.uniform(0, total)
        running = 0.0
        for weight, mult, flavor in SUSHI_MENU:
            running += weight
            if roll <= running:
                return mult, flavor
        return SUSHI_MENU[-1][1], SUSHI_MENU[-1][2]

    async def _do_sushi(self, ctx_or_interaction, bet: int):
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
        jmsg = jail_message(guild.id, user.id)
        if jmsg:
            await reply(jmsg)
            return
        if bet <= 0:
            await reply("You gotta order SOMETHING, bro.")
            return
        if get_coins(guild.id, user.id) < bet:
            await reply(f"Too broke for sushi. Balance: **{get_coins(guild.id, user.id)}**")
            return

        deduct_coins(guild.id, user.id, bet)
        mult, flavor = self._pick()

        if mult >= 1.0:
            payout = int(bet * mult)
            add_coins(guild.id, user.id, payout)
            net = payout - bet
            result = f"**Net +{net}** coins."
        elif mult == 0.0:
            result = f"**Lost {bet}** coins to the cause."
        else:
            # Negative mult = extra fine on top of bet loss. e.g., mult=-0.5 means extra 0.5*bet fine.
            extra = min(get_coins(guild.id, user.id), int(abs(mult) * bet))
            if extra > 0:
                deduct_coins(guild.id, user.id, extra)
                result = f"**Lost {bet}** + **{extra}** medical bills."
            else:
                result = f"**Lost {bet}**. Tried to charge you a hospital bill but you were already broke."

        text = (
            f"🍣 **{user.display_name}** orders gas station sushi for **{bet}** coins.\n"
            f"{flavor}\n"
            f"{result}\n"
            f"Balance: **{get_coins(guild.id, user.id)}**"
        )
        await reply(text)

    @commands.command(name="sushi", aliases=["gasstationsushi"])
    @commands.guild_only()
    async def sushi_prefix(self, ctx, bet: int):
        await self._do_sushi(ctx, bet)

    @app_commands.command(name="sushi", description="Order gas station sushi. Results vary. Wildly.")
    @app_commands.describe(bet="Coins to risk on this culinary adventure")
    async def sushi_slash(self, interaction: discord.Interaction, bet: int):
        await self._do_sushi(interaction, bet)


async def setup(bot):
    await bot.add_cog(Sushi(bot))
