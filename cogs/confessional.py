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

# Each verdict is a (weight, name, mult, priest_line_template)
# {sin} is the user's text, {name} is their display name.
# Multiplier applied to bet: 0 = lose bet, 1 = break even, >1 = win.
VERDICTS = [
    # Blessings (rare, lucrative)
    (2, "DIVINE ABSOLUTION", 10.0,
     "🕊️ *The priest falls to his knees.* 'My child... **{sin}**?! That's the greatest thing I've ever heard. God Himself has wired you 10× your offering.'"),
    (4, "HOLY BENEDICTION", 5.0,
     "✨ The priest hiccups, loudly. 'Listen. Listen. *That* — what you just said — **{sin}** — that *owns*. 5× blessing.' He burps."),
    (7, "BLESSED ASSURANCE", 3.0,
     "⛪ *The priest nods solemnly, eyes closed, mostly because he's passed out.* 'I absolve thee at a 3× rate. Walk with God. Also walk straight.'"),
    (12, "PENITENT DISCOUNT", 2.0,
     "🍷 The priest sways. 'For a sin of that caliber — **{sin}** — the Lord would like to offer you double back. Limited-time.'"),
    # Break even
    (15, "SUSPICIOUSLY NEUTRAL", 1.0,
     "🤔 The priest squints. 'I've heard worse. I've heard *so* much worse. Take your money back and go.'"),
    # Losses (common, mid flavor)
    (20, "STANDARD PENANCE", 0.0,
     "📜 'For **{sin}**, the Church demands your entire offering and 10 Hail Marys. Don't ask which 10.'"),
    (15, "UNAMUSED", 0.0,
     "😐 The priest stares at you for 30 full seconds. 'Pay your tithe and leave, {name}.' (You lose your bet.)"),
    (10, "SIN TAX", 0.0,
     "💀 'That'll cost you, my child.' The priest pockets your coins visibly."),
    # Damnations (rare, extra punishment)
    (8, "DAMNATION", -0.5,
     "🔥 The priest stands up. His wine glass shatters in his hand. 'YOU DID **{sin}**?!' He takes your bet AND a 'damnation surcharge.'"),
    (4, "EXCOMMUNICATION", -1.0,
     "⛓️ *'LEAVE THIS PLACE, {name}. AND TAKE YOUR MONEY. AND ALSO PAY A FINE.'* You are ejected. You pay double."),
    (3, "POSSESSION FEE", -0.75,
     "👹 The priest's head turns 360°. A demonic voice says: 'We like what **{sin}** represents. But we still demand tribute.' Lose bet + 75% fine."),
]


class Confessional(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Drunken Confessional loaded.")

    def _pick_verdict(self):
        total = sum(w for w, _, _, _ in VERDICTS)
        roll = random.uniform(0, total)
        running = 0.0
        for weight, name, mult, line in VERDICTS:
            running += weight
            if roll <= running:
                return name, mult, line
        return VERDICTS[-1][1], VERDICTS[-1][2], VERDICTS[-1][3]

    async def _do_confess(self, ctx_or_interaction, sin: str, bet: int):
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
        sin = sin.strip()
        if not sin:
            await reply("You gotta actually confess SOMETHING.")
            return
        if len(sin) > 200:
            sin = sin[:200] + "..."
        if bet <= 0:
            await reply("No tithe, no trial.")
            return
        if get_coins(guild.id, user.id) < bet:
            await reply(f"Too broke to tithe. Balance: **{get_coins(guild.id, user.id)}**")
            return

        deduct_coins(guild.id, user.id, bet)
        verdict_name, mult, line = self._pick_verdict()
        priest_line = line.format(sin=sin, name=user.display_name)

        if mult >= 1.0:
            payout = int(bet * mult)
            add_coins(guild.id, user.id, payout)
            net = payout - bet
            result = f"**+{net}** coins."
        elif mult == 0.0:
            result = f"**Lost {bet}** coins."
        else:
            extra = min(get_coins(guild.id, user.id), int(abs(mult) * bet))
            if extra > 0:
                deduct_coins(guild.id, user.id, extra)
                result = f"**Lost {bet}** + extra **{extra}** penalty."
            else:
                result = f"**Lost {bet}**. Was going to fine you more but you're broke."

        text = (
            f"⛪ **{user.display_name}** kneels in the confessional and confesses: _'{sin}'_\n"
            f"Tithe: **{bet}** coins.\n\n"
            f"**Verdict: {verdict_name}** ({mult:.2f}×)\n"
            f"{priest_line}\n\n"
            f"{result} Balance: **{get_coins(guild.id, user.id)}**"
        )
        await reply(text)

    @commands.command(name="confess", aliases=["confession"])
    @commands.guild_only()
    async def confess_prefix(self, ctx, bet: int, *, sin: str):
        """Usage: !confess <bet> <your sin>"""
        await self._do_confess(ctx, sin, bet)

    @app_commands.command(name="confess", description="Confess to a drunken priest for random divine judgment and coin consequences.")
    @app_commands.describe(sin="What you need to confess", bet="Tithe you offer the priest")
    async def confess_slash(self, interaction: discord.Interaction, sin: str, bet: int):
        await self._do_confess(interaction, sin, bet)


async def setup(bot):
    await bot.add_cog(Confessional(bot))
