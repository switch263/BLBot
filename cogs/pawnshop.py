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

MAX_ROUNDS = 3

ITEM_PREFIXES = [
    "Cursed", "Bootleg", "Autographed (forged)", "Slightly Haunted",
    "Mostly Functional", "Suspiciously Mint", "Vaguely Radioactive",
    "Pre-owned by a Clown", "Goodwill-Tier", "Deep-Fried", "Factory Sealed (probably)",
]
ITEM_OBJECTS = [
    "Gamecube", "Claw Machine Plushie", "Signed Hockey Puck", "Bag of Rocks",
    "Taxidermied Possum", "VHS Copy of Shrek 2", "Broken Katana", "Ouija Board",
    "Neon Beer Sign", "Laminated Dolphin Poster", "Rusted Frying Pan",
    "Jar of Teeth", "1987 Tax Return", "Discount Santa Suit",
]

BROKER_OFFERS = [
    "scrutinizes your item through a jeweler's loupe. He whistles low.",
    "chews his toothpick. Stares at the ceiling. Makes a calculation.",
    "shouts into the back room. Shouts again. Gets no response.",
    "punches numbers into a 1990s calculator, squinting.",
    "sniffs it. Licks it. Nods sagely.",
    "puts on reading glasses that are clearly prop glasses.",
    "calls his cousin. The cousin also doesn't know.",
    "consults a pricing guide from 1994.",
]

WALK_AWAY_FLAVOR = [
    "The broker shrugs. 'Suit yourself.' You leave with your item. Which has no resale value anywhere else. Lose it all.",
    "'Don't let the door hit ya.' You walk out into the rain. The item dissolves. Lose everything.",
    "Broker laughs. 'Gonna be a YouTube short.' He was right. Lose everything.",
    "You storm out, item in hand. Fifteen feet later you realize your item was just a brick painted gold. Lose everything.",
]


class PawnGame:
    def __init__(self, guild_id, user_id, user_name, bet, item_name):
        self.guild_id = guild_id
        self.user_id = user_id
        self.user_name = user_name
        self.bet = bet
        self.item_name = item_name
        self.round = 0
        self.current_mult = 0.0
        self.history: list[tuple[int, float]] = []  # (round, multiplier offered)
        self.ended = False


def roll_offer(round_num: int) -> float:
    """Offer distribution widens each round — round 3 can be jackpot OR catastrophic."""
    if round_num == 1:
        return random.choices(
            [0.5, 0.75, 1.0, 1.25, 1.5],
            weights=[10, 25, 30, 25, 10],
        )[0]
    if round_num == 2:
        return random.choices(
            [0.25, 0.75, 1.0, 1.5, 2.0, 3.0],
            weights=[12, 18, 20, 25, 15, 10],
        )[0]
    # round 3
    return random.choices(
        [0.0, 0.5, 1.0, 2.0, 4.0, 8.0],
        weights=[15, 20, 15, 25, 15, 10],
    )[0]


class PawnView(discord.ui.View):
    def __init__(self, cog, game: PawnGame):
        super().__init__(timeout=120)
        self.cog = cog
        self.game = game

    def _refresh(self):
        g = self.game
        payout = int(g.bet * g.current_mult)
        self.accept_button.label = f"Accept ({g.current_mult:.2f}× = {payout})"
        self.hold_button.disabled = g.round >= MAX_ROUNDS
        if g.round >= MAX_ROUNDS:
            self.hold_button.label = "Walk Away (lose it all)"
            self.hold_button.style = discord.ButtonStyle.danger
        else:
            self.hold_button.label = f"Hold Out (Round {g.round + 1}/{MAX_ROUNDS})"

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="🤝")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        g = self.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message("Not your item.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return
        g.ended = True
        payout = int(g.bet * g.current_mult)
        add_coins(g.guild_id, g.user_id, payout)
        for child in self.children:
            child.disabled = True
        net = payout - g.bet
        final = (
            f"🤝 **Deal.** The broker counts out **{payout}** coins.\n"
            f"Net: **{'+' if net >= 0 else ''}{net}**.\n"
            f"Balance: **{get_coins(g.guild_id, g.user_id)}**"
        )
        await interaction.response.edit_message(content=self.cog._render(g, final), view=self)

    @discord.ui.button(label="Hold Out", style=discord.ButtonStyle.primary, emoji="⏳")
    async def hold_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        g = self.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message("Not your item.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return
        if g.round >= MAX_ROUNDS:
            # Walk away from final offer
            g.ended = True
            for child in self.children:
                child.disabled = True
            walkaway = random.choice(WALK_AWAY_FLAVOR)
            final = f"🚪 {walkaway}\nBalance: **{get_coins(g.guild_id, g.user_id)}**"
            await interaction.response.edit_message(content=self.cog._render(g, final), view=self)
            return

        g.round += 1
        g.current_mult = roll_offer(g.round)
        g.history.append((g.round, g.current_mult))
        self._refresh()
        await interaction.response.edit_message(content=self.cog._render(g), view=self)


class PawnShop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Pawn Shop loaded.")

    def _render(self, g: PawnGame, footer: str | None = None) -> str:
        lines = [
            f"🏪 **The Pawn Shop** — {g.user_name} brought in **a {g.item_name}** (cost basis: **{g.bet}** coins).",
        ]
        for rnd, mult in g.history:
            flavor = random.choice(BROKER_OFFERS) if rnd == g.round else ""
            if rnd == g.round and not g.ended:
                lines.append(f"**Round {rnd}:** The broker {flavor}")
                lines.append(f"➡️ Offer: **{mult:.2f}×** ({int(g.bet * mult)} coins)")
            else:
                lines.append(f"Round {rnd} offer: **{mult:.2f}×** (passed)")
        if not g.history:
            lines.append("*Click **Hold Out** to hear the first offer, or **Accept** to just take whatever.*")
            lines.append("Round 1 offers: 0.5×–1.5×. Round 2 gets wilder. Round 3 is a coinflip between bonanza and ruin.")
        if footer:
            lines.append("")
            lines.append(footer)
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
            await reply("You gotta bring an item of some value.")
            return
        if get_coins(guild.id, user.id) < bet:
            await reply(f"Too broke. Balance: **{get_coins(guild.id, user.id)}**")
            return

        deduct_coins(guild.id, user.id, bet)
        item_name = f"{random.choice(ITEM_PREFIXES)} {random.choice(ITEM_OBJECTS)}"
        game = PawnGame(guild.id, user.id, user.display_name, bet, item_name)
        # Prime round 1 on display
        game.round = 1
        game.current_mult = roll_offer(1)
        game.history.append((1, game.current_mult))
        view = PawnView(self, game)
        view._refresh()
        await reply(self._render(game), view=view)

    @commands.command(name="pawn", aliases=["pawnshop"])
    @commands.guild_only()
    async def pawn_prefix(self, ctx, bet: int):
        await self._start(ctx, bet)

    @app_commands.command(name="pawn", description="Hawk a cursed item at the pawn shop. Accept an offer or hold out for better (or worse).")
    @app_commands.describe(bet="Value of the item you're pawning")
    async def pawn_slash(self, interaction: discord.Interaction, bet: int):
        await self._start(interaction, bet)


async def setup(bot):
    await bot.add_cog(PawnShop(bot))
