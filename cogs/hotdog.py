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

# Each eat: +MULT_PER_DOG to the multiplier, +HURL_INCREMENT to hurl chance.
MULT_PER_DOG = 0.30
HURL_START = 0.04
HURL_INCREMENT = 0.045
MAX_DOGS = 10

DOG_NAMES = [
    "a gas-station tubesteak of unknown provenance",
    "a hot dog someone's mom made with LOVE",
    "a suspicious chili dog that is MOSTLY chili",
    "the dreaded 'Ol' Gray Uncle' — nobody knows how old",
    "a 7-Eleven roller dog that's been rolling since Tuesday",
    "a bacon-wrapped kingdom dog with visible regret",
    "a dubious kielbasa in a bun that is technically ADA-compliant",
    "a corn dog in the Texas style (big, aggressive)",
    "a Chicago dog that SCREAMED at you for the ketchup",
    "a Wal-Mart brand 'Franken-Frank' — allegedly meat",
]

HURL_MESSAGES = [
    "**HWAAAAARGH.** The stomach has filed a grievance. You lose it all.",
    "**BLOORF.** Turns out dog #{n} was the limit. Everything comes back.",
    "**GAME OVER.** The chili took a look around, said 'nah', and left.",
    "**Tactical emesis.** The judges weep. You lose your bet.",
    "**The dam breaks.** Your shirt is ruined. So are your finances.",
]

BANK_MESSAGES = [
    "You lift your arms in shaky victory. The judges nod. Bank!",
    "You wipe the mustard from your chin and walk away with your dignity.",
    "You tap out before disaster. Wisdom.",
    "Your stomach thanks you later. For now, take your winnings.",
]


class HotDogGame:
    def __init__(self, guild_id, user_id, user_name, bet):
        self.guild_id = guild_id
        self.user_id = user_id
        self.user_name = user_name
        self.bet = bet
        self.eaten = 0
        self.multiplier = 1.0
        self.log: list[str] = []
        self.ended = False


class HotDogView(discord.ui.View):
    def __init__(self, cog, game: HotDogGame):
        super().__init__(timeout=180)
        self.cog = cog
        self.game = game

    def _refresh(self):
        payout = int(self.game.bet * self.game.multiplier)
        net = payout - self.game.bet
        self.bank_button.label = f"Tap Out ({self.game.multiplier:.2f}×, +{net})"
        self.eat_button.disabled = self.game.ended or self.game.eaten >= MAX_DOGS
        self.bank_button.disabled = self.game.ended or self.game.eaten == 0

    @discord.ui.button(label="Eat Another Dog 🌭", style=discord.ButtonStyle.danger)
    async def eat_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        g = self.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message("Eat your own dogs.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return

        g.eaten += 1
        hurl_chance = HURL_START + HURL_INCREMENT * (g.eaten - 1)
        dog = random.choice(DOG_NAMES)

        if random.random() < hurl_chance:
            g.ended = True
            hurl = random.choice(HURL_MESSAGES).format(n=g.eaten)
            g.log.append(f"#{g.eaten}: {dog} → {hurl}")
            self._refresh()
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(content=self.cog._render(g, final=True), view=self)
            return

        g.multiplier += MULT_PER_DOG
        g.log.append(f"#{g.eaten}: {dog} — *kept down.* (×{g.multiplier:.2f})")
        if g.eaten >= MAX_DOGS:
            g.ended = True
            payout = int(g.bet * g.multiplier)
            add_coins(g.guild_id, g.user_id, payout)
            g.log.append(f"🏆 **TEN DOG LIMIT REACHED.** You are a national treasure. Auto-bank at ×{g.multiplier:.2f}.")
            self._refresh()
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(content=self.cog._render(g, final=True), view=self)
            return

        self._refresh()
        await interaction.response.edit_message(content=self.cog._render(g), view=self)

    @discord.ui.button(label="Tap Out (1.00×, +0)", style=discord.ButtonStyle.success)
    async def bank_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        g = self.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message("Not your contest.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return
        if g.eaten == 0:
            await interaction.response.send_message("You haven't eaten yet, coward.", ephemeral=True)
            return
        g.ended = True
        payout = int(g.bet * g.multiplier)
        add_coins(g.guild_id, g.user_id, payout)
        g.log.append(f"✅ **Tapped out at ×{g.multiplier:.2f}.** {random.choice(BANK_MESSAGES)}")
        self._refresh()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content=self.cog._render(g, final=True), view=self)


class HotDogContest(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Hot Dog Eating Contest loaded.")

    def _render(self, g: HotDogGame, final: bool = False) -> str:
        next_risk = HURL_START + HURL_INCREMENT * g.eaten
        next_risk = min(next_risk, 0.99)
        lines = [
            f"🌭 **{g.user_name}'s Hot Dog Eating Contest** — buy-in **{g.bet}**",
            f"Dogs eaten: **{g.eaten}/{MAX_DOGS}** | Multiplier: **{g.multiplier:.2f}×**",
        ]
        if not g.ended:
            lines.append(f"Next dog hurl chance: **{next_risk*100:.0f}%**")
        if g.log:
            lines.append("")
            lines.extend(g.log[-6:])
        if final:
            lines.append("")
            lines.append(f"Balance: **{get_coins(g.guild_id, g.user_id)}**")
        return "\n".join(lines)

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
            await reply("Server only.")
            return
        jmsg = jail_message(guild.id, user.id)
        if jmsg:
            await reply(jmsg)
            return
        if bet <= 0:
            await reply("Gotta ante up, skinny.")
            return
        if get_coins(guild.id, user.id) < bet:
            await reply(f"Too broke. Balance: **{get_coins(guild.id, user.id)}**")
            return

        deduct_coins(guild.id, user.id, bet)
        game = HotDogGame(guild.id, user.id, user.display_name, bet)
        view = HotDogView(self, game)
        view._refresh()
        await reply(self._render(game), view=view)

    @commands.command(name="dogs", aliases=["hotdog", "hotdogs"])
    @commands.guild_only()
    async def dogs_prefix(self, ctx, bet: int):
        await self._start(ctx, bet)

    @app_commands.command(name="dogs", description="Hot dog eating contest. Each dog = bigger multiplier, bigger risk.")
    @app_commands.describe(bet="Buy-in coins for the contest")
    async def dogs_slash(self, interaction: discord.Interaction, bet: int):
        await self._start(interaction, bet)


async def setup(bot):
    await bot.add_cog(HotDogContest(bot))
