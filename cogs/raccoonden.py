import discord
from discord.ext import commands
from discord import app_commands
import random
import sys
import os
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from economy import get_coins, add_coins, deduct_coins

logger = logging.getLogger(__name__)

GRID_ROWS = 4
GRID_COLS = 4
GRID_SIZE = GRID_ROWS * GRID_COLS
NUM_RACCOONS = 3
HOUSE_EDGE = 0.97

RACCOON_SCREAMS = [
    "A feral raccoon launches at your face.",
    "Three raccoons in a trench coat. You owe them rent now.",
    "A rabid raccoon screeches in a register only dogs can hear. You flee.",
    "The raccoon was wearing your grandma's earrings. You did NOT ask questions.",
    "A raccoon with a switchblade. Classic Tuesday.",
    "The raccoon was on the phone. You're pretty sure it was ordering a hit.",
    "Raccoon. Syringe. Flagrant eye contact.",
]

WIN_FLAVOR = [
    "You waddle out with a grocery bag of wet cash.",
    "You smelled like garbage juice for a week, but it was worth it.",
    "A crow watched you the whole time. Respect the bird.",
    "You sold your findings to a pawn shop run by a ferret. Don't ask.",
    "Your mom will never know.",
]


def current_multiplier(revealed_safe: int) -> float:
    if revealed_safe <= 0:
        return 1.0
    p_survive = 1.0
    for i in range(revealed_safe):
        p_survive *= (GRID_SIZE - NUM_RACCOONS - i) / (GRID_SIZE - i)
    return HOUSE_EDGE / p_survive


class DenGame:
    def __init__(self, guild_id: int, user_id: int, user_name: str, bet: int):
        self.guild_id = guild_id
        self.user_id = user_id
        self.user_name = user_name
        self.bet = bet
        self.raccoons: set[int] = set(random.sample(range(GRID_SIZE), NUM_RACCOONS))
        self.revealed: set[int] = set()
        self.ended = False
        self.won = False


