import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

from economy import get_coins, record_game, casino_payout, transfer_to_house
from game_common import casino_prelude
from gridgame import GridView

logger = logging.getLogger(__name__)

GRID_ROWS = 4
GRID_COLS = 4
GRID_SIZE = GRID_ROWS * GRID_COLS
DEFAULT_RACCOONS = 3
MIN_RACCOONS = 1
MAX_RACCOONS = 12   # always leaves at least 4 safe bins to dig
HOUSE_EDGE = 0.97
BONUS_CHANCE = 0.25
# The multiplier is probability-fair (HOUSE_EDGE / P(survival)), so more
# raccoons = steeper payouts automatically, same edge at every difficulty.
# The cap bounds the tail: a deep full clear can otherwise reach five
# figures of multiplier (16-choose-8 = 12,870), and one fair-odds hit for
# a third of the house pot is exactly the kind of rare mega-drain we cap
# everywhere else (see HOUSE_HEIST_MAX_PCT / MINES_MAX_MULT).
DEN_MAX_MULT = 1000.0

# Weighted pool of bonuses. When the bonus tile is dug, one of these resolves.
# Effects: "mult" multiplies cashout; "kick" removes N raccoons (turns those
# tiles into safe revealed tiles).
BONUS_TYPES = [
    {
        "key": "double",
        "weight": 30,
        "label": "✨",
        "effect": "mult",
        "value": 2.0,
        "flavor": "✨ A tinfoil ball wrapped around something REAL. Multiplier **doubled**!",
    },
    {
        "key": "mega",
        "weight": 8,
        "label": "💎",
        "effect": "mult",
        "value": 10.0,
        "flavor": "💎 You unearthed the Holy Grail of trash. Multiplier **×10**!",
    },
    {
        "key": "exodus",
        "weight": 7,
        "label": "🚨",
        "effect": "kick",
        "value": "all",
        "flavor": "🚨 The trash truck rolls in. **Every raccoon flees the den.**",
    },
    {
        "key": "plague",
        "weight": 25,
        "label": "🤒",
        "effect": "kick",
        "value": 2,
        "flavor": "🤒 The raccoons caught the trash flu. **Two collapse** harmlessly.",
    },
    {
        "key": "kangaroo",
        "weight": 30,
        "label": "🦘",
        "effect": "kick",
        "value": 1,
        "flavor": "🦘 SURPRISE — it's a kangaroo. It **bodyslams a raccoon** and bounces off.",
    },
]

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


def current_multiplier(revealed_safe: int, num_raccoons: int) -> float:
    # Cap so kick-bonuses (which mark raccoon tiles as revealed) can't push
    # past the safe-tile count and divide by zero.
    revealed_safe = min(revealed_safe, GRID_SIZE - num_raccoons)
    if revealed_safe <= 0:
        return 1.0
    p_survive = 1.0
    for i in range(revealed_safe):
        p_survive *= (GRID_SIZE - num_raccoons - i) / (GRID_SIZE - i)
    return min(HOUSE_EDGE / p_survive, DEN_MAX_MULT)


def pick_bonus_type() -> dict:
    return random.choices(BONUS_TYPES, weights=[b["weight"] for b in BONUS_TYPES])[0]


