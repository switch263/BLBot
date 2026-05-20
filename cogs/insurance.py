import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

from economy import get_coins, jail_message, jail_user, transfer_to_house, casino_payout, MAX_BET

logger = logging.getLogger(__name__)

# Each claim has its own weighted outcome table.
# (weight, multiplier, jail_seconds, flavor)
# multiplier 0.0 = total loss. >= 1.0 = profit.
# jail_seconds > 0 = the user gets locked up for that long.
CLAIMS = {
    "whiplash": {
        "emoji": "🚗",
        "label": "Whiplash Claim",
        "outcomes": [
            (30, 1.3, 0,       "Settled out of court. The chiropractor signs whatever you bring."),
            (25, 0.8, 0,       "Adjuster paid the minimum and went to lunch. Easy money."),
            (15, 0.4, 0,       "Refund of premium. Adjuster suspicious but tired. Break-even."),
            (12, 0.4, 0,       "Partial denial — 'pre-existing condition'. Half-back."),
            (8,  2.1, 0,       "Sympathetic juror saw the neck brace and wept. ×2.5."),
            (5,  0.0, 0,       "Surveillance shows you benching 225 the next morning. Denied."),
            (3,  0.0, 60 * 20, "Investigator catches the gym footage. Fraud charges, 20m in the box."),
            (2,  3.4, 0,       "Riding shotgun on a class-action means your bogus pain funds Cabo. ×4."),
        ],
    },
    "warehouse_fire": {
        "emoji": "🔥",
        "label": "Warehouse Fire",
        "outcomes": [
            (20, 0.8, 0,       "Inventory mysteriously catches fire. Sprinklers mysteriously off. ×2."),
            (16, 1.2, 0,       "Convenient electrical fault. Claim filed before the embers cool. ×3."),
            (12, 0.6, 0,       "Partial payout — they noticed the gas can in the parking lot. ×1.5."),
            (10, 0.6, 0,       "Claim slow-walked 18 months through bureaucracy. Break-even."),
            (12, 0.0, 0,       "Arson investigator found receipts for kerosene. Denied."),
            (10, 0.7, 0,       "You forgot to mention the rare violins in the back. Bonus payout. ×5."),
            (8,  2.4, 0,       "The 'warehouse' was a barn full of vintage muscle cars. Jackpot ×6."),
            (5,  0.0, 60 * 45, "ATF kicks the door down. Arson + fraud. 45m."),
            (4,  3.3, 0,       "The warehouse next door also burned — and YOU insured both. ×8."),
            (2,  0.0, 60 * 90, "The arsonist you hired was an undercover agent. Federal heat. 90m."),
            (1, 4.9, 0,       "Insurance company also commits fraud during your claim. You blackmail them. ×12."),
        ],
    },
    "jetski": {
        "emoji": "🚤",
        "label": "Jet Ski Disappearance",
        "outcomes": [
            (22, 1.1, 0,       "Reported stolen at the dock. Adjuster never visits. ×1.8."),
            (18, 0.9, 0,       "Coast Guard logged a 'capsizing event'. Full payout. ×2.5."),
            (15, 0.4, 0,       "Claim sat six months. You got your premium back. Whatever."),
            (12, 0.3, 0,       "Adjuster found the ski parked at your cousin's. Half-paid."),
            (10, 2.4, 0,       "Insurance also lost your paperwork. Paid extra to make you go away. ×4."),
            (8,  0.0, 0,       "Marine forensics. They CSI'd the boat ramp. Denied."),
            (7,  1.8, 0,       "Hurricane hit the harbor that week. Act of God ×3."),
            (4,  0.0, 60 * 30, "GPS tracker pinged from your garage. Fraud. 30m."),
            (2,  1.2, 0,       "You salvaged the ski yourself AND collected. Double-dip ×6."),
            (2,  0.0, 60 * 90, "Adjuster recognized your name from THREE prior claims. The pattern. 90m."),
        ],
    },
    "fake_death": {
        "emoji": "💀",
        "label": "Fake Your Own Death",
        "outcomes": [
            (20, 1.8, 0,        "Body double from the morgue cooperates. Life policy pays out big. ×5."),
            (15, 3.5, 0,        "Closed-casket funeral. Cousin signs the affidavit. ×3.5."),
            (15, 0.0, 0,        "Your mom came to identify the body. Plan collapses. Lose it all."),
            (12, 0.0, 60 * 60,  "FBI flags you boarding a flight as 'Brad Wilson'. 60m."),
            (10, 2.9, 0,        "Whole life policy pays. AND your fake wife collects too. ×8."),
            (10, 1.0, 0,        "Plan stalled — payout never came, but no one caught on. Break-even."),
            (8,  1.2, 0,        "Sister liquidates your assets and sends cash via cousin in Belize. ×2."),
            (5,  0.0, 0,        "Tabloid finds you on a beach. You return the money to stay 'dead'."),
            (3, 4.3, 0,        "Movie deal on top. Tom Hanks plays you. ×12."),
            (2,  0.0, 60 * 120, "Caught at your OWN funeral. Eating cake. 2 hours in the box."),
        ],
    },
    "antiques": {
        "emoji": "👵",
        "label": "Grandma's Antiques",
        "outcomes": [
            (25, 0.0, 0,       "The urn was actually grandma. Karma denied the claim."),
            (18, 2.0, 0,       "Appraiser was on the take. Inflated everything by 200%. ×2."),
            (15, 1.5, 0,       "Estate paid out partial. The cat got half. ×1.5."),
            (12, 1.8, 0,       "The vase was real Ming. You broke it. Insurance covered. ×3."),
            (10, 2.4, 0,       "Hidden Picasso 'lost' to a leaky roof. ×4."),
            (8,  0.0, 0,       "Niece's TikTok shows the urn intact yesterday. Denied."),
            (5,  3.6, 0,       "Whole estate burns down conveniently. ×6."),
            (4,  0.3, 0,       "Adjuster paid out, family sues you, you settle. Half-back."),
            (2,  0.0, 60 * 60, "Probate court catches the forged appraisal. 60m in the box."),
            (1, 5.9, 0,       "Antiques Roadshow segment goes viral. Museum buys the lot. ×10."),
        ],
    },
}