class BinButton(discord.ui.Button):
    def __init__(self, idx: int, row: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="🗑️", row=row)
        self.idx = idx

    async def callback(self, interaction: discord.Interaction):
        view: "DenView" = self.view  # type: ignore
        g = view.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message("Find your own dumpster.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return

        g.revealed.add(self.idx)
        self.disabled = True

        if self.idx in g.raccoons:
            g.ended = True
            self.label = "🦝"
            self.style = discord.ButtonStyle.danger
            for child in view.children:
                if isinstance(child, BinButton) and child.idx in g.raccoons:
                    child.label = "🦝"
                    child.style = discord.ButtonStyle.danger
                child.disabled = True
            scream = random.choice(RACCOON_SCREAMS)
            content = view.cog._render(g, f"🦝 **BITTEN!** {scream}\nYou lose **{g.bet}** coins.")
            await interaction.response.edit_message(content=content, view=view)
            return

        self.label = "💎"
        self.style = discord.ButtonStyle.success
        view._refresh_cashout()
        if len(g.revealed) == GRID_SIZE - NUM_RACCOONS:
            # Cleared the board — max payout, auto cashout
            g.ended = True
            g.won = True
            mult = current_multiplier(len(g.revealed))
            payout = int(g.bet * mult)
            add_coins(g.guild_id, g.user_id, payout)
            for child in view.children:
                if isinstance(child, BinButton) and child.idx in g.raccoons:
                    child.label = "🦝"
                    child.style = discord.ButtonStyle.danger
                child.disabled = True
            net = payout - g.bet
            flavor = random.choice(WIN_FLAVOR)
            content = view.cog._render(
                g,
                f"🏆 **PERFECT RUN at {mult:.2f}×!** You cleaned out the den.\n"
                f"Net **+{net}** coins. _{flavor}_",
            )
            await interaction.response.edit_message(content=content, view=view)
            return

        await interaction.response.edit_message(content=view.cog._render(g), view=view)


class CashOutButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Climb Out (1.00×)", emoji="💰", row=GRID_ROWS)

    async def callback(self, interaction: discord.Interaction):
        view: "DenView" = self.view  # type: ignore
        g = view.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message("Not your den.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return
        if not g.revealed:
            await interaction.response.send_message("You haven't touched a single bin yet, coward.", ephemeral=True)
            return
        g.ended = True
        g.won = True
        mult = current_multiplier(len(g.revealed))
        payout = int(g.bet * mult)
        add_coins(g.guild_id, g.user_id, payout)
        for child in view.children:
            if isinstance(child, BinButton) and child.idx in g.raccoons:
                child.label = "🦝"
                child.style = discord.ButtonStyle.danger
            child.disabled = True
        net = payout - g.bet
        flavor = random.choice(WIN_FLAVOR)
        content = view.cog._render(
            g,
            f"💰 **Climbed out at {mult:.2f}×.** Net **+{net}** coins. _{flavor}_",
        )
        await interaction.response.edit_message(content=content, view=view)


class DenView(discord.ui.View):
    def __init__(self, cog, game: DenGame):
        super().__init__(timeout=300)
        self.cog = cog
        self.game = game
        for i in range(GRID_SIZE):
            self.add_item(BinButton(i, row=i // GRID_COLS))
        self.cashout = CashOutButton()
        self.add_item(self.cashout)

    def _refresh_cashout(self):
        mult = current_multiplier(len(self.game.revealed))
        payout = int(self.game.bet * mult)
        net = payout - self.game.bet
        self.cashout.label = f"Climb Out ({mult:.2f}×, +{net})"

    async def on_timeout(self):
        if not self.game.ended:
            # Cashout for the user at whatever they've got
            g = self.game
            if g.revealed:
                mult = current_multiplier(len(g.revealed))
                add_coins(g.guild_id, g.user_id, int(g.bet * mult))
            g.ended = True


class RaccoonDen(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Raccoon's Den loaded.")

    def _render(self, g: DenGame, footer: str | None = None) -> str:
        mult = current_multiplier(len(g.revealed))
        safe_possible = GRID_SIZE - NUM_RACCOONS
        lines = [
            f"🦝 **{g.user_name}'s Raccoon Den** — bet **{g.bet}** coins",
            f"{NUM_RACCOONS} feral raccoons hide in {GRID_SIZE} bins. "
            f"Revealed: **{len(g.revealed)}/{safe_possible}** | Multiplier: **{mult:.2f}×**",
        ]
        if not g.ended:
            lines.append(f"Click bins to dig. Climb Out any time to bank **{int(g.bet * mult)}** coins.")
        if footer:
            lines.append("")
            lines.append(footer)
            lines.append(f"Balance: **{get_coins(g.guild_id, g.user_id)}**")
        return "\n".join(lines)

    async def _start_game(self, ctx_or_interaction, bet: int):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild
        user = ctx_or_interaction.user if is_slash else ctx_or_interaction.author

        async def reply(content, **kwargs):
            if is_slash:
                await ctx_or_interaction.response.send_message(content, **kwargs)
                return await ctx_or_interaction.original_response()
            return await ctx_or_interaction.send(content, **kwargs)

        if not guild:
            await reply("Can only dig in a server.")
            return
        if bet <= 0:
            await reply("You gotta risk something, cheapskate.")
            return
        balance = get_coins(guild.id, user.id)
        if balance < bet:
            await reply(f"Too broke. Balance: **{balance}**")
            return

        deduct_coins(guild.id, user.id, bet)
        game = DenGame(guild.id, user.id, user.display_name, bet)
        view = DenView(self, game)
        await reply(self._render(game), view=view)

    @commands.command(name="dig", aliases=["den", "raccoon"])
    @commands.guild_only()
    async def dig_prefix(self, ctx, bet: int):
        await self._start_game(ctx, bet)

    @app_commands.command(name="dig", description="Dig through a raccoon den — avoid the raccoons, grab the loot.")
    @app_commands.describe(bet="Coins to risk on the dig")
    async def dig_slash(self, interaction: discord.Interaction, bet: int):
        await self._start_game(interaction, bet)


async def setup(bot):
    await bot.add_cog(RaccoonDen(bot))
