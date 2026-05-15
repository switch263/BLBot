import discord
from discord.ext import commands
from discord import app_commands
import random
import time
import logging

from economy import (
    get_coins, jail_message, jail_remaining,
    get_active_jails, pay_bail, jail_user,
    casino_payout,
)

logger = logging.getLogger(__name__)

# (weight, multiplier, bondsman_jail_seconds, flavor)
# Multiplier applies to the bail amount; the bondsman's "bet" is whatever the
# inmate's bail happens to be. mult >= 1.0 = profit. 0.0 = total loss.
# bondsman_jail_seconds > 0 = the bondsman themselves gets locked up.
BOND_OUTCOMES = [
    (5,  3.0, 0,
     "🎰 Client hits the Powerball that night. Tips you absurdly on the way out."),
    (18, 1.6, 0,
     "Client pays in full plus a fat vig. Cash hand-delivered in a paper bag."),
    (25, 1.3, 0,
     "Standard vig collected. Smooth pickup. You buy yourself a sandwich."),
    (15, 1.0, 0,
     "Client pays back exact bail — no vig, no skip. Lawful good of them."),
    (15, 0.5, 0,
     "Client skipped. You tracked them to a Waffle House mid-omelet. Half-recovery."),
    (12, 0.0, 0,
     "Client skipped clean. Blocked your number. Bail money is gone."),
    (4,  4.0, 0,
     "Client is a county judge. Throws you a fat municipal contract. Huge payout."),
    (3,  0.0, 60 * 30,
     "Client was an undercover agent. YOU eat the bond-tampering charge. 30m."),
    (2,  6.0, 0,
     "Client co-signs you onto a class-action. You ride their coattails to Cabo."),
    (1,  0.0, 60 * 90,
     "Client was a federal asset. FBI sweats you for 90 minutes about everyone you've bailed."),
]


def _pick_outcome():
    total = sum(w for w, *_ in BOND_OUTCOMES)
    roll = random.uniform(0, total)
    running = 0.0
    for weight, mult, jail_s, flavor in BOND_OUTCOMES:
        running += weight
        if roll <= running:
            return mult, jail_s, flavor
    return BOND_OUTCOMES[-1][1], BOND_OUTCOMES[-1][2], BOND_OUTCOMES[-1][3]


