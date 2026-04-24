import discord
from discord.ext import commands
from discord import app_commands
import random
import sys
import os
import logging
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from economy import get_coins, add_coins, deduct_coins, jail_message

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

FLORIDA_MAN_HEADLINES = [
    "punched a manatee and demanded 50 coins from the gulf",
    "set their own mailbox on fire to 'send a message to the sky'",
    "challenged a vending machine to a duel and lost",
    "was found wearing nothing but a traffic cone and a smile",
    "tried to trade a raccoon for bonus spins",
    "licked a toad and claimed enlightenment, then 50 coins",
    "attempted to deposit a live iguana at the coin ATM",
    "swore at a pelican for 40 minutes with no provocation",
    "declared war on the concept of 'pineapple' in the Publix parking lot",
    "drove a riding mower through a Chick-fil-A drive-thru demanding waffle fries",
    "stole 11 garden gnomes and allegedly 'made them into a council'",
    "was arrested trying to 'exorcise' a Waffle House at 3 AM",
    "wrestled an emu at a quinceañera for reasons unclear to all parties",
    "attempted to marry a pontoon boat in a civil ceremony",
    "claimed to be the rightful heir to the Gulf of Mexico",
    "threw a frozen turkey at a weather reporter live on air",
    "was mistaken for a DeSantis staffer and given $40 anyway",
    "hot-wired a pontoon and joined a flotilla without permission",
    "was found asleep inside a Build-A-Bear holding a crossbow",
    "tried to file a restraining order against a specific cloud",
    "attempted to register an armadillo to vote in the primary",
    "was caught painting 'SEX COINS' on the side of a church in period-accurate Comic Sans",
    "attempted to sell a timeshare of the moon at a Cracker Barrel",
    "was tasered while arguing with a jukebox about Jimmy Buffett royalties",
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
    (5,  "florida_man"),
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
            add_coins(guild_id, user_id, bet * 10)
            return f"🎉 **JACKPOT ×10!** You won **{bet * 9}** coins."

        if outcome == "jackpot_5x":
            add_coins(guild_id, user_id, bet * 5)
            return f"💎 **×5 HIT!** +**{bet * 4}** coins."

        if outcome == "payout_3x":
            add_coins(guild_id, user_id, bet * 3)
            return f"🎰 **×3!** +**{bet * 2}** coins."

        if outcome == "payout_2x":
            add_coins(guild_id, user_id, bet * 2)
            return f"✨ **×2!** +**{bet}** coins."

        if outcome == "break_even":
            add_coins(guild_id, user_id, bet)
            return f"🙃 **Break even.** The wheel is bored. Bet returned."

        if outcome == "nothing":
            return f"💀 **The wheel ate your {bet} coins and stared silently.**"

        if outcome == "lose_extra":
            extra = min(get_coins(guild_id, user_id), bet // 2)
            if extra > 0:
                deduct_coins(guild_id, user_id, extra)
                return f"🪦 **Cursed!** Lost **{bet}** + an extra **{extra}** fee ripped from your wallet."
            return f"🪦 **Cursed!** Lost **{bet}**. Tried to charge you more but you're already broke. Humiliating."

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
                return f"🏚️ **The wheel wanted to pay the audience but nobody's around. Lose {bet}.**"
            per = max(1, bet // len(recent_users))
            for u in recent_users:
                add_coins(guild_id, u.id, per)
            names = ", ".join(u.display_name for u in recent_users)
            return f"🎁 **The wheel is generous (with your money)!** {names} each get **{per}**. You lose **{bet}**."

        if outcome == "pay_random_user":
            members = [m for m in guild.members if not m.bot and m.id != user_id]
            if not members:
                return f"💀 **No lucky winners in sight. Lose {bet}.**"
            lucky = random.choice(members)
            add_coins(guild_id, lucky.id, bet)
            return f"🎰 **The wheel chose a benefactor!** **{lucky.display_name}** pockets your **{bet}** coins."

        if outcome == "florida_man":
            headline = random.choice(FLORIDA_MAN_HEADLINES)
            try:
                await user.send(f"💌 **BREAKING:** *{user.display_name} {headline}.*")
            except discord.Forbidden:
                pass
            return f"📰 **Florida Man Incident!** You lose **{bet}** and your dignity. Check your DMs."

        if outcome == "silly_nickname":
            nick = random.choice(SILLY_NICKNAMES)
            member = guild.get_member(user_id)
            if member:
                old_nick = member.nick
                try:
                    await member.edit(nick=nick, reason="Wheel of Misfortune")
                    asyncio.create_task(self._restore_nickname(member, old_nick, 3600))
                    return f"🤡 **CURSED!** You are now **{nick}** for 1 hour. Also lose **{bet}**."
                except discord.Forbidden:
                    return f"🤡 The wheel tried to rename you to **{nick}** but the bot lacks permissions. Lose **{bet}** anyway, coward."
            return f"🤡 Somehow couldn't curse you. Lose **{bet}** regardless."

        if outcome == "wheel_again":
            bonus = self._pick_outcome()
            while bonus == "wheel_again":
                bonus = self._pick_outcome()
            bonus_text = await self._apply_outcome(bonus, bet, user, guild, channel)
            return f"🔄 **FREE BONUS SPIN!** The wheel re-rolls...\n↳ {bonus_text}"

        return "???"

    async def _do_spin(self, ctx_or_interaction, bet: int):
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
            await reply("Can only spin in a server.")
            return
        jmsg = jail_message(guild.id, user.id)
        if jmsg:
            await reply(jmsg)
            return
        if bet <= 0:
            await reply("Bet more than 0, cheapskate.")
            return
        balance = get_coins(guild.id, user.id)
        if balance < bet:
            await reply(f"You're too broke. Balance: **{balance}**")
            return

        deduct_coins(guild.id, user.id, bet)

        frames = [
            "🎡 **Spinning the Wheel of Misfortune...**",
            "🎡 *clack clack clack clack*",
            "🎡 *cla...ck...  cla......ck*",
            "🎡 *It lands on...*",
        ]
        msg = await reply(frames[0])
        for frame in frames[1:]:
            await asyncio.sleep(0.9)
            try:
                await msg.edit(content=frame)
            except discord.HTTPException:
                break

        outcome = self._pick_outcome()
        result = await self._apply_outcome(outcome, bet, user, guild, channel)
        final = (
            f"🎡 **{user.display_name}** fed the Wheel of Misfortune **{bet}** coins.\n"
            f"{result}\n"
            f"Balance: **{get_coins(guild.id, user.id)}**"
        )
        try:
            await msg.edit(content=final)
        except discord.HTTPException:
            await channel.send(final)

    @commands.command(name="wheel", aliases=["misfortune", "wom"])
    @commands.guild_only()
    async def wheel_prefix(self, ctx, bet: int):
        await self._do_spin(ctx, bet)

    @app_commands.command(name="wheel", description="Spin the Wheel of Misfortune. Chaotic outcomes guaranteed.")
    @app_commands.describe(bet="How many coins you're feeding the wheel")
    async def wheel_slash(self, interaction: discord.Interaction, bet: int):
        await self._do_spin(interaction, bet)


async def setup(bot):
    await bot.add_cog(WheelOfMisfortune(bot))
