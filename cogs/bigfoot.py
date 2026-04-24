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

# 4x4 grid of forest hexes
GRID_ROWS = 4
GRID_COLS = 4
GRID_SIZE = GRID_ROWS * GRID_COLS  # 16

# Tile composition per game:
NUM_BEARS = 3       # bust tiles
NUM_BIGFOOT = 1     # jackpot tile — auto-wins on reveal
# remaining 12 are footprint tiles that bump the multiplier
SAFE_BUMP = 0.25    # +25% of bet per footprint
BIGFOOT_MULT = 10.0 # whole-bet multiplier when photographed

BEAR_NARRATIVES = [
    "A black bear emerges from the bushes looking personally wronged by you.",
    "You startle a grizzly doing its taxes. It is not pleased.",
    "A mother bear thinks you're threatening her cubs. You are not. It doesn't matter.",
    "A bear in a hat. That's all. That's the whole sentence. You're done.",
    "You tripped over a bear that was napping. Rookie mistake.",
    "The bear was the cryptid all along. It gets you.",
    "A bear wearing your uncle's hat rips your film out.",
]

BIGFOOT_NARRATIVES = [
    "You lock eyes with a 9-foot sasquatch. You raise the camera. He poses. National Geographic calls.",
    "Bigfoot steps out of the trees, nods respectfully, and vanishes. You got the shot.",
    "The beast is real. You have the photo. You are rich.",
    "Bigfoot sees you, sighs, and offers to split your royalties 60/40. You'd be a fool to refuse.",
    "A clear, in-focus, unambiguous photograph. Cryptozoologists are going to lose their minds.",
]

FOOTPRINT_FLAVOR = [
    "A fresh print. You're close.",
    "Another print. Bigger than the last.",
    "You smell something. Wet fur? Old bologna?",
    "Branches snap somewhere. You ignore it.",
    "A tuft of hair. Definitely not human.",
    "A half-eaten slim jim. Big guy was here.",
    "Giant prints leading to a 7-Eleven? Weird.",
    "You hear distant footsteps. You press on.",
]

CASHOUT_FLAVOR = [
    "You jog back to the ranger station with your findings.",
    "You decide this is enough for tonight.",
    "Your back is killing you. Time to cash in.",
    "A raccoon whispers that you should bank. You listen.",
    "You exit the woods before something exits with you.",
]


class Expedition:
    def __init__(self, guild_id: int, user_id: int, user_name: str, bet: int):
        self.guild_id = guild_id
        self.user_id = user_id
        self.user_name = user_name
        self.bet = bet
        # Randomly place bears and 1 bigfoot
        slots = list(range(GRID_SIZE))
        random.shuffle(slots)
        self.bears = set(slots[:NUM_BEARS])
        self.bigfoot = slots[NUM_BEARS]
        # everything else is safe
        self.revealed: set[int] = set()
        self.footprints_found = 0
        self.ended = False


def current_multiplier(footprints: int) -> float:
    return 1.0 + SAFE_BUMP * footprints


