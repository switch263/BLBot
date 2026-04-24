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

ROUNDS = 5
MULT_PER_HIT = 0.5
PRE_CUE_MIN = 2.5
PRE_CUE_MAX = 6.5
CUE_WINDOW = 2.5

WAITING_FLAVOR = [
    "You grip the wheel. The dashed lines hypnotize you.",
    "A possum on the shoulder makes eye contact. Rude.",
    "The radio is stuck on polka. You accept this.",
    "Your headlights briefly illuminate a cornfield. Nothing in it. Probably.",
    "You think about your life choices. Briefly. Then stop.",
    "A single windshield bug. You don't wipe it.",
    "You pass a 'REDUCED SPEED AHEAD' sign at exactly current speed.",
]

CUE_FLAVOR = [
    "🟢 **PRESS NOW** — a deer. A DEER.",
    "🟢 **PRESS NOW** — cop on the shoulder.",
    "🟢 **PRESS NOW** — your exit!",
    "🟢 **PRESS NOW** — a raccoon in the road, no eye contact.",
    "🟢 **PRESS NOW** — the rumble strip is SCREAMING.",
    "🟢 **PRESS NOW** — you are drifting.",
    "🟢 **PRESS NOW** — red light coming fast.",
]

EARLY_MESSAGES = [
    "🚧 **You swerved at nothing.** The car is in a ditch. So are you. Lose it all.",
    "🚧 **You slammed the gas at the wrong moment.** You t-boned a mailbox. Lose it all.",
    "🚧 **You panicked.** The cruiser behind you turned on its lights. Lose it all.",
    "🚧 **You overcorrected into a corn field.** Lose it all.",
]

ASLEEP_MESSAGES = [
    "😴 **You fell asleep.** The car is now part of a barn. Lose it all.",
    "😴 **Your head hit the wheel.** The horn plays a sad song. Lose it all.",
    "😴 **Zzz.** You are now a statistic. Lose it all.",
    "😴 **You drifted into oncoming traffic.** An 18-wheeler honks the Wilhelm scream. Lose it all.",
]

SUCCESS_BEATS = [
    "Nailed it. Car still on road.",
    "Smooth. The deer nods at you.",
    "Cop doesn't even blink.",
    "You missed the raccoon. The raccoon salutes.",
    "Reflexes of a caffeinated squirrel.",
]

COMPLETE_FLAVOR = [
    "You pull into your driveway. Somehow. You are a legend.",
    "You park perfectly. Crooked. But perfectly.",
    "You made it home. Your mom is disappointed but alive.",
    "The car is now at 3% tread on all tires but you survived.",
]


class DUIGame:
    def __init__(self, guild_id, user_id, user_name, bet):
        self.guild_id = guild_id
        self.user_id = user_id
        self.user_name = user_name
        self.bet = bet
        self.round = 0
        self.multiplier = 1.0
        self.state = "idle"  # idle | waiting | cue | done
        self.cue_event = asyncio.Event()
        self.crash_event = asyncio.Event()
        self.beats: list[str] = []
        self.ended = False
        self.end_reason: str | None = None


