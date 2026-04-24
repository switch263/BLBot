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

# Each action has its own weighted outcome table.
# (weight, multiplier, flavor). Multiplier is total payout on bet (0 = total loss, 1 = break even).
ACTIONS = {
    "chase_jogger": {
        "emoji": "🏃",
        "label": "Chase a Jogger",
        "outcomes": [
            (20, 0.0,  "The jogger is a cardio beast. They outrun you. You are winded and sober now."),
            (35, 1.5,  "You catch them. They drop a fanny pack of granola bars and loose bills."),
            (20, 2.0,  "You eat a jogger. A whole jogger. They had a full wallet."),
            (15, 0.0,  "The jogger was an undercover cop. You are tased. Humiliating."),
            (7,  4.0,  "The jogger was a tech CEO. You now have their Rolex AND their coins."),
            (3,  0.0,  "The jogger had bear spray. You know what you did."),
        ],
    },
    "eat_jetski": {
        "emoji": "🚤",
        "label": "Eat a Jet Ski",
        "outcomes": [
            (25, 0.0,  "The jet ski tastes like fiberglass and regret. Your teeth are ruined."),
            (20, 1.5,  "You scared the rider off the ski. They left their tackle box. It is mostly full."),
            (20, 2.5,  "You ate most of the ski. You are now 73% fiberglass. Worth it."),
            (15, 4.0,  "You swallowed the ignition key. You ARE the ski now. Sponsorship ensues."),
            (12, 6.0,  "The jet ski had drugs in it. You now have more drugs. Also coins."),
            (8,  12.0, "Went viral on TikTok. Red Bull sponsors you. The ski man is now your agent."),
        ],
    },
    "crash_wedding": {
        "emoji": "💒",
        "label": "Crash a Wedding",
        "outcomes": [
            (15, 0.0,  "Grandma beats you senseless with a cane. Nobody comes to help. Lose bet."),
            (20, 1.2,  "You eat the cake. The baker cries. Small haul in the kitchen."),
            (25, 1.8,  "You eat the bouquet. Bride screams. You find cash in a card."),
            (18, 3.0,  "You eat a minor groomsman. The groom is SECRETLY RELIEVED. He tips you."),
            (12, 5.0,  "You eat the dowry envelopes. The contents are yours now."),
            (7,  7.0,  "The groom joins your chaos. You are now business partners. Huge payout."),
            (3,  0.5,  "The DJ plays 'Despacito.' You lose focus. Shuffle away with chips and dip."),
        ],
    },
    "dollar_store": {
        "emoji": "🏪",
        "label": "Attack a Dollar Store",
        "outcomes": [
            (15, 0.5,  "The automatic doors intimidate you. You leave with a single pool noodle."),
            (40, 1.3,  "You eat a bag of Flamin' Hot and 3 lighters. Register is open. +a little."),
            (25, 1.8,  "You find $20 in crumpled bills under a shelf. You eat the shelf."),
            (10, 1.0,  "Locked in overnight. Ate the entire beef jerky rack. Break even."),
            (7,  3.5,  "Discovered the manager's safe. It was unlocked. Embarrassing for them."),
            (3,  8.0,  "Found the DOLLAR GENERAL VAULT (local legend). You are rich now."),
        ],
    },
    "appear_on_news": {
        "emoji": "📺",
        "label": "Appear on Local News",
        "outcomes": [
            (20, 1.5,  "Slow news day. They do a fluff piece on you. Pays well in exposure AND coins."),
            (20, 2.5,  "Viral sponsorship deal. Axe Body Spray wants your reptilian face on billboards."),
            (20, 0.0,  "You get into a political argument with the anchor. They drag you out."),
            (15, 2.0,  "You interrupt the weather. The meteorologist laughs so hard he gives you a tip."),
            (12, 0.4,  "Shot with a tranquilizer dart live. You wake up with a smaller wallet."),
            (8,  5.0,  "Somehow you are elected mayor during the broadcast. Generous stipend."),
            (5,  0.0,  "The intern reporter was your EX. She reveals all your secrets. You flee."),
        ],
    },
}


class MethGatorView(discord.ui.View):
    def __init__(self, cog, user_id: int, bet: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.bet = bet
        for key, data in ACTIONS.items():
            self.add_item(ActionButton(key, data["label"], data["emoji"]))


class ActionButton(discord.ui.Button):
    def __init__(self, action_key: str, label: str, emoji: str):
        super().__init__(style=discord.ButtonStyle.primary, label=label, emoji=emoji)
        self.action_key = action_key

    async def callback(self, interaction: discord.Interaction):
        view: MethGatorView = self.view  # type: ignore
        if interaction.user.id != view.user_id:
            await interaction.response.send_message("Not your gator.", ephemeral=True)
            return
        for child in view.children:
            child.disabled = True
        self.style = discord.ButtonStyle.success
        await view.cog._resolve(interaction, view, self.action_key)


class MethGator(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Meth Gator Rampage loaded.")

    def _pick_outcome(self, outcomes):
        total = sum(w for w, _, _ in outcomes)
        roll = random.uniform(0, total)
        running = 0.0
        for weight, mult, flavor in outcomes:
            running += weight
            if roll <= running:
                return mult, flavor
        return outcomes[-1][1], outcomes[-1][2]

    async def _resolve(self, interaction: discord.Interaction, view: MethGatorView, action_key: str):
        action = ACTIONS[action_key]
        mult, flavor = self._pick_outcome(action["outcomes"])

        guild_id = interaction.guild.id
        user_id = interaction.user.id
        bet = view.bet

        if mult >= 1.0:
            payout = int(bet * mult)
            add_coins(guild_id, user_id, payout)
            result = f"**×{mult:.2f}** → **+{payout - bet}** coins."
        elif mult > 0:
            payout = int(bet * mult)
            add_coins(guild_id, user_id, payout)
            result = f"**×{mult:.2f}** → partial refund **{payout}**. Lost **{bet - payout}**."
        else:
            result = f"**Lost {bet}** coins."

        text = (
            f"🐊 **{interaction.user.display_name}'s Meth Gator** picks: **{action['emoji']} {action['label']}**\n\n"
            f"_{flavor}_\n\n"
            f"{result}\n"
            f"Balance: **{get_coins(guild_id, user_id)}**"
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
            await reply("Server only.")
            return
        jmsg = jail_message(guild.id, user.id)
        if jmsg:
            await reply(jmsg)
            return
        if bet <= 0:
            await reply("The meth gator demands tribute. > 0.")
            return
        if get_coins(guild.id, user.id) < bet:
            await reply(f"Too broke for chaos. Balance: **{get_coins(guild.id, user.id)}**")
            return

        deduct_coins(guild.id, user.id, bet)
        view = MethGatorView(self, user.id, bet)
        content = (
            f"🐊 **{user.display_name}** is a meth gator. **{bet}** coins on the line.\n"
            f"Pick your rampage. Each option has a different personality — and a different distribution of chaos."
        )
        await reply(content, view=view)

    @commands.command(name="methgator", aliases=["gator", "rampage"])
    @commands.guild_only()
    async def gator_prefix(self, ctx, bet: int):
        await self._start(ctx, bet)

    @app_commands.command(name="methgator", description="You are a meth gator. Pick a rampage. Pray.")
    @app_commands.describe(bet="Coins to stake on your reptilian mayhem")
    async def gator_slash(self, interaction: discord.Interaction, bet: int):
        await self._start(interaction, bet)


async def setup(bot):
    await bot.add_cog(MethGator(bot))