class InsuranceView(discord.ui.View):
    def __init__(self, cog, user_id: int, bet: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.bet = bet
        for i, (key, data) in enumerate(CLAIMS.items()):
            row = 0 if i < 3 else 1
            self.add_item(ClaimButton(key, data["label"], data["emoji"], row=row))


class ClaimButton(discord.ui.Button):
    def __init__(self, claim_key: str, label: str, emoji: str, row: int = 0):
        super().__init__(style=discord.ButtonStyle.primary, label=label, emoji=emoji, row=row)
        self.claim_key = claim_key

    async def callback(self, interaction: discord.Interaction):
        view: InsuranceView = self.view  # type: ignore
        if interaction.user.id != view.user_id:
            await interaction.response.send_message("Not your policy.", ephemeral=True)
            return
        for child in view.children:
            child.disabled = True
        self.style = discord.ButtonStyle.success
        await view.cog._resolve(interaction, view, self.claim_key)


class Insurance(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Insurance Fraud Bureau loaded.")

    def _pick_outcome(self, outcomes):
        total = sum(w for w, *_ in outcomes)
        roll = random.uniform(0, total)
        running = 0.0
        for weight, mult, jail_s, flavor in outcomes:
            running += weight
            if roll <= running:
                return mult, jail_s, flavor
        return outcomes[-1][1], outcomes[-1][2], outcomes[-1][3]

    async def _resolve(self, interaction: discord.Interaction, view: InsuranceView, claim_key: str):
        claim = CLAIMS[claim_key]
        mult, jail_s, flavor = self._pick_outcome(claim["outcomes"])

        guild_id = interaction.guild.id
        user_id = interaction.user.id
        bet = view.bet

        if mult >= 1.0:
            requested = int(bet * mult)
            paid = casino_payout(guild_id, user_id, requested)
            short = f" *(house was short — owed {requested:,})*" if paid < requested else ""
            result = f"**×{mult:.2f}** → **{paid - bet:+,}** coins.{short}"
        elif mult > 0:
            requested = int(bet * mult)
            paid = casino_payout(guild_id, user_id, requested)
            short = f" *(house was short — owed {requested:,})*" if paid < requested else ""
            result = f"**×{mult:.2f}** → partial payout **{paid:,}**. Lost **{bet - paid:,}**.{short}"
        else:
            result = f"**Lost {bet:,}** coins."

        jail_line = ""
        if jail_s > 0:
            bail_amount = max(50, int(bet * 0.5))
            channel_id = getattr(interaction.channel, "id", 0)
            jail_user(
                guild_id, user_id, jail_s,
                reason=f"Insurance fraud — {claim['label']}",
                bail_amount=bail_amount, channel_id=channel_id,
            )
            mins = max(1, jail_s // 60)
            jail_line = (
                f"\n🚔 **Jailed for {mins}m.** Bail set at **{bail_amount:,}** — "
                f"a friend can `/bail` you (once per week)."
            )

        text = (
            f"📋 **{interaction.user.display_name}'s Insurance Claim** — "
            f"**{claim['emoji']} {claim['label']}**\n\n"
            f"_{flavor}_\n\n"
            f"{result}{jail_line}\n"
            f"Balance: **{get_coins(guild_id, user_id):,}**"
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
            await reply("Premium has to be > 0. The actuary is firm on this.")
            return
        if bet > MAX_BET:
            await reply(f"Easy, high roller — max premium is {MAX_BET:,} coins.")
            return
        bet_result = transfer_to_house(guild.id, user.id, bet)
        if not bet_result.get("ok"):
            if bet_result.get("error") == "broke":
                await reply(f"Premium denied — insufficient funds. Balance: **{bet_result.get('have', 0):,}**")
            else:
                await reply("Premium couldn't process. The actuary is on lunch.")
            return
        view = InsuranceView(self, user.id, bet)
        content = (
            f"📋 **{user.display_name}** walks into the Insurance Fraud Bureau. "
            f"Premium paid: **{bet:,}** coins.\n"
            f"Pick a claim. Each has a different risk profile — and a different chance of jail."
        )
        await reply(content, view=view)

    @commands.command(name="insurance", aliases=["claim", "fraud"])
    @commands.guild_only()
    async def insurance_prefix(self, ctx, bet: int):
        await self._start(ctx, bet)

    @app_commands.command(name="insurance", description="File a fraudulent insurance claim. Pick your scheme. Try not to get caught.")
    @app_commands.describe(bet="Premium you're paying upfront")
    async def insurance_slash(self, interaction: discord.Interaction, bet: int):
        await self._start(interaction, bet)


async def setup(bot):
    await bot.add_cog(Insurance(bot))
