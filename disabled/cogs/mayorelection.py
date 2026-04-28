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

TOTAL_ROUNDS = 3
BREAK_EVEN_VOTES = 50  # votes needed to break even on bet

# Opponents: (name, speeches_mod, bribe_mod, smear_mod, flavor_intro)
# Modifiers multiply the vote roll. Some are hard-countered or super-effective.
OPPONENTS = [
    (
        "Jerry the Raccoon (in a thrifted JCPenney suit)",
        0.4,  # speeches weak (he can't talk)
        1.0,  # bribe normal
        1.7,  # smear amazing (he IS a raccoon, easy to sling dirt)
        "He waves with a tiny paw. Someone claps out of pity.",
    ),
    (
        "A Tire That's Been On Fire Since 1998",
        0.6,  # speeches: nobody can hear over the whooshing flames
        1.8,  # bribe: the tire does not care what you give it
        0.3,  # smear: you can't smear a burning tire, it's ALREADY on fire
        "The tire emits black smoke that spells 'VOTE ME.' Impressive.",
    ),
    (
        "Cousin Randy (who ran last year. And the year before. And before that.)",
        1.6,  # speeches: he's lazy, easy to out-speech
        0.5,  # bribe: he'll tell mom
        1.0,  # smear: he has plenty of dirt either way
        "Randy is wearing a shirt that says 'RANDY 4 MAYOR (AGAIN).' It is sweat-stained.",
    ),
    (
        "Lawn Gnome #4 (the family's least favorite)",
        1.0,
        1.4,  # bribe strong (gnomes accept WEED as legal tender)
        0.6,  # smear weak (gnomes are stoic)
        "The gnome is silent. His eyes follow you. You feel judged.",
    ),
    (
        "Big Ron, Proprietor of the Lay-Z Boy on Lot 42",
        0.7,  # speeches: Ron is louder
        1.5,  # bribe: Ron respects cash
        1.0,
        "Ron reclines in his platform. He has not stood in 14 years. He will not start now.",
    ),
    (
        "Pastor Dave (rumored cannibal)",
        0.5,  # speeches: he has a pulpit, easy loss
        0.8,  # bribe: he donates it to 'the cause' (unclear)
        1.9,  # smear: RUMORED CANNIBAL is a great smear
        "Pastor Dave smiles. His incisors are filed to points. This is fine.",
    ),
    (
        "A Possum Wearing a 'VOTE' Sticker",
        1.3,  # speeches: the possum is just a possum, you can out-speak it
        0.4,  # bribe: it will just eat the cash
        1.1,  # smear works okay
        "The possum plays dead for 45 minutes of the debate. It wins the debate.",
    ),
]

STRATEGIES = {
    "speeches": {
        "emoji": "📣",
        "label": "Give Speeches",
        "base_range": (10, 30),
        "backfire_chance": 0.08,
        "backfire_msg": "You said something racist about birds. Voters flee. Lose votes.",
        "backfire_penalty": (-20, -5),
    },
    "bribe": {
        "emoji": "💰",
        "label": "Bribe Voters",
        "base_range": (0, 45),
        "backfire_chance": 0.20,
        "backfire_msg": "You got caught handing cash to a narc. Voters flee. Lose votes.",
        "backfire_penalty": (-35, -10),
    },
    "smear": {
        "emoji": "🐷",
        "label": "Smear Campaign",
        "base_range": (5, 35),
        "backfire_chance": 0.12,
        "backfire_msg": "Your smear flyer had your home address on it. Sympathy surge FOR YOUR OPPONENT.",
        "backfire_penalty": (-25, -5),
    },
}

SPEECH_QUIPS = [
    "You promise 'more ducks in the pond.' Applause.",
    "You deliver a stirring speech about potholes. The crowd weeps.",
    "Your speech is mostly about your ex. It lands.",
    "You do a call-and-response. Nobody responds. But they remember.",
    "Your closing line: 'I don't not want this.' Profound.",
]

BRIBE_QUIPS = [
    "You slide a twenty and a joint into their pocket. They nod.",
    "You distribute 'campaign sandwiches.' Sandwiches are a powerful force.",
    "You offer a discount on your cousin's tattoo parlor. Voters fold.",
    "You give the pastor a gift card to Hobby Lobby. A classic.",
    "You pay voters in gift cards to a store that closed in 2007. Somehow it works.",
]

SMEAR_QUIPS = [
    "You print fliers saying your opponent 'probably owns a Furby.' Damning.",
    "You spread a rumor that your opponent 'doesn't recycle.' DEVASTATING.",
    "You leak an 'internal memo' you fabricated in Paint.",
    "You hire a guy to stand outside Applebee's with a sign.",
    "You post a blurry photo of your opponent holding what is CLEARLY A SANDWICH but you caption it 'WMD.'",
]


