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

# Each "slot" button picks from a weighted outcome table. The fun is in the flavor.
SODAS = [
    ("A1", "🥤 Toilet Cola"),
    ("B2", "🧃 Crungus Juice"),
    ("C3", "🧪 Unlabeled Green Liquid"),
    ("D4", "🍾 Stolen Church Wine"),
    ("E5", "🥫 Radioactive Ecto-Cooler"),
    ("F6", "🍺 Expired Busch Light"),
]

# Which soda got picked doesn't bias outcomes, but the name is rotated in randomly
# to add variety. These expand the named-drink flavor pool.
EXTRA_SODAS = [
    "💀 Boney Fanta",
    "🦷 Dentist's Choice Kombucha",
    "🐛 Tennessee Yard Tea",
    "🌶️ Arizona Punk Rock Cactus Blast",
    "🔋 Discount Liquid Battery",
    "🧃 Off-Brand Sunny D (store brand: 'Cloudy A-')",
    "🫧 Gentleman's Seltzer",
    "💉 Cough Syrup & Cream",
    "🧻 3-Ply Ginger Beer",
    "🚬 Smoker's Root Beer",
    "🐡 Pufferfish Pepsi",
    "👢 Bootleg Dr. Pepper (labeled 'DR. PAPPER')",
]

# (weight, key)
OUTCOMES = [
    (2,  "jackpot"),       # 10x
    (4,  "big_win"),       # 5x
    (8,  "medium_win"),    # 3x
    (14, "small_win"),     # 2x
    (14, "break_even"),
    (24, "nothing"),       # lose bet
    (12, "extra_loss"),    # lose bet + small extra
    (8,  "pay_channel"),   # bet goes to recent chatters
    (6,  "cursed_nick"),   # silly nickname for 1h
    (6,  "insult_dm"),     # lose + get DM'd an insult
    (2,  "explosion"),     # lose bet + extra big fee, dramatic
]

CURSED_NICKS = [
    "Machine Simp", "Soda Goblin", "Vending Victim", "Flavor Fiend",
    "Carbonation Casualty", "The Sticky One", "Dispenser Dependent",
    "Certified L (soda edition)", "Lil Fizz Regret", "Dr. Pepper's Intern",
    "Mountain Don't", "Sprite Goblin", "The Carbonated Disappointment",
    "Dented Can", "The Jammed One", "Gatorade's Least Favorite Flavor",
    "Dasani Defender", "Off-Brand Enthusiast", "Sir Jams-a-Lot",
    "Shaken (Not Stirred)", "Vending Crimes", "Sticky Fingers Jr.",
    "Concession Stand Caleb", "Your Honor's Least Favorite",
]

INSULTS = [
    "the machine wants you to know it thinks less of you than it did yesterday, and it didn't think much then",
    "your breath smells like expired aspirations",
    "somewhere, a vending machine in a hospital is doing real work, and you are here",
    "the can laughed at you on the way down",
    "even the spiders in here are disappointed",
    "the receipt paper shivered when it printed your name",
    "you have the aura of a break room at a regional bank",
    "you are technically a Ponzi scheme of one",
    "every machine in a 3-mile radius filed a complaint about you",
    "the soda was trying to escape YOU",
    "someone at corporate is getting fired because of you, and they deserve it",
    "the machine has a LinkedIn. You do not. Figure that out",
    "a crow just flew past. it was better than you at this",
]

FLAVOR_PULL = [
    "You kick the machine. It kicks back.",
    "The glass is sticky. Don't think about why.",
    "A light flickers. Somewhere a crow caws.",
    "The coin slot makes a noise it definitely shouldn't.",
    "You can hear the machine breathing.",
    "A tiny sign reads: ALL SALES FINAL. NO EXCEPTIONS. NO GOD.",
    "The reflection in the glass is not yours.",
    "You feel a small tug at your ankle. You do not look down.",
    "The machine smells faintly of barbecue. And sulfur.",
    "A moth circles inside the machine. It's been there for years.",
    "The LED display flickers between '$1.25' and 'REPENT'.",
    "A low hum. Not electrical. Something else.",
    "The keypad is warm. Like. Body temperature warm.",
    "A tiny child's handprint is smudged on the coin return.",
    "There's a single M&M wedged in the coin slot. Don't touch it.",
    "The machine accepts your coin. It also accepts your regret.",
]


