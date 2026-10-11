import discord
from discord.ext import commands
from discord import app_commands
import random
import logging
import asyncio

from economy import get_coins, transfer_to_house, casino_payout, record_game
from game_common import casino_prelude

logger = logging.getLogger(__name__)

SILLY_NICKNAMES = [
    "Wheel Goblin", "Coin Simp", "Jackpot Jester", "Bet Regretter",
    "Ambient Moron", "Uncle Crypto", "Lord Lossington", "Tax Goblin",
    "Mr. Brokelord", "Discount Degen", "Wheel Wrecker", "Certified L",
    "The Cursed One", "Lil Refund", "Bankruptcy Boy", "Wheel Widow",
    "Sir Payeth-a-Lot", "Nickel Nephew", "Casino Crustacean", "Wallet Wraith",
    "Dame Debt", "Professor Paycut", "The Malf", "Slot Cousin",
    "Count Chargeback", "Doctor Deficit", "Baron Bankrupt", "The Wager Weasel",
    "His Majesty King Lossington III", "Sir Clicks-a-Lot", "Premium Peasant",
    "The Tiltmaster", "Lil Evaporator", "Big Mistake Energy", "Financial Gremlin",
    "The Inverse Midas", "Couponless", "Scholarship Loser", "Subprime Sam",
]

# (weight, key)
OUTCOMES = [
    (2,  "jackpot_10x"),
    (3,  "jackpot_5x"),
    (5,  "payout_3x"),
    (10, "payout_2x"),
    (15, "break_even"),
    (25, "nothing"),
    (10, "lose_extra"),
    (10, "pay_channel"),
    (5,  "pay_random_user"),
    (5,  "silly_nickname"),
    (5,  "wheel_again"),
]


