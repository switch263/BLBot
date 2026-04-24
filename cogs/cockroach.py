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

ROACH_NAMES = [
    "Chitin Chad", "Gregory", "Little Stepper", "The Exterminator's Nemesis",
    "Sir Skitters", "Baron von Scuttle", "Roachy McRoachface", "Abdomen Johnson",
    "The Suburban Legend", "Feelers McGee", "Antenna Jones", "Crumb Duke",
    "Trash Panda Jr.", "Diplomatic Immunity", "The 3AM Ghost", "Count Carapace",
]

COMBAT_BEATS = [
    "{a} feints left. {b} isn't falling for it.",
    "{a} bites off one of {b}'s legs. {b} has like 5 more.",
    "{b} throws a cheeto at {a}. It is returned with interest.",
    "{a} and {b} hiss at each other for 40 seconds. The crowd is invested.",
    "{b} does a little dance that is canonically 'scary.'",
    "{a} tries to flip {b} onto its back. {b} is furious.",
    "{a} eats a nearby crumb for the stat boost. {b} is also eating a crumb.",
    "{b} winds up for a haymaker. Connects. {a} yells 'MOM.'",
    "Both roaches enter a staring contest. Both lose. They resume.",
    "{a} monologues. {b} is polite enough to wait.",
]

WINNER_FLOURISHES = [
    "and lands the finisher: a powerbomb from the top rope.",
    "and whispers something in {b}'s ear. {b} simply gives up.",
    "and body-slams {b} into a juicebox.",
    "and just... keeps hitting. Someone call it.",
    "and delivers a speech so scathing {b} dissolves.",
    "and executes {b} with a single well-aimed flick.",
]


class RoachChallenge:
    def __init__(self, challenger: discord.Member, opponent: discord.Member, bet: int,
                 guild_id: int, channel_id: int):
        self.challenger = challenger
        self.opponent = opponent
        self.bet = bet
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.accepted = False
        self.declined = False


class ChallengeView(discord.ui.View):
    def __init__(self, cog, challenge: RoachChallenge):
        super().__init__(timeout=60)
        self.cog = cog
        self.challenge = challenge

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="🪳")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        c = self.challenge
        if interaction.user.id != c.opponent.id:
            await interaction.response.send_message("This challenge isn't for you.", ephemeral=True)
            return
        jmsg = jail_message(c.guild_id, interaction.user.id)
        if jmsg:
            await interaction.response.send_message(jmsg, ephemeral=True)
            return
        if get_coins(c.guild_id, c.opponent.id) < c.bet:
            await interaction.response.send_message(
                f"You can't cover the **{c.bet}** bet.", ephemeral=True)
            return
        if get_coins(c.guild_id, c.challenger.id) < c.bet:
            # Challenger went broke in the meantime
            await interaction.response.send_message(
                f"{c.challenger.display_name} no longer has the coins. Bout cancelled.", ephemeral=True)
            c.declined = True
            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)
            return
        deduct_coins(c.guild_id, c.challenger.id, c.bet)
        deduct_coins(c.guild_id, c.opponent.id, c.bet)
        c.accepted = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        await self.cog._fight(interaction, c)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, emoji="🚫")
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        c = self.challenge
        if interaction.user.id != c.opponent.id:
            await interaction.response.send_message("This challenge isn't for you.", ephemeral=True)
            return
        c.declined = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content=f"🚫 **{c.opponent.display_name}** declined the bout.",
            view=self,
        )

    async def on_timeout(self):
        if not self.challenge.accepted and not self.challenge.declined:
            self.challenge.declined = True
            for item in self.children:
                item.disabled = True


class CockroachFightClub(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Cockroach Fight Club loaded.")

    async def _fight(self, interaction: discord.Interaction, c: RoachChallenge):
        roach_a = random.choice(ROACH_NAMES)
        roach_b = random.choice([n for n in ROACH_NAMES if n != roach_a])

        channel = interaction.channel
        intro = (
            f"🪳 **COCKROACH FIGHT CLUB** 🪳\n"
            f"{c.challenger.mention}'s **{roach_a}** vs {c.opponent.mention}'s **{roach_b}**\n"
            f"Pot: **{c.bet * 2}** coins. The rules are simple: there are no rules."
        )
        msg = await channel.send(intro)
        await asyncio.sleep(2)

        # 3-4 combat beats
        beats = random.sample(COMBAT_BEATS, k=min(4, len(COMBAT_BEATS)))
        for i, beat in enumerate(beats):
            # randomize which is A/B for the beat
            if random.random() < 0.5:
                a, b = roach_a, roach_b
            else:
                a, b = roach_b, roach_a
            line = beat.format(a=a, b=b)
            try:
                new_content = msg.content + f"\n🥊 {line}"
                await msg.edit(content=new_content)
            except discord.HTTPException:
                pass
            await asyncio.sleep(1.6)

        # Winner
        winner_is_challenger = random.random() < 0.5
        if winner_is_challenger:
            winner_member = c.challenger
            winner_roach, loser_roach = roach_a, roach_b
        else:
            winner_member = c.opponent
            winner_roach, loser_roach = roach_b, roach_a
        flourish = random.choice(WINNER_FLOURISHES).format(b=loser_roach)
        payout = c.bet * 2
        add_coins(c.guild_id, winner_member.id, payout)

        final = (
            f"\n💀 **{winner_roach}** {flourish}\n"
            f"🏆 **{winner_member.mention}** wins the pot of **{payout}** coins. "
            f"{loser_roach} has gone to the great garbage disposal in the sky."
        )
        try:
            await msg.edit(content=msg.content + final)
        except discord.HTTPException:
            await channel.send(final)

    async def _start(self, ctx_or_interaction, opponent: discord.Member, bet: int):
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
            await reply("Server only.")
            return
        if opponent.id == user.id:
            await reply("You can't fight yourself. Therapy exists.")
            return
        if opponent.bot:
            await reply("Bots don't fight. They just judge.")
            return
        jmsg = jail_message(guild.id, user.id)
        if jmsg:
            await reply(jmsg)
            return
        if bet <= 0:
            await reply("Put some skin in the game.")
            return
        if get_coins(guild.id, user.id) < bet:
            await reply(f"Too broke for this bout. Balance: **{get_coins(guild.id, user.id)}**")
            return
        if get_coins(guild.id, opponent.id) < bet:
            await reply(f"{opponent.display_name} can't cover the **{bet}** bet.")
            return

        challenge = RoachChallenge(user, opponent, bet, guild.id, channel.id)
        view = ChallengeView(self, challenge)
        content = (
            f"🪳 **{user.display_name}** wants to settle this in the **Cockroach Fight Club**.\n"
            f"{opponent.mention}, you have 60s to accept a bout for **{bet}** coins a side. "
            f"Winner takes **{bet * 2}**."
        )
        await reply(content, view=view)

    @commands.command(name="roach", aliases=["cockroach", "fightclub"])
    @commands.guild_only()
    async def roach_prefix(self, ctx, opponent: discord.Member, bet: int):
        await self._start(ctx, opponent, bet)

    @app_commands.command(name="roach", description="Challenge another user to a cockroach fight. Winner takes the pot.")
    @app_commands.describe(opponent="Who you're calling out", bet="Coins each side antes up")
    async def roach_slash(self, interaction: discord.Interaction, opponent: discord.Member, bet: int):
        await self._start(interaction, opponent, bet)


async def setup(bot):
    await bot.add_cog(CockroachFightClub(bot))