class DenView(GridView):
    HIDDEN_LABEL = "🗑️"

    def __init__(self, cog, guild_id: int, user_id: int, user_name: str, bet: int,
                 num_raccoons: int = DEFAULT_RACCOONS):
        super().__init__(user_id, rows=GRID_ROWS, cols=GRID_COLS, timeout=300,
                         not_yours="Find your own dumpster.")
        self.cog = cog
        self.guild_id = guild_id
        self.user_name = user_name
        self.bet = bet
        self.num_raccoons = num_raccoons
        self.raccoons: set[int] = set(random.sample(range(GRID_SIZE), num_raccoons))
        self.revealed: set[int] = set()
        self.won = False
        self.bonus_tile: int | None = None
        self.bonus_type: dict | None = None
        self.bonus_multiplier: float = 1.0
        if random.random() < BONUS_CHANCE:
            safe_tiles = [i for i in range(GRID_SIZE) if i not in self.raccoons]
            self.bonus_tile = random.choice(safe_tiles)
            self.bonus_type = pick_bonus_type()
        self.action_btn.label = "Climb Out (1.00×)"
        self.action_btn.emoji = "💰"

    @property
    def bonus_triggered(self) -> bool:
        return self.bonus_tile is not None and self.bonus_tile in self.revealed

    def get_multiplier(self) -> float:
        base = current_multiplier(len(self.revealed), self.num_raccoons)
        return min(base * self.bonus_multiplier, DEN_MAX_MULT)

    # ---- GridView hooks ---------------------------------------------------
    def tile_face(self, idx: int):
        if idx in self.raccoons:
            return "🦝", discord.ButtonStyle.danger
        return None  # dug bins already show their face; unclicked bins stay shut

    async def on_tile(self, interaction: discord.Interaction, idx: int):
        self.revealed.add(idx)
        btn = self.tile_btns[idx]
        btn.disabled = True

        if idx in self.raccoons:
            record_game(self.guild_id, self.user_id, "den", won=False)
            btn.label = "🦝"
            btn.style = discord.ButtonStyle.danger
            self.finish()
            scream = random.choice(RACCOON_SCREAMS)
            content = self.cog._render(
                self, f"🦝 **BITTEN!** {scream}\nYou lose **{self.bet:,}** coins.")
            await interaction.response.edit_message(content=content, view=self)
            return

        bonus_msg = None
        if idx == self.bonus_tile and self.bonus_type:
            bt = self.bonus_type
            btn.label = bt["label"]
            btn.style = discord.ButtonStyle.success
            bonus_msg = bt["flavor"]
            self._apply_bonus_effect()
        else:
            btn.label = "💎"
            btn.style = discord.ButtonStyle.success
        self._refresh_cashout()

        if len(self.revealed) >= GRID_SIZE - self.num_raccoons:
            # Cleared the board — max payout, auto cashout
            await self._cash_out(interaction, perfect=True)
            return

        await interaction.response.edit_message(content=self.cog._render(self, bonus_msg), view=self)

    async def on_action(self, interaction: discord.Interaction):
        if not self.revealed:
            await interaction.response.send_message(
                "You haven't touched a single bin yet, coward.", ephemeral=True)
            return
        await self._cash_out(interaction, perfect=False)

    async def _cash_out(self, interaction: discord.Interaction, perfect: bool):
        self.won = True
        mult = self.get_multiplier()
        requested = int(self.bet * mult)
        paid = casino_payout(self.guild_id, self.user_id, requested)
        record_game(self.guild_id, self.user_id, "den", won=True)
        self.finish()
        net = paid - self.bet
        short = f" *(house was short — owed {requested:,})*" if paid < requested else ""
        flavor = random.choice(WIN_FLAVOR)
        if perfect:
            lead = f"🏆 **PERFECT RUN at {mult:.2f}×!** You cleaned out the den.\n"
        else:
            lead = f"💰 **Climbed out at {mult:.2f}×.** "
        content = self.cog._render(self, f"{lead}Net **{net:+,}** coins.{short} _{flavor}_")
        await interaction.response.edit_message(content=content, view=self)

    async def on_abandon(self):
        # Cashout for the user at whatever they've got
        if self.revealed:
            casino_payout(self.guild_id, self.user_id, int(self.bet * self.get_multiplier()))
            record_game(self.guild_id, self.user_id, "den", won=True)
        else:
            record_game(self.guild_id, self.user_id, "den", won=False)

    # ---- bonuses ------------------------------------------------------------
    def _refresh_cashout(self):
        mult = self.get_multiplier()
        net = int(self.bet * mult) - self.bet
        self.action_btn.label = f"Climb Out ({mult:.2f}×, +{net:,})"

    def _apply_bonus_effect(self):
        bt = self.bonus_type
        if not bt:
            return
        if bt["effect"] == "mult":
            self.bonus_multiplier = bt["value"]
        elif bt["effect"] == "kick":
            kick = len(self.raccoons) if bt["value"] == "all" else bt["value"]
            for victim in random.sample(list(self.raccoons), min(kick, len(self.raccoons))):
                self._kick_out_raccoon(victim, bt["label"])

    def _kick_out_raccoon(self, idx: int, label: str):
        self.raccoons.discard(idx)
        self.revealed.add(idx)
        btn = self.tile_btns[idx]
        btn.label = label
        btn.style = discord.ButtonStyle.success
        btn.disabled = True