class WheelOfMisfortune(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Wheel of Misfortune loaded.")

    def _pick_outcome(self) -> str:
        total = sum(w for w, _ in OUTCOMES)
        roll = random.uniform(0, total)
        running = 0.0
        for weight, key in OUTCOMES:
            running += weight
            if roll <= running:
                return key
        return OUTCOMES[-1][1]

    async def _restore_nickname(self, member: discord.Member, old_nick, delay: int):
        try:
            await asyncio.sleep(delay)
            await member.edit(nick=old_nick, reason="Wheel of Misfortune curse expired")
        except discord.HTTPException:
            pass

    async def _apply_outcome(self, outcome: str, bet: int, user: discord.Member,
                             guild: discord.Guild, channel: discord.TextChannel) -> str:
        guild_id = guild.id
        user_id = user.id

        if outcome == "jackpot_10x":
            paid = casino_payout(guild_id, user_id, bet * 10)
            short = f" *(house was short — owed {bet*10:,})*" if paid < bet * 10 else ""
            return f"🎉 **JACKPOT ×10!** You won **{paid - bet:+,}** coins.{short}"

        if outcome == "jackpot_5x":
            paid = casino_payout(guild_id, user_id, bet * 5)
            short = f" *(house was short — owed {bet*5:,})*" if paid < bet * 5 else ""
            return f"💎 **×5 HIT!** **{paid - bet:+,}** coins.{short}"

        if outcome == "payout_3x":
            paid = casino_payout(guild_id, user_id, bet * 3)
            short = f" *(house was short — owed {bet*3:,})*" if paid < bet * 3 else ""
            return f"🎰 **×3!** **{paid - bet:+,}** coins.{short}"

        if outcome == "payout_2x":
            paid = casino_payout(guild_id, user_id, bet * 2)
            short = f" *(house was short — owed {bet*2:,})*" if paid < bet * 2 else ""
            return f"✨ **×2!** **{paid - bet:+,}** coins.{short}"

        if outcome == "break_even":
            casino_payout(guild_id, user_id, bet)
            return "🙃 **Break even.** The wheel is bored. Bet returned."

        if outcome == "nothing":
            return f"💀 **The wheel ate your {bet:,} coins and stared silently.**"

        if outcome == "lose_extra":
            extra_target = bet // 2
            extra = 0
            if extra_target > 0:
                extra_result = transfer_to_house(guild_id, user_id, extra_target)
                if extra_result.get("ok"):
                    extra = extra_target
            if extra > 0:
                return f"🪦 **Cursed!** Lost **{bet:,}** + an extra **{extra:,}** fee ripped from your wallet."
            return f"🪦 **Cursed!** Lost **{bet:,}**. Tried to charge you more but you're already broke. Humiliating."

        if outcome == "pay_channel":
            recent_users = []
            try:
                async for msg in channel.history(limit=50):
                    if msg.author.bot or msg.author.id == user_id:
                        continue
                    if msg.author.id not in [u.id for u in recent_users]:
                        recent_users.append(msg.author)
                    if len(recent_users) >= 5:
                        break
            except discord.HTTPException:
                pass
            if not recent_users:
                return f"🏚️ **The wheel wanted to pay the audience but nobody's around. Lose {bet:,}.**"
            per = max(1, bet // len(recent_users))
            for u in recent_users:
                casino_payout(guild_id, u.id, per)
            names = ", ".join(u.display_name for u in recent_users)
            return f"🎁 **The wheel is generous (with your money)!** {names} each get **{per:,}**. You lose **{bet:,}**."

        if outcome == "pay_random_user":
            members = [m for m in guild.members if not m.bot and m.id != user_id]
            if not members:
                return f"💀 **No lucky winners in sight. Lose {bet:,}.**"
            lucky = random.choice(members)
            casino_payout(guild_id, lucky.id, bet)
            return f"🎰 **The wheel chose a benefactor!** **{lucky.display_name}** pockets your **{bet:,}** coins."

        if outcome == "silly_nickname":
            nick = random.choice(SILLY_NICKNAMES)
            member = guild.get_member(user_id)
            if member:
                old_nick = member.nick
                try:
                    await member.edit(nick=nick, reason="Wheel of Misfortune")
                    asyncio.create_task(self._restore_nickname(member, old_nick, 3600))
                    return f"🤡 **CURSED!** You are now **{nick}** for 1 hour. Also lose **{bet:,}**."
                except discord.Forbidden:
                    return f"🤡 The wheel tried to rename you to **{nick}** but the bot lacks permissions. Lose **{bet:,}** anyway, coward."
            return f"🤡 Somehow couldn't curse you. Lose **{bet:,}** regardless."

        return "???"

    async def _do_spin(self, ctx_or_interaction, bet):
        start = await casino_prelude(ctx_or_interaction, bet, zero_msg="Bet more than 0, cheapskate.",
                                     no_guild_msg="Can only spin in a server.")
        if start is None:
            return
        guild, user, bet, reply = start.guild, start.user, start.bet, start.reply

        frames = [
            "🎡 **Spinning the Wheel of Misfortune...**",
            "🎡 *clack clack clack clack*",
            "🎡 *cla...ck...  cla......ck*",
            "🎡 *It lands on...*",
        ]
        msg = await reply(frames[0])
        channel = msg.channel  # pay_channel outcome scans history for recipients
        for frame in frames[1:]:
            await asyncio.sleep(0.9)
            try:
                await msg.edit(content=frame)
            except discord.HTTPException:
                break

        outcome = self._pick_outcome()
        # wheel_again is a re-roll wrapper — resolve it here so the recorded
        # stat is the outcome that actually settled, not the wrapper.
        rerolled = outcome == "wheel_again"
        while outcome == "wheel_again":
            outcome = self._pick_outcome()
        result = await self._apply_outcome(outcome, bet, user, guild, channel)
        if rerolled:
            result = f"🔄 **FREE BONUS SPIN!** The wheel re-rolls...\n↳ {result}"
        record_game(guild.id, user.id, "wheel",
                    won=outcome in ("jackpot_10x", "jackpot_5x", "payout_3x", "payout_2x"))
        final = (
            f"🎡 **{user.display_name}** fed the Wheel of Misfortune **{bet:,}** coins.\n"
            f"{result}\n"
            f"Balance: **{get_coins(guild.id, user.id):,}**"
        )
        try:
            await msg.edit(content=final)
        except discord.HTTPException:
            await channel.send(final)

    @commands.command(name="wheel", aliases=["misfortune", "wom"])
    @commands.guild_only()
    async def wheel_prefix(self, ctx, bet: str):
        await self._do_spin(ctx, bet)

    @app_commands.command(name="wheel", description="Spin the Wheel of Misfortune. Chaotic outcomes guaranteed.")
    @app_commands.describe(bet="How many coins you're feeding the wheel — supports 1k, 5m, all, half, 50%")
    async def wheel_slash(self, interaction: discord.Interaction, bet: str):
        await self._do_spin(interaction, bet)


async def setup(bot):
    await bot.add_cog(WheelOfMisfortune(bot))