class DUIView(discord.ui.View):
    def __init__(self, cog, game: DUIGame):
        super().__init__(timeout=120)
        self.cog = cog
        self.game = game

    @discord.ui.button(label="HIT GAS", style=discord.ButtonStyle.danger, emoji="🚗")
    async def gas_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        g = self.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message("Get your own car.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return

        if g.state == "cue":
            g.cue_event.set()
            await interaction.response.defer()
            return

        if g.state == "waiting":
            # Clicked too early → crash
            g.state = "crashed"
            g.crash_event.set()
            await interaction.response.defer()
            return

        await interaction.response.defer()


class DUISimulator(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("DUI Simulator loaded.")

    def _render(self, g: DUIGame, header: str) -> str:
        lines = [
            f"🚗 **{g.user_name}'s DUI Simulator** — bet **{g.bet}**",
            f"Round **{g.round}/{ROUNDS}** | Multiplier: **{g.multiplier:.2f}×**",
            "",
            header,
        ]
        if g.beats:
            lines.append("")
            lines.extend(g.beats[-5:])
        return "\n".join(lines)

    async def _run_game(self, game: DUIGame, view: DUIView, message: discord.Message):
        try:
            for rnd in range(1, ROUNDS + 1):
                game.round = rnd
                game.cue_event.clear()
                game.crash_event.clear()
                game.state = "waiting"

                header = f"*{random.choice(WAITING_FLAVOR)}*"
                try:
                    await message.edit(content=self._render(game, header), view=view)
                except discord.HTTPException:
                    pass

                # Wait the pre-cue random delay, but bail early if user crashed
                pre_cue = random.uniform(PRE_CUE_MIN, PRE_CUE_MAX)
                wait_task = asyncio.create_task(asyncio.sleep(pre_cue))
                crash_task = asyncio.create_task(game.crash_event.wait())
                done, pending = await asyncio.wait(
                    [wait_task, crash_task], return_when=asyncio.FIRST_COMPLETED
                )
                for p in pending:
                    p.cancel()

                if game.crash_event.is_set():
                    game.ended = True
                    game.end_reason = "early"
                    break

                # Cue phase
                game.state = "cue"
                cue_text = random.choice(CUE_FLAVOR)
                try:
                    await message.edit(content=self._render(game, cue_text), view=view)
                except discord.HTTPException:
                    pass

                try:
                    await asyncio.wait_for(game.cue_event.wait(), timeout=CUE_WINDOW)
                    # Hit!
                    game.multiplier += MULT_PER_HIT
                    game.beats.append(f"✅ Round {rnd}: {random.choice(SUCCESS_BEATS)} (×{game.multiplier:.2f})")
                    game.state = "between"
                except asyncio.TimeoutError:
                    game.ended = True
                    game.end_reason = "asleep"
                    break

            # Resolve
            if not game.ended:
                # All rounds complete — auto-bank
                payout = int(game.bet * game.multiplier)
                add_coins(game.guild_id, game.user_id, payout)
                net = payout - game.bet
                final = (
                    f"🏁 **{random.choice(COMPLETE_FLAVOR)}**\n"
                    f"Final multiplier: **{game.multiplier:.2f}×** → **+{net}** coins.\n"
                    f"Balance: **{get_coins(game.guild_id, game.user_id)}**"
                )
            elif game.end_reason == "early":
                final = (
                    f"{random.choice(EARLY_MESSAGES)}\n"
                    f"Lost **{game.bet}**. Balance: **{get_coins(game.guild_id, game.user_id)}**"
                )
            else:  # asleep
                final = (
                    f"{random.choice(ASLEEP_MESSAGES)}\n"
                    f"Lost **{game.bet}**. Balance: **{get_coins(game.guild_id, game.user_id)}**"
                )

            for item in view.children:
                item.disabled = True
            game.state = "done"
            try:
                await message.edit(content=self._render(game, final), view=view)
            except discord.HTTPException:
                pass
        except Exception as e:
            logger.exception(f"DUI sim error: {e}")

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
            await reply("Gas money, bro.")
            return
        if get_coins(guild.id, user.id) < bet:
            await reply(f"Too broke for gas. Balance: **{get_coins(guild.id, user.id)}**")
            return

        deduct_coins(guild.id, user.id, bet)
        game = DUIGame(guild.id, user.id, user.display_name, bet)
        view = DUIView(self, game)
        intro = (
            f"🚗 **{user.display_name}** fires up the engine. Bet: **{bet}**.\n"
            f"**Rules:** Wait for 🟢 **PRESS NOW** then tap HIT GAS within **{CUE_WINDOW:.1f}s**.\n"
            f"Click too early = ditch. Too late = asleep. **{ROUNDS}** rounds.\n"
            f"Each successful round adds +{MULT_PER_HIT:.1f}× to the multiplier."
        )
        msg = await reply(intro, view=view)
        # Start the game loop
        asyncio.create_task(self._run_game(game, view, msg))

    @commands.command(name="dui", aliases=["drive", "drunk"])
    @commands.guild_only()
    async def dui_prefix(self, ctx, bet: int):
        await self._start(ctx, bet)

    @app_commands.command(name="dui", description="DUI reflex simulator. Tap HIT GAS when prompted. Do not crash.")
    @app_commands.describe(bet="How much gas money you're risking")
    async def dui_slash(self, interaction: discord.Interaction, bet: int):
        await self._start(interaction, bet)


async def setup(bot):
    await bot.add_cog(DUISimulator(bot))
