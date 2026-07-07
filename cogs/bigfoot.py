import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

from economy import get_coins, casino_payout, record_game
from game_common import casino_prelude
from gridgame import GridView

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
# Walking straight up to Bigfoot on your very first hex (1-in-16 per game)
# skips the print math entirely and pays this flat.
FIRST_SHOT_MULT = 100.0

BEAR_NARRATIVES = [
    "A black bear emerges from the bushes looking personally wronged by you.",
    "You startle a grizzly doing its taxes. It is not pleased.",
    "A mother bear thinks you're threatening her cubs. You are not. It doesn't matter.",
    "A bear in a hat. That's all. That's the whole sentence. You're done.",
    "You tripped over a bear that was napping. Rookie mistake.",
    "The bear was the cryptid all along. It gets you.",
    "A bear wearing your uncle's hat rips your film out.",
]

FIRST_SHOT_NARRATIVES = [
    "You step off the trail and he's RIGHT THERE, mid-yawn. One frame. Perfect focus. History.",
    "No tracking, no prints, no patience — you simply walk into the clearing and Bigfoot is waiting like he had an appointment.",
    "First hex. First step. There he is, backlit by the moon like he was posing for the cover. The shot of the century.",
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


def current_multiplier(footprints: int) -> float:
    return 1.0 + SAFE_BUMP * footprints


class ExpeditionView(GridView):
    HIDDEN_LABEL = "🌲"

    def __init__(self, cog, guild_id: int, user_id: int, user_name: str, bet: int):
        super().__init__(user_id, rows=GRID_ROWS, cols=GRID_COLS, timeout=300,
                         not_yours="Find your own forest.")
        self.cog = cog
        self.guild_id = guild_id
        self.user_name = user_name
        self.bet = bet
        # Randomly place bears and 1 bigfoot
        slots = list(range(GRID_SIZE))
        random.shuffle(slots)
        self.bears = set(slots[:NUM_BEARS])
        self.bigfoot = slots[NUM_BEARS]
        self.revealed: set[int] = set()
        self.footprints_found = 0
        self.action_btn.label = "Head Back (1.00×)"
        self.action_btn.emoji = "📷"

    # ---- GridView hooks ---------------------------------------------------
    def tile_face(self, idx: int):
        if idx in self.bears:
            return "🐻", discord.ButtonStyle.danger
        if idx == self.bigfoot:
            return "🦍", (discord.ButtonStyle.success if idx in self.revealed
                          else discord.ButtonStyle.secondary)
        if idx in self.revealed:
            return "🦶", discord.ButtonStyle.success
        return None

    async def on_tile(self, interaction: discord.Interaction, idx: int):
        self.revealed.add(idx)
        self.tile_btns[idx].disabled = True

        if idx in self.bears:
            record_game(self.guild_id, self.user_id, "bigfoot", won=False)
            self.finish()
            narrative = random.choice(BEAR_NARRATIVES)
            content = self.cog._render(
                self, f"🐻 **MAULED!** {narrative}\nYou lose **{self.bet:,}** coins.")
            await interaction.response.edit_message(content=content, view=self)
            return

        if idx == self.bigfoot:
            first_shot = len(self.revealed) == 1
            if first_shot:
                # Bigfoot on the very first hex: flat FIRST_SHOT_MULT jackpot.
                final_mult = FIRST_SHOT_MULT
                headline = "📸 **FIRST SHOT!** " + random.choice(FIRST_SHOT_NARRATIVES)
                breakdown = f"Final multiplier: **{final_mult:.0f}×** — first-hex jackpot, no prints needed."
            else:
                base_mult = current_multiplier(self.footprints_found)
                final_mult = base_mult * BIGFOOT_MULT
                headline = f"🦍 **BIGFOOT PHOTOGRAPHED!** {random.choice(BIGFOOT_NARRATIVES)}"
                breakdown = (f"Final multiplier: **{final_mult:.2f}×** "
                             f"({base_mult:.2f}× prints × {BIGFOOT_MULT:.0f}× jackpot).")
            requested = int(self.bet * final_mult)
            paid = casino_payout(self.guild_id, self.user_id, requested)
            record_game(self.guild_id, self.user_id, "bigfoot", won=True)
            self.finish()
            net = paid - self.bet
            short = f" *(house was short — owed {requested:,})*" if paid < requested else ""
            content = self.cog._render(
                self, f"{headline}\n{breakdown} Net **{net:+,}** coins.{short}")
            await interaction.response.edit_message(content=content, view=self)
            return

        # Footprint (safe)
        self.footprints_found += 1
        self.tile_btns[idx].label = "🦶"
        self.tile_btns[idx].style = discord.ButtonStyle.success
        self._refresh_cashout()
        await interaction.response.edit_message(content=self.cog._render(self), view=self)

    async def on_action(self, interaction: discord.Interaction):
        if self.footprints_found == 0:
            await interaction.response.send_message(
                "You haven't even left the parking lot yet.", ephemeral=True)
            return
        mult = current_multiplier(self.footprints_found)
        requested = int(self.bet * mult)
        paid = casino_payout(self.guild_id, self.user_id, requested)
        record_game(self.guild_id, self.user_id, "bigfoot", won=True)
        self.finish()
        net = paid - self.bet
        short = f" *(house was short — owed {requested:,})*" if paid < requested else ""
        narrative = random.choice(CASHOUT_FLAVOR)
        content = self.cog._render(
            self,
            f"📷 **Headed back with {self.footprints_found} footprints.** {narrative}\n"
            f"Multiplier **{mult:.2f}×** → net **{net:+,}** coins.{short}",
        )
        await interaction.response.edit_message(content=content, view=self)

    async def on_abandon(self):
        # Walked away mid-expedition: bank whatever prints they found.
        if self.footprints_found > 0:
            mult = current_multiplier(self.footprints_found)
            casino_payout(self.guild_id, self.user_id, int(self.bet * mult))
            record_game(self.guild_id, self.user_id, "bigfoot", won=True)
        else:
            record_game(self.guild_id, self.user_id, "bigfoot", won=False)

    def _refresh_cashout(self):
        mult = current_multiplier(self.footprints_found)
        net = int(self.bet * mult) - self.bet
        self.action_btn.label = f"Head Back ({mult:.2f}×, +{net})"


class BigfootExpedition(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Bigfoot Expedition loaded.")

    def _render(self, v: ExpeditionView, footer: str | None = None) -> str:
        mult = current_multiplier(v.footprints_found)
        lines = [
            f"🌲 **{v.user_name}'s Bigfoot Expedition** — bet **{v.bet:,}** coins",
            f"Somewhere in these **{GRID_SIZE}** hexes: **{NUM_BEARS} bears** and **1 Bigfoot** (jackpot ×{BIGFOOT_MULT:.0f}).",
            f"Prints found: **{v.footprints_found}** | Multiplier: **{mult:.2f}×**",
        ]
        if not v.resolved:
            lines.append(
                f"Each print bumps the multiplier. Find Bigfoot and the multiplier is ×{BIGFOOT_MULT:.0f} — "
                f"or a flat **×{FIRST_SHOT_MULT:.0f}** if he's your very first hex."
            )
        if footer:
            lines.append("")
            lines.append(footer)
            lines.append(f"Balance: **{get_coins(v.guild_id, v.user_id):,}**")
        return "\n".join(lines)

    async def _start(self, ctx_or_interaction, bet):
        start = await casino_prelude(
            ctx_or_interaction, bet,
            zero_msg="You gotta risk something, coward.",
            no_guild_msg="Can only hunt cryptids in a server.",
        )
        if start is None:
            return
        view = ExpeditionView(self, start.guild.id, start.user.id,
                              start.user.display_name, start.bet)
        view.message = await start.reply(self._render(view), view=view)

    @commands.command(name="bigfoot", aliases=["cryptid", "expedition"])
    @commands.guild_only()
    async def bigfoot_prefix(self, ctx, bet: str):
        await self._start(ctx, bet)

    @app_commands.command(name="bigfoot", description="Hunt Bigfoot. Avoid bears. Photograph the myth.")
    @app_commands.describe(bet="Coins to risk on your expedition — supports 1k, 5m, 100,000")
    async def bigfoot_slash(self, interaction: discord.Interaction, bet: str):
        await self._start(interaction, bet)


async def setup(bot):
    await bot.add_cog(BigfootExpedition(bot))