class HexButton(discord.ui.Button):
    def __init__(self, idx: int, row: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="🌲", row=row)
        self.idx = idx

    async def callback(self, interaction: discord.Interaction):
        view: "ExpeditionView" = self.view  # type: ignore
        g = view.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message("Find your own forest.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return

        g.revealed.add(self.idx)
        self.disabled = True

        if self.idx in g.bears:
            g.ended = True
            self.label = "🐻"
            self.style = discord.ButtonStyle.danger
            for child in view.children:
                if isinstance(child, HexButton):
                    if child.idx in g.bears:
                        child.label = "🐻"
                        child.style = discord.ButtonStyle.danger
                    elif child.idx == g.bigfoot:
                        child.label = "🦍"
                child.disabled = True
            narrative = random.choice(BEAR_NARRATIVES)
            content = view.cog._render(g, f"🐻 **MAULED!** {narrative}\nYou lose **{g.bet}** coins.")
            await interaction.response.edit_message(content=content, view=view)
            return

        if self.idx == g.bigfoot:
            g.ended = True
            self.label = "🦍"
            self.style = discord.ButtonStyle.success
            # Base multiplier from footprints PLUS Bigfoot jackpot
            base_mult = current_multiplier(g.footprints_found)
            final_mult = base_mult * BIGFOOT_MULT
            payout = int(g.bet * final_mult)
            add_coins(g.guild_id, g.user_id, payout)
            for child in view.children:
                if isinstance(child, HexButton):
                    if child.idx in g.bears:
                        child.label = "🐻"
                        child.style = discord.ButtonStyle.danger
                child.disabled = True
            net = payout - g.bet
            narrative = random.choice(BIGFOOT_NARRATIVES)
            content = view.cog._render(
                g,
                f"🦍 **BIGFOOT PHOTOGRAPHED!** {narrative}\n"
                f"Final multiplier: **{final_mult:.2f}×** ({base_mult:.2f}× prints × {BIGFOOT_MULT:.0f}× jackpot). Net **+{net}** coins.",
            )
            await interaction.response.edit_message(content=content, view=view)
            return

        # Footprint (safe)
        g.footprints_found += 1
        self.label = "🦶"
        self.style = discord.ButtonStyle.success
        view._refresh_cashout()
        await interaction.response.edit_message(content=view.cog._render(g), view=view)


class CashOutButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Head Back (1.00×)", emoji="📷", row=GRID_ROWS)

    async def callback(self, interaction: discord.Interaction):
        view: "ExpeditionView" = self.view  # type: ignore
        g = view.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message("Not your expedition.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return
        if g.footprints_found == 0:
            await interaction.response.send_message("You haven't even left the parking lot yet.", ephemeral=True)
            return
        g.ended = True
        mult = current_multiplier(g.footprints_found)
        payout = int(g.bet * mult)
        add_coins(g.guild_id, g.user_id, payout)
        for child in view.children:
            if isinstance(child, HexButton):
                if child.idx in g.bears:
                    child.label = "🐻"
                    child.style = discord.ButtonStyle.danger
                elif child.idx == g.bigfoot:
                    child.label = "🦍"
            child.disabled = True
        net = payout - g.bet
        narrative = random.choice(CASHOUT_FLAVOR)
        content = view.cog._render(
            g,
            f"📷 **Headed back with {g.footprints_found} footprints.** {narrative}\n"
            f"Multiplier **{mult:.2f}×** → net **+{net}** coins.",
        )
        await interaction.response.edit_message(content=content, view=view)


class ExpeditionView(discord.ui.View):
    def __init__(self, cog, game: Expedition):
        super().__init__(timeout=300)
        self.cog = cog
        self.game = game
        for i in range(GRID_SIZE):
            self.add_item(HexButton(i, row=i // GRID_COLS))
        self.cashout = CashOutButton()
        self.add_item(self.cashout)

    def _refresh_cashout(self):
        mult = current_multiplier(self.game.footprints_found)
        payout = int(self.game.bet * mult)
        net = payout - self.game.bet
        self.cashout.label = f"Head Back ({mult:.2f}×, +{net})"

    async def on_timeout(self):
        if not self.game.ended:
            g = self.game
            if g.footprints_found > 0:
                mult = current_multiplier(g.footprints_found)
                add_coins(g.guild_id, g.user_id, int(g.bet * mult))
            g.ended = True


class BigfootExpedition(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Bigfoot Expedition loaded.")

    def _render(self, g: Expedition, footer: str | None = None) -> str:
        mult = current_multiplier(g.footprints_found)
        lines = [
            f"🌲 **{g.user_name}'s Bigfoot Expedition** — bet **{g.bet}** coins",
            f"Somewhere in these **{GRID_SIZE}** hexes: **{NUM_BEARS} bears** and **1 Bigfoot** (jackpot ×{BIGFOOT_MULT:.0f}).",
            f"Prints found: **{g.footprints_found}** | Multiplier: **{mult:.2f}×**",
        ]
        if not g.ended:
            lines.append(f"Each print bumps the multiplier. Find Bigfoot and the multiplier is ×{BIGFOOT_MULT:.0f}.")
        if footer:
            lines.append("")
            lines.append(footer)
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
            await reply("Can only hunt cryptids in a server.")
            return
        jmsg = jail_message(guild.id, user.id)
        if jmsg:
            await reply(jmsg)
            return
        if bet <= 0:
            await reply("You gotta risk something, coward.")
            return
        if get_coins(guild.id, user.id) < bet:
            await reply(f"Too broke for an expedition. Balance: **{get_coins(guild.id, user.id)}**")
            return

        deduct_coins(guild.id, user.id, bet)
        game = Expedition(guild.id, user.id, user.display_name, bet)
        view = ExpeditionView(self, game)
        await reply(self._render(game), view=view)

    @commands.command(name="bigfoot", aliases=["cryptid", "expedition"])
    @commands.guild_only()
    async def bigfoot_prefix(self, ctx, bet: int):
        await self._start(ctx, bet)

    @app_commands.command(name="bigfoot", description="Hunt Bigfoot. Avoid bears. Photograph the myth.")
    @app_commands.describe(bet="Coins to risk on your expedition")
    async def bigfoot_slash(self, interaction: discord.Interaction, bet: int):
        await self._start(interaction, bet)


async def setup(bot):
    await bot.add_cog(BigfootExpedition(bot))