class RaccoonDen(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Raccoon's Den loaded.")

    def _render(self, v: DenView, footer: str | None = None) -> str:
        mult = v.get_multiplier()
        safe_possible = GRID_SIZE - v.num_raccoons
        mult_label = f"**{mult:.2f}×**"
        if v.bonus_triggered and v.bonus_type:
            mult_label += f" {v.bonus_type['label']}"
        lines = [
            f"🦝 **{v.user_name}'s Raccoon Den** — bet **{v.bet:,}** coins",
            f"**{v.num_raccoons}** feral raccoons hide in {GRID_SIZE} bins. "
            f"Revealed: **{len(v.revealed)}/{safe_possible}** | Multiplier: {mult_label}",
        ]
        if not v.resolved:
            lines.append(f"Click bins to dig. Climb Out any time to bank **{int(v.bet * mult):,}** coins.")
        if footer:
            lines.append("")
            lines.append(footer)
            lines.append(f"Balance: **{get_coins(v.guild_id, v.user_id):,}**")
        return "\n".join(lines)

    async def _start_game(self, ctx_or_interaction, bet, raccoons: int = DEFAULT_RACCOONS):
        # collect=False: the bet is parsed and validated but not taken, so the
        # raccoon-count check below can still bail without needing a refund.
        start = await casino_prelude(
            ctx_or_interaction, bet, collect=False,
            zero_msg="You gotta risk something, cheapskate.",
            no_guild_msg="Can only dig in a server.",
        )
        if start is None:
            return
        if not (MIN_RACCOONS <= raccoons <= MAX_RACCOONS):
            await start.reply(f"Pick **{MIN_RACCOONS}–{MAX_RACCOONS}** raccoons. "
                              f"More raccoons, steeper multipliers.", ephemeral=True)
            return
        res = transfer_to_house(start.guild.id, start.user.id, start.bet)
        if not res.get("ok"):
            if res.get("error") == "broke":
                await start.reply(f"Too broke. Balance: **{res.get('have', 0):,}**", ephemeral=True)
            else:
                await start.reply("Bet failed. Try again.", ephemeral=True)
            return
        view = DenView(self, start.guild.id, start.user.id, start.user.display_name,
                       start.bet, num_raccoons=raccoons)
        view.message = await start.reply(self._render(view), view=view)

    @commands.command(name="dig", aliases=["den", "raccoon"])
    @commands.guild_only()
    async def dig_prefix(self, ctx, bet: str, raccoons: int = DEFAULT_RACCOONS):
        """Dig the den: !dig <bet> [raccoons 1-12] — more raccoons, richer bins."""
        await self._start_game(ctx, bet, raccoons)

    @app_commands.command(name="dig", description="Dig through a raccoon den — pick how many raccoons; more = steeper multipliers.")
    @app_commands.describe(
        bet="Coins to risk on the dig",
        raccoons=f"How many raccoons hide in the 16 bins ({MIN_RACCOONS}-{MAX_RACCOONS}, default {DEFAULT_RACCOONS}) — more raccoons, richer payouts",
    )
    async def dig_slash(self, interaction: discord.Interaction, bet: str,
                        raccoons: app_commands.Range[int, MIN_RACCOONS, MAX_RACCOONS] = DEFAULT_RACCOONS):
        await self._start_game(interaction, bet, raccoons)


async def setup(bot):
    await bot.add_cog(RaccoonDen(bot))
