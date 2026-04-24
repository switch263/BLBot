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
            (18, 0.0,  "The jogger is a cardio beast. They outrun you. You are winded and sober now."),
            (30, 1.5,  "You catch them. They drop a fanny pack of granola bars and loose bills."),
            (18, 2.0,  "You eat a jogger. A whole jogger. They had a full wallet."),
            (13, 0.0,  "The jogger was an undercover cop. You are tased. Humiliating."),
            (6,  4.0,  "The jogger was a tech CEO. You now have their Rolex AND their coins."),
            (3,  0.0,  "The jogger had bear spray. You know what you did."),
            (4,  2.5,  "You ate the jogger's AirPods. They still work somehow. ×2.5."),
            (3,  3.5,  "The jogger challenges you to a footrace for pride. You somehow win. ×3.5."),
            (2,  0.3,  "The jogger's kid is with them. You have scruples, apparently. You sulk off with pocket lint."),
            (2,  6.0,  "The jogger was a lawyer. You ate the lawyer. Estate gives you a windfall."),
            (1,  0.0,  "The jogger was an undercover cryptid. IT bites YOU. Humiliating AND mystical."),
        ],
    },
    "eat_jetski": {
        "emoji": "🚤",
        "label": "Eat a Jet Ski",
        "outcomes": [
            (20, 0.0,  "The jet ski tastes like fiberglass and regret. Your teeth are ruined."),
            (18, 1.5,  "You scared the rider off the ski. They left their tackle box. It is mostly full."),
            (17, 2.5,  "You ate most of the ski. You are now 73% fiberglass. Worth it."),
            (12, 4.0,  "You swallowed the ignition key. You ARE the ski now. Sponsorship ensues."),
            (10, 6.0,  "The jet ski had drugs in it. You now have more drugs. Also coins."),
            (6,  12.0, "Went viral on TikTok. Red Bull sponsors you. The ski man is now your agent."),
            (5,  1.8,  "There was a baby seat (empty, mercifully) with a gift card glued inside. ×1.8."),
            (4,  0.3,  "You choked on the battery. Hospital bill. Partial refund from a soft-hearted ER nurse."),
            (3,  6.0,  "Found a treasure map sewn into the seat foam. X marks an ATM. ×6."),
            (3,  0.0,  "The Coast Guard was three seconds away. You flee with nothing."),
            (2,  8.0,  "It was a RENTAL. The deposit check was still in the glovebox. Jackpot."),
        ],
    },
    "crash_wedding": {
        "emoji": "💒",
        "label": "Crash a Wedding",
        "outcomes": [
            (13, 0.0,  "Grandma beats you senseless with a cane. Nobody comes to help. Lose bet."),
            (18, 1.2,  "You eat the cake. The baker cries. Small haul in the kitchen."),
            (22, 1.8,  "You eat the bouquet. Bride screams. You find cash in a card."),
            (16, 3.0,  "You eat a minor groomsman. The groom is SECRETLY RELIEVED. He tips you."),
            (10, 5.0,  "You eat the dowry envelopes. The contents are yours now."),
            (6,  7.0,  "The groom joins your chaos. You are now business partners. Huge payout."),
            (3,  0.5,  "The DJ plays 'Despacito.' You lose focus. Shuffle away with chips and dip."),
            (4,  4.0,  "The officiant was ALSO a gator. You bonded over a mutual hatred of monogamy. ×4."),
            (3,  2.0,  "You were mistaken for paid entertainment. You did not dance. They paid anyway."),
            (3,  0.5,  "The fire alarm went off during the vows. You got blamed. Some refund, some fine."),
            (2,  8.0,  "You ate the venue. Not the food — the BUILDING. Insurance payout applies."),
        ],
    },
    "dollar_store": {
        "emoji": "🏪",
        "label": "Attack a Dollar Store",
        "outcomes": [
            (15, 0.5,  "The automatic doors intimidate you. You leave with a single pool noodle."),
            (34, 1.3,  "You eat a bag of Flamin' Hot and 3 lighters. Register is open. +a little."),
            (22, 1.8,  "You find $20 in crumpled bills under a shelf. You eat the shelf."),
            (9,  1.0,  "Locked in overnight. Ate the entire beef jerky rack. Break even."),
            (6,  3.5,  "Discovered the manager's safe. It was unlocked. Embarrassing for them."),
            (3,  8.0,  "Found the DOLLAR GENERAL VAULT (local legend). You are rich now."),
            (5,  1.4,  "The cashier tips you from her own tip jar 'for the show.' ×1.4."),
            (3,  3.0,  "You scratched a scratch-off with your claw. Winner. ×3."),
            (2,  0.6,  "You got caught eating the welcome mat. Partial refund, full shame."),
            (1,  0.0,  "The store was a SET for an indie film. No coins. Just regret."),
        ],
    },
    "appear_on_news": {
        "emoji": "📺",
        "label": "Appear on Local News",
        "outcomes": [
            (18, 1.5,  "Slow news day. They do a fluff piece on you. Pays well in exposure AND coins."),
            (17, 2.5,  "Viral sponsorship deal. Axe Body Spray wants your reptilian face on billboards."),
            (17, 0.0,  "You get into a political argument with the anchor. They drag you out."),
            (12, 2.0,  "You interrupt the weather. The meteorologist laughs so hard he gives you a tip."),
            (10, 0.4,  "Shot with a tranquilizer dart live. You wake up with a smaller wallet."),
            (7,  5.0,  "Somehow you are elected mayor during the broadcast. Generous stipend."),
            (5,  0.0,  "The intern reporter was your EX. She reveals all your secrets. You flee."),
            (5,  1.5,  "You endorsed a random city council candidate on air. They lost but paid you."),
            (4,  4.0,  "A streaming service picked up your reality show that very afternoon. ×4."),
            (3,  2.0,  "The weather map was projected onto your body for 7 minutes. Ad revenue was yours."),
            (2,  8.0,  "A Hollywood agent happened to be watching. You now have representation. ×8."),
        ],
    },
    "hoa_raid": {
        "emoji": "🏠",
        "label": "Raid the HOA President's House",
        "outcomes": [
            (14, 0.0,  "The HOA president was home. With a gun. You flee the subdivision."),
            (22, 2.0,  "Found their secret stash of coins marked 'FOR BRIBES.' ×2."),
            (18, 1.5,  "Ate their entire prize-winning garden. Passive-aggressive note was all that remained."),
            (12, 3.0,  "Got caught but they were so impressed they MADE YOU the new HOA president. ×3."),
            (10, 0.5,  "Cops were called. You ran. You dropped most of the coins. Partial refund."),
            (8,  4.0,  "Emptied the HOA treasury. Fines go up next month but you are RICH. ×4."),
            (6,  6.0,  "The president's mom was home. She ADORED you. Gave you her inheritance early."),
            (5,  0.0,  "Their security system was 'smart.' The fridge alone called 911. Lose bet."),
            (3,  7.0,  "They were running a Ponzi scheme. You exposed it. Whistleblower reward. ×7."),
            (2,  0.0,  "The 'HOA President' was actually a raccoon in a tie. Humiliating."),
        ],
    },
    "costco_samples": {
        "emoji": "🛒",
        "label": "Rob a Costco Sample Cart",
        "outcomes": [
            (35, 1.3,  "Ate every sample on the cart. The old lady in the apron saluted. Small payout."),
            (20, 1.5,  "Security asked you to leave. Gave you a $5 gift card as a parting gift. ×1.5."),
            (13, 0.7,  "Tackled by an elderly linebacker in a grandma sweater. Partial refund."),
            (10, 2.5,  "Ate the rotisserie chicken display. ALL OF IT. Management respects it. ×2.5."),
            (6,  5.0,  "Found a Kirkland Signature gold bar in the clearance bin. ×5."),
            (5,  2.0,  "Joined a cult that meets in aisle 12. They paid for your Kirkland Signature initiation."),
            (4,  1.0,  "Bought a membership on the way out. Break even spiritually and financially."),
            (3,  3.5,  "The hot dog combo was only $1.50. Obviously a scam. YOU ate the REGISTER."),
            (2,  8.0,  "Somehow you sold the empty sample cart for ×8 to a collector. Do not ask."),
            (2,  0.0,  "The sample cart was a SECURITY DRONE. It tasered you AND your ego."),
        ],
    },
    "prius_race": {
        "emoji": "🚗",
        "label": "Challenge a Prius to a Drag Race",
        "outcomes": [
            (25, 0.3,  "The Prius beat you off the line. It beat you at the finish. It beat you in spirit."),
            (18, 2.5,  "You crashed the Prius. Insurance scam nets you a settlement. ×2.5."),
            (13, 1.8,  "Prius driver was SO impressed they tipped you in Trader Joe's gift cards. ×1.8."),
            (12, 3.0,  "You ate the Prius. Battery included. You now hum at a constant low frequency."),
            (10, 0.0,  "The Prius was a Tesla. The Tesla was a Cybertruck. The Cybertruck was cheating. Lose bet."),
            (6,  7.0,  "A NASCAR scout was filming. Sponsorship deal on the spot. ×7."),
            (5,  0.0,  "The driver was an off-duty cop. They were ON-DUTY now. Cuffed and fined."),
            (4,  4.0,  "Prius driver quit on the spot and handed you the keys. Insurance, title, everything."),
            (4,  1.5,  "It ended in a draw. You shook hands. He gave you his rewards-card points."),
            (3,  0.5,  "Someone on Reddit filmed the whole thing. You're a meme. No money but FAME."),
        ],
    },
}


class MethGatorView(discord.ui.View):
    def __init__(self, cog, user_id: int, bet: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.bet = bet
        for i, (key, data) in enumerate(ACTIONS.items()):
            # Discord max 5 buttons per row; split across rows 0 and 1.
            row = 0 if i < 4 else 1
            self.add_item(ActionButton(key, data["label"], data["emoji"], row=row))


class ActionButton(discord.ui.Button):
    def __init__(self, action_key: str, label: str, emoji: str, row: int = 0):
        super().__init__(style=discord.ButtonStyle.primary, label=label, emoji=emoji, row=row)
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