class VendingView(discord.ui.View):
    def __init__(self, cog, user_id: int, bet: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id
        self.bet = bet
        for slot_id, soda_name in SODAS:
            self.add_item(SlotButton(slot_id, soda_name))


class SlotButton(discord.ui.Button):
    def __init__(self, slot_id: str, soda_name: str):
        super().__init__(style=discord.ButtonStyle.primary, label=f"{slot_id}: {soda_name}")
        self.slot_id = slot_id
        self.soda_name = soda_name

    async def callback(self, interaction: discord.Interaction):
        view: VendingView = self.view  # type: ignore
        if interaction.user.id != view.user_id:
            await interaction.response.send_message("Not your machine.", ephemeral=True)
            return
        for child in view.children:
            child.disabled = True
        self.style = discord.ButtonStyle.success
        await view.cog._dispense(interaction, view, self.slot_id, self.soda_name)


class VendingMachine(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Vending Machine From Hell loaded.")

    def _pick_outcome(self) -> str:
        total = sum(w for w, _ in OUTCOMES)
        roll = random.uniform(0, total)
        running = 0.0
        for weight, key in OUTCOMES:
            running += weight
            if roll <= running:
                return key
        return OUTCOMES[-1][1]

    async def _restore_nickname(self, member, old_nick, delay):
        try:
            await asyncio.sleep(delay)
            await member.edit(nick=old_nick, reason="Vending Machine curse expired")
        except discord.HTTPException:
            pass

    async def _apply_outcome(self, outcome: str, bet: int, user: discord.Member,
                             guild: discord.Guild, channel: discord.TextChannel) -> str:
        gid = guild.id
        uid = user.id
        if outcome == "jackpot":
            add_coins(gid, uid, bet * 10)
            return f"💎 **JACKPOT.** The can was stuffed with hundred-dollar bills. **+{bet * 9}** coins."
        if outcome == "big_win":
            add_coins(gid, uid, bet * 5)
            return f"🎰 **×5!** Crungus smiles upon you. **+{bet * 4}** coins."
        if outcome == "medium_win":
            add_coins(gid, uid, bet * 3)
            return f"✨ **×3!** The soda is also cold. **+{bet * 2}** coins."
        if outcome == "small_win":
            add_coins(gid, uid, bet * 2)
            return f"🥤 **×2!** It's drinkable. **+{bet}** coins."
        if outcome == "break_even":
            add_coins(gid, uid, bet)
            return f"😐 **Break even.** The can is empty but the coin fell back out. Weird."
        if outcome == "nothing":
            return f"💀 **Nothing drops.** The machine takes your **{bet}** and whistles innocently."
        if outcome == "extra_loss":
            extra = min(get_coins(gid, uid), bet // 2)
            if extra > 0:
                deduct_coins(gid, uid, extra)
                return f"🪦 **The machine charges a processing fee.** Lost **{bet}** + an extra **{extra}**."
            return f"🪦 **Processing fee attempted, but you're broke.** Lost **{bet}**."
        if outcome == "pay_channel":
            recent = []
            try:
                async for msg in channel.history(limit=50):
                    if msg.author.bot or msg.author.id == uid:
                        continue
                    if msg.author.id not in [u.id for u in recent]:
                        recent.append(msg.author)
                    if len(recent) >= 4:
                        break
            except discord.HTTPException:
                pass
            if not recent:
                return f"🏚️ **The machine dispenses a pity handful of receipts.** Lose **{bet}**."
            per = max(1, bet // len(recent))
            for u in recent:
                add_coins(gid, u.id, per)
            names = ", ".join(u.display_name for u in recent)
            return f"🎁 **The machine is generous... to others.** {names} each get **{per}** from your **{bet}**."
        if outcome == "cursed_nick":
            nick = random.choice(CURSED_NICKS)
            member = guild.get_member(uid)
            if member:
                old = member.nick
                try:
                    await member.edit(nick=nick, reason="Vending Machine curse")
                    asyncio.create_task(self._restore_nickname(member, old, 3600))
                    return f"🤡 **Branded!** You are **{nick}** for 1 hour. Also lose **{bet}**."
                except discord.Forbidden:
                    pass
            return f"🤡 Tried to brand you **{nick}** but couldn't. Lose **{bet}** anyway."
        if outcome == "insult_dm":
            try:
                await user.send(f"💌 A wet receipt slides out of a nearby machine. It reads: *{random.choice(INSULTS)}*")
            except discord.Forbidden:
                pass
            return f"📃 **A receipt slides out. It is not kind.** Lose **{bet}**. Check DMs."
        if outcome == "explosion":
            extra = min(get_coins(gid, uid), bet)
            if extra > 0:
                deduct_coins(gid, uid, extra)
            return (
                f"💥 **THE MACHINE EXPLODES.** Glass, soda, and regret everywhere. "
                f"Lose **{bet}** + **{extra}** in damages. You are also wet."
            )
        return "???"

    async def _dispense(self, interaction: discord.Interaction, view: VendingView,
                        slot_id: str, soda_name: str):
        outcome = self._pick_outcome()
        result = await self._apply_outcome(
            outcome, view.bet, interaction.user, interaction.guild, interaction.channel,
        )
        flavor = random.choice(FLAVOR_PULL)
        # 30% of the time, the machine gives you something you did NOT ask for.
        if random.random() < 0.3:
            wrong = random.choice(EXTRA_SODAS)
            pick_line = f"picks **{slot_id}: {soda_name}**, receives **{wrong}** instead"
        else:
            pick_line = f"picks **{slot_id}: {soda_name}**"
        text = (
            f"🎛️ **{interaction.user.display_name}** {pick_line}.\n"
            f"_{flavor}_\n"
            f"{result}\n"
            f"Balance: **{get_coins(interaction.guild.id, interaction.user.id)}**"
        )
        await interaction.response.edit_message(content=text, view=view)

    async def _start(self, ctx_or_interaction, bet: int):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild
        user = ctx_or_interaction.user if is_slash else ctx_or_interaction.author

        async def reply(content, **kwargs):
            if is_slash:
                await ctx_or_interaction.response.send_message(content, **kwargs)
                return await ctx_or_interaction.original_response()
            return await ctx_or_interaction.send(content, **kwargs)

        if not guild:
            await reply("Only in a server, weirdo.")
            return
        jmsg = jail_message(guild.id, user.id)
        if jmsg:
            await reply(jmsg)
            return
        if bet <= 0:
            await reply("Gotta feed it something.")
            return
        if get_coins(guild.id, user.id) < bet:
            await reply(f"Too broke. Balance: **{get_coins(guild.id, user.id)}**")
            return

        deduct_coins(guild.id, user.id, bet)
        view = VendingView(self, user.id, bet)
        content = (
            f"🤖 **THE VENDING MACHINE FROM HELL** accepts **{user.display_name}**'s offering of **{bet}** coins.\n"
            f"Pick a slot. You probably shouldn't."
        )
        await reply(content, view=view)

    @commands.command(name="vend", aliases=["vendingmachine", "hellvend"])
    @commands.guild_only()
    async def vend_prefix(self, ctx, bet: int):
        await self._start(ctx, bet)

    @app_commands.command(name="vend", description="Feed the Vending Machine From Hell. It does not like you.")
    @app_commands.describe(bet="Coins to offer the machine")
    async def vend_slash(self, interaction: discord.Interaction, bet: int):
        await self._start(interaction, bet)


async def setup(bot):
    await bot.add_cog(VendingMachine(bot))