def _format_duration(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, _s = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


class BailBonds(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Bail Bonds loaded.")

    # ---- Board listing -------------------------------------------------

    def _format_board(self, guild: discord.Guild) -> str:
        rows = get_active_jails(guild.id)
        bondable = [r for r in rows if r.get("bail_amount", 0) > 0]
        if not bondable:
            return "📋 **Bail Bonds Board** — no bondable inmates right now. Quiet night."
        bondable.sort(key=lambda r: r["bail_amount"], reverse=True)
        lines = ["📋 **Bail Bonds Board** — currently bondable inmates:"]
        for r in bondable[:15]:
            member = guild.get_member(r["user_id"])
            name = member.display_name if member else f"<id:{r['user_id']}>"
            bail = r["bail_amount"]
            reason = r["reason"] or "Unspecified mayhem"
            remaining = max(0, int(r["until_ts"] - time.time()))
            lines.append(
                f"• **{name}** — bail **{bail:,}** — {_format_duration(remaining)} left — _{reason}_"
            )
        lines.append("")
        lines.append("Use `/bailbonds @user` to post their bond. Outcome roll is your problem.")
        return "\n".join(lines)

    # ---- Post a bond ---------------------------------------------------

    async def _do_post(self, guild: discord.Guild, payer: discord.Member,
                       jailed: discord.Member, channel_id: int) -> str:
        if jailed.bot:
            return "The house doesn't deal in bot bonds. They have nothing to lose."
        if jailed.id == payer.id:
            return "🚫 You can't bondsman yourself — that's just `/bail`. Use that."
        if jail_remaining(guild.id, payer.id) > 0:
            return "🚫 You're in jail. Bondsmen don't operate from the inside. Spring yourself first."

        result = pay_bail(guild.id, jailed.id, payer.id)
        if not result.get("ok"):
            err = result.get("error")
            if err == "not_jailed":
                return f"✅ **{jailed.display_name}** isn't in casino jail. No bond to post."
            if err == "sentence_done":
                return f"✅ **{jailed.display_name}**'s sentence is up — the doors are already opening."
            if err == "no_bail":
                return f"⛔ **{jailed.display_name}** has no bail set. They have to serve it."
            if err == "cooldown":
                cd = result.get("cooldown_remaining", 0)
                return (f"⏳ **{jailed.display_name}** was bailed too recently. "
                        f"Try again in **{_format_duration(cd)}**.")
            if err == "broke":
                return (f"💸 Posting this bond requires **{result.get('need', 0):,} coins** up front. "
                        f"You have **{result.get('have', 0):,}**.")
            return "⚠️ The clerk lost your paperwork. Try again in a moment."

        bail = result["amount"]
        mult, jail_s, flavor = _pick_outcome()
        requested = int(bail * mult)
        payout = casino_payout(guild.id, payer.id, requested) if requested > 0 else 0
        short_note = ""
        if requested > 0 and payout < requested:
            short_note = f" *(house was short — owed {requested:,})*"
        net = payout - bail

        lines = [
            f"💼 **{payer.display_name}** posts **{bail:,}** for {jailed.mention} — they walk free.",
            "",
            f"_{flavor}_",
        ]
        if jail_s > 0:
            bondsman_bail = max(50, int(bail * 0.3))
            jail_user(
                guild.id, payer.id, jail_s,
                reason="Bond-tampering charges",
                bail_amount=bondsman_bail, channel_id=channel_id,
            )
            lines.append(
                f"🚔 **{payer.display_name}** is now in casino jail for **{_format_duration(jail_s)}**. "
                f"Bail: **{bondsman_bail:,}**."
            )
        if net > 0:
            lines.append(f"📈 Net: **+{net:,}** coins.{short_note}")
        elif net == 0:
            lines.append(f"⚖️ Net: **break-even**.{short_note}")
        else:
            lines.append(f"📉 Net: **{net:,}** coins.{short_note}")
        lines.append(f"Balance: **{get_coins(guild.id, payer.id):,}**")
        return "\n".join(lines)

    # ---- Commands ------------------------------------------------------

    @commands.command(name="bondboard", aliases=["bonds", "bailboard"])
    @commands.guild_only()
    async def bondboard_prefix(self, ctx):
        await ctx.send(self._format_board(ctx.guild))

    @app_commands.command(name="bondboard", description="See currently-jailed users you could post bond on.")
    async def bondboard_slash(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Server only.")
            return
        await interaction.response.send_message(self._format_board(interaction.guild))

    @commands.command(name="bailbonds", aliases=["bondsman", "postbond"])
    @commands.guild_only()
    async def bailbonds_prefix(self, ctx, member: discord.Member = None):
        if member is None:
            await ctx.send("Usage: `!bailbonds @user` — see `!bondboard` for the current inmate list.")
            return
        channel_id = getattr(ctx.channel, "id", 0)
        msg = await self._do_post(ctx.guild, ctx.author, member, channel_id)
        await ctx.send(msg)

    @app_commands.command(name="bailbonds", description="Post bond on a jailed user. Roll for vig — or for jail.")
    @app_commands.describe(member="The jailed user you're posting bond on")
    async def bailbonds_slash(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.guild:
            await interaction.response.send_message("Server only.")
            return
        channel_id = getattr(interaction.channel, "id", 0)
        msg = await self._do_post(interaction.guild, interaction.user, member, channel_id)
        await interaction.response.send_message(msg)


async def setup(bot):
    await bot.add_cog(BailBonds(bot))
