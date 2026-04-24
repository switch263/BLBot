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

# Each riddle: question, [three options], correct_index.
# Riddles are intentionally absurd. There's no logic. It's a coinflip with vibes.
RIDDLES = [
    ("I have no mouth, but I scream. What am I?",
     ["A file not found error", "The abyss", "My uncle Terry"], 2),
    ("What is greater than God, worse than the devil, the poor have it, the rich need it, and if you eat it you die?",
     ["Nothing", "A gas station burrito", "Hubris"], 0),
    ("Which of these is illegal in Ohio?",
     ["Breathing", "Making eye contact with a corn stalk", "Owning a trombone before 7 AM"], 1),
    ("Pick the one the troll is most afraid of.",
     ["A goat", "A slightly older goat", "A goat wearing sunglasses"], 2),
    ("What did the troll have for breakfast?",
     ["Three (3) wayward cyclists", "A Ford F-150", "His own ear"], 1),
    ("The troll's true name is:",
     ["Gorbax", "Steve", "Steve (the second one)"], 2),
    ("To cross this bridge, you must:",
     ["Answer a riddle", "Give the troll 37 nickels", "Admit that Sonic 06 is underrated"], 0),
    ("What will the troll do if you answer incorrectly?",
     ["Eat you", "Charge you", "Post about it"], 1),
    ("The troll's hobby is:",
     ["Collecting molars", "Competitive bridge (the card game)", "Identity theft"], 1),
    ("Which of these is the troll's favorite sitcom?",
     ["Frasier", "Frasier", "Also Frasier"], 0),
    ("What lives under the bridge besides the troll?",
     ["37 possums in a trench coat", "A forgotten shopping cart named Gerald", "The concept of Tuesday"], 0),
    ("Pick the heavy rock.",
     ["The gray one", "The other gray one", "The heavy one"], 2),
]

FAIL_FLAVOR = [
    "The troll cackles and pockets your coins. Also charges a 'processing fee.'",
    "The troll picks you up, shakes you upside down, keeps what falls out.",
    "WRONG. The troll sends a Venmo request for punitive damages.",
    "The troll is so offended he takes extra. He then sobs about it.",
    "Ha! Says the troll. Ha ha. Ha. He takes more. He laughs some more.",
]

WIN_FLAVOR = [
    "The troll is weirdly impressed. He steps aside and slips you extra from his pouch.",
    "'Good answer,' the troll says, suspiciously. He pays up.",
    "'Nobody's ever said that before,' the troll whispers, doubling your coins.",
    "The troll respects the hustle. You walk across with bonus treasure.",
    "'Fine. FINE.' The troll tips you. Unusual but appreciated.",
]


class BridgeView(discord.ui.View):
    def __init__(self, cog, user_id: int, bet: int, options: list[str], correct_idx: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id
        self.bet = bet
        self.correct_idx = correct_idx
        self.answered = False
        for i, opt in enumerate(options):
            self.add_item(AnswerButton(i, opt))


class AnswerButton(discord.ui.Button):
    def __init__(self, idx: int, label: str):
        super().__init__(style=discord.ButtonStyle.primary, label=label)
        self.idx = idx

    async def callback(self, interaction: discord.Interaction):
        view: BridgeView = self.view  # type: ignore
        if interaction.user.id != view.user_id:
            await interaction.response.send_message("Wait your turn, vagrant.", ephemeral=True)
            return
        if view.answered:
            await interaction.response.defer()
            return
        view.answered = True
        for child in view.children:
            child.disabled = True
            if isinstance(child, AnswerButton):
                if child.idx == view.correct_idx:
                    child.style = discord.ButtonStyle.success
                elif child.idx == self.idx:
                    child.style = discord.ButtonStyle.danger
        await view.cog._resolve(interaction, view, self.idx == view.correct_idx)


class TrollBridge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Troll Bridge loaded.")

    async def _resolve(self, interaction: discord.Interaction, view: BridgeView, correct: bool):
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        bet = view.bet
        if correct:
            payout = bet * 3
            add_coins(guild_id, user_id, payout)
            net = payout - bet
            result = f"✅ **Correct!** {random.choice(WIN_FLAVOR)}\n**+{net}** coins."
        else:
            extra = min(get_coins(guild_id, user_id), bet // 2)
            if extra > 0:
                deduct_coins(guild_id, user_id, extra)
                fine_line = f"**Lost {bet}** + **{extra}** fine."
            else:
                fine_line = f"**Lost {bet}**."
            result = f"❌ **Wrong!** {random.choice(FAIL_FLAVOR)}\n{fine_line}"

        original = interaction.message.content
        new_content = f"{original}\n\n{result}\nBalance: **{get_coins(guild_id, user_id)}**"
        await interaction.response.edit_message(content=new_content, view=view)

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
            await reply("The troll demands tribute. > 0 coins.")
            return
        if get_coins(guild.id, user.id) < bet:
            await reply(f"Too broke for the toll. Balance: **{get_coins(guild.id, user.id)}**")
            return

        deduct_coins(guild.id, user.id, bet)
        question, options, correct_idx = random.choice(RIDDLES)
        view = BridgeView(self, user.id, bet, options, correct_idx)
        text = (
            f"🌉 **{user.display_name}** approaches the bridge. The troll emerges, reeking of bologna.\n"
            f"The troll demands **{bet}** coins and poses a riddle:\n\n"
            f"**❓ {question}**\n\n"
            f"Pick wisely. Correct = **3×** back. Wrong = lose bet + 50% fine."
        )
        await reply(text, view=view)

    @commands.command(name="troll", aliases=["bridge", "riddle"])
    @commands.guild_only()
    async def troll_prefix(self, ctx, bet: int):
        await self._start(ctx, bet)

    @app_commands.command(name="troll", description="Pay a troll, answer a riddle. Correct triples; wrong costs extra.")
    @app_commands.describe(bet="Coins the troll demands as toll")
    async def troll_slash(self, interaction: discord.Interaction, bet: int):
        await self._start(interaction, bet)


async def setup(bot):
    await bot.add_cog(TrollBridge(bot))