class MayorGame:
    def __init__(self, guild_id, user_id, user_name, bet):
        self.guild_id = guild_id
        self.user_id = user_id
        self.user_name = user_name
        self.bet = bet
        self.round = 1
        self.votes = 0
        self.log: list[str] = []
        # Pick 3 random opponents without repeats
        self.opponents = random.sample(OPPONENTS, TOTAL_ROUNDS)
        self.ended = False


class StrategyButton(discord.ui.Button):
    def __init__(self, key: str):
        data = STRATEGIES[key]
        super().__init__(style=discord.ButtonStyle.primary, label=data["label"], emoji=data["emoji"])
        self.key = key

    async def callback(self, interaction: discord.Interaction):
        view: "MayorView" = self.view  # type: ignore
        g = view.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message("Run your own campaign.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return
        await view.cog._play_round(interaction, view, self.key)


class MayorView(discord.ui.View):
    def __init__(self, cog, game: MayorGame):
        super().__init__(timeout=300)
        self.cog = cog
        self.game = game
        for key in STRATEGIES:
            self.add_item(StrategyButton(key))


class MayorElection(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Trailer Park Mayor Election loaded.")

    def _render(self, g: MayorGame, footer: str | None = None) -> str:
        lines = [
            f"🗳️ **{g.user_name} for Mayor of the Trailer Park** — bet **{g.bet}**",
            f"Round **{g.round}/{TOTAL_ROUNDS}** | Votes: **{g.votes}** _(break even at {BREAK_EVEN_VOTES})_",
        ]
        if not g.ended and g.round <= TOTAL_ROUNDS:
            opp_name, _, _, _, intro = g.opponents[g.round - 1]
            lines.append("")
            lines.append(f"**Opponent:** {opp_name}")
            lines.append(f"_{intro}_")
        if g.log:
            lines.append("")
            lines.extend(g.log[-8:])
        if footer:
            lines.append("")
            lines.append(footer)
        return "\n".join(lines)

    async def _play_round(self, interaction: discord.Interaction, view: MayorView, key: str):
        g = view.game
        opp_name, spk_mod, brb_mod, smr_mod, _ = g.opponents[g.round - 1]
        strategy = STRATEGIES[key]

        # Modifier based on strategy × opponent
        mod = {"speeches": spk_mod, "bribe": brb_mod, "smear": smr_mod}[key]

        # Backfire?
        if random.random() < strategy["backfire_chance"]:
            penalty = random.randint(*strategy["backfire_penalty"])
            g.votes += penalty
            quip = strategy["backfire_msg"]
            g.log.append(f"R{g.round} vs {opp_name}: **{penalty:+d} votes.** {quip}")
        else:
            base = random.randint(*strategy["base_range"])
            gained = int(round(base * mod))
            g.votes += gained
            # Quip
            quip = random.choice({
                "speeches": SPEECH_QUIPS,
                "bribe": BRIBE_QUIPS,
                "smear": SMEAR_QUIPS,
            }[key])
            mod_note = ""
            if mod >= 1.3:
                mod_note = " _(supereffective)_"
            elif mod <= 0.7:
                mod_note = " _(ineffective)_"
            g.log.append(f"R{g.round} vs {opp_name}: **+{gained} votes**{mod_note}. {quip}")

        g.round += 1

        if g.round > TOTAL_ROUNDS:
            # Election over — settle
            g.ended = True
            g.votes = max(g.votes, 0)
            payout = int(g.bet * (g.votes / BREAK_EVEN_VOTES))
            net = payout - g.bet
            if payout > 0:
                add_coins(g.guild_id, g.user_id, payout)
            if g.votes >= BREAK_EVEN_VOTES:
                headline = f"🏆 **ELECTED.** Final vote total: **{g.votes}**."
            else:
                headline = f"💀 **You lost the election** with **{g.votes}** votes."
            footer = f"{headline}\nPayout: **{payout}** coins (net **{'+' if net >= 0 else ''}{net}**).\nBalance: **{get_coins(g.guild_id, g.user_id)}**"
            for child in view.children:
                child.disabled = True
            await interaction.response.edit_message(content=self._render(g, footer), view=view)
            return

        await interaction.response.edit_message(content=self._render(g), view=view)

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
            await reply("Campaigns aren't free. > 0.")
            return
        if get_coins(guild.id, user.id) < bet:
            await reply(f"Too broke to campaign. Balance: **{get_coins(guild.id, user.id)}**")
            return

        deduct_coins(guild.id, user.id, bet)
        game = MayorGame(guild.id, user.id, user.display_name, bet)
        view = MayorView(self, game)
        await reply(self._render(game), view=view)

    @commands.command(name="mayor", aliases=["election", "campaign"])
    @commands.guild_only()
    async def mayor_prefix(self, ctx, bet: int):
        await self._start(ctx, bet)

    @app_commands.command(name="mayor", description="Run for Trailer Park Mayor. 3 rounds, 3 strategies, 7 absurd opponents.")
    @app_commands.describe(bet="Campaign budget")
    async def mayor_slash(self, interaction: discord.Interaction, bet: int):
        await self._start(interaction, bet)


async def setup(bot):
    await bot.add_cog(MayorElection(bot))
