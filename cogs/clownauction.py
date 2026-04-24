import discord
from discord.ext import commands
from discord import app_commands
import random
import sys
import os
import logging
import asyncio
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from economy import get_coins, add_coins, deduct_coins, jail_message

logger = logging.getLogger(__name__)

INITIAL_SECONDS = 45
EXTENSION_SECONDS = 15  # each new bid extends the timer

BID_INCREMENTS = [10, 50, 250, 1000]

# (weight, multiplier_on_winning_bid, flavor)
BOX_CONTENTS = [
    # Scam tier (most common) — multiplier on what they PAID
    (25, 0.0,  "📦 An empty box. There is a single pubic hair. You lose it all."),
    (15, 0.1,  "🧽 A wet sponge. Smells musty. Worth basically nothing."),
    (15, 0.3,  "🥫 Four cans of generic beans. Dented. ~30% of what you paid."),
    (10, 0.5,  "🦝 A sleeping raccoon. It wakes up angry. You flee with half your bid's value."),
    # Break-even-ish
    (10, 0.75, "📻 A working AM radio stuck on polka 24/7. Recovers 75%."),
    (8,  1.0,  "🧸 A stuffed animal with LEDs. Break even. Weird outcome honestly."),
    # Small wins
    (6,  1.5,  "💿 Three mint-condition Limp Bizkit CDs. Collectors call. +50%."),
    (4,  2.0,  "👟 A box of off-brand sneakers. Actually fire. ×2."),
    # Nice wins
    (3,  3.5,  "💎 A 'diamond' ring that's somehow real. ×3.5."),
    (2,  5.0,  "🎮 Sealed original Xbox with 7 games. ×5."),
    # Jackpots
    (1,  10.0, "🏆 A small bag of unmarked bills. You walk away ×10."),
    (1,  20.0, "🛸 AN ACTUAL UFO FRAGMENT. A men-in-black type shows up with a briefcase of cash. ×20."),
]


class Auction:
    LOBBY = "lobby"
    DONE = "done"

    def __init__(self, guild_id: int, channel_id: int, host_id: int, starting_bid: int):
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.host_id = host_id
        self.starting_bid = starting_bid
        self.current_bid = 0
        self.current_bidder: discord.Member | None = None
        self.deadline = 0.0
        self.phase = Auction.LOBBY
        self.message: discord.Message | None = None
        self.timer_task: asyncio.Task | None = None
        self.history: list[tuple[str, int]] = []  # (bidder_name, amount)
        # all bidders who currently have coins escrowed with the auction
        # map user_id -> amount escrowed (so we can refund losers on resolution)
        self.escrow: dict[int, int] = {}


class BidButton(discord.ui.Button):
    def __init__(self, increment: int, row: int):
        super().__init__(style=discord.ButtonStyle.primary, label=f"+{increment}", row=row)
        self.increment = increment

    async def callback(self, interaction: discord.Interaction):
        view: "AuctionView" = self.view  # type: ignore
        a = view.auction
        if a.phase != Auction.LOBBY:
            await interaction.response.send_message("Auction's over.", ephemeral=True)
            return
        jmsg = jail_message(a.guild_id, interaction.user.id)
        if jmsg:
            await interaction.response.send_message(jmsg, ephemeral=True)
            return

        new_bid = max(a.current_bid, a.starting_bid - 1) + self.increment
        # If user has existing escrow, their effective additional cost is (new_bid - existing_escrow).
        existing = a.escrow.get(interaction.user.id, 0)
        need = new_bid - existing
        if need <= 0:
            # shouldn't happen given increments are positive, but guard
            await interaction.response.send_message("That bid doesn't increase the leader.", ephemeral=True)
            return
        balance = get_coins(a.guild_id, interaction.user.id)
        if balance < need:
            await interaction.response.send_message(
                f"Too broke — need another **{need}**. Balance: **{balance}**.", ephemeral=True)
            return

        # Deduct the incremental escrow
        deduct_coins(a.guild_id, interaction.user.id, need)
        a.escrow[interaction.user.id] = new_bid
        a.current_bid = new_bid
        a.current_bidder = interaction.user
        a.history.append((interaction.user.display_name, new_bid))
        # Extend the deadline
        a.deadline = max(a.deadline, time.time() + EXTENSION_SECONDS)

        view._refresh_labels()
        await interaction.response.edit_message(content=view.cog._render(a), view=view)


class WithdrawButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.danger, label="Withdraw (refund)", emoji="🚪", row=1)

    async def callback(self, interaction: discord.Interaction):
        view: "AuctionView" = self.view  # type: ignore
        a = view.auction
        if a.phase != Auction.LOBBY:
            await interaction.response.send_message("Auction's over.", ephemeral=True)
            return
        amount = a.escrow.pop(interaction.user.id, 0)
        if amount <= 0:
            await interaction.response.send_message("You haven't bid anything to withdraw.", ephemeral=True)
            return
        if a.current_bidder and a.current_bidder.id == interaction.user.id:
            await interaction.response.send_message(
                "Can't withdraw while you're the top bidder — someone has to outbid you.", ephemeral=True)
            a.escrow[interaction.user.id] = amount  # restore
            return
        add_coins(a.guild_id, interaction.user.id, amount)
        await interaction.response.send_message(
            f"Withdrew **{amount}** coins. You're out of the bidding.", ephemeral=True)


class AuctionView(discord.ui.View):
    def __init__(self, cog, auction: Auction):
        super().__init__(timeout=INITIAL_SECONDS + 60)
        self.cog = cog
        self.auction = auction
        for i, inc in enumerate(BID_INCREMENTS):
            self.add_item(BidButton(inc, row=0))
        self.add_item(WithdrawButton())

    def _refresh_labels(self):
        pass  # increments stay fixed; current bid visible in message


class ClownAuction(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auctions: dict[int, Auction] = {}  # channel_id -> auction

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Clown Auction loaded.")

    def _render(self, a: Auction, footer: str | None = None) -> str:
        lines = [
            f"🎪 **MYSTERY BOX AUCTION** 🎪",
            f"A clown drags a cardboard box into the center of the room. It smells.",
            f"Starting bid: **{a.starting_bid}** | Current top bid: **{a.current_bid}**"
            + (f" by **{a.current_bidder.display_name}**" if a.current_bidder else ""),
            f"Ends <t:{int(a.deadline)}:R>. Each new bid extends the timer by {EXTENSION_SECONDS}s.",
        ]
        if a.history:
            last = a.history[-5:]
            lines.append("")
            lines.append("**Bids:**")
            for name, amt in last:
                lines.append(f"• {name}: **{amt}**")
        if footer:
            lines.append("")
            lines.append(footer)
        return "\n".join(lines)

    async def _auction_timer(self, a: Auction):
        try:
            while time.time() < a.deadline and a.phase == Auction.LOBBY:
                remaining = a.deadline - time.time()
                await asyncio.sleep(min(remaining, 1.5))
        except asyncio.CancelledError:
            return
        if a.phase == Auction.LOBBY:
            await self._close_auction(a)

    async def _close_auction(self, a: Auction):
        a.phase = Auction.DONE
        self.auctions.pop(a.channel_id, None)
        if not a.current_bidder:
            # No bids — refund nobody (nothing escrowed)
            try:
                await a.message.edit(content="🎪 **Auction ended with no bids.** The clown cries. The box goes back in the van.", view=None)
            except discord.HTTPException:
                pass
            return

        winner = a.current_bidder
        winning_bid = a.current_bid

        # Refund all non-winners' escrows
        for uid, amt in a.escrow.items():
            if uid != winner.id:
                add_coins(a.guild_id, uid, amt)

        # Roll the box contents
        total = sum(w for w, _, _ in BOX_CONTENTS)
        roll = random.uniform(0, total)
        running = 0.0
        mult, flavor = BOX_CONTENTS[-1][1], BOX_CONTENTS[-1][2]
        for w, m, f in BOX_CONTENTS:
            running += w
            if roll <= running:
                mult, flavor = m, f
                break

        payout = int(winning_bid * mult)
        add_coins(a.guild_id, winner.id, payout)
        net = payout - winning_bid

        result_lines = [
            f"🔨 **SOLD** to **{winner.display_name}** for **{winning_bid}** coins.",
            f"The clown yanks the box open:",
            f"{flavor}",
            f"Payout multiplier on winning bid: **{mult:.2f}×** → **{payout}** coins.",
            f"Net for **{winner.display_name}**: **{'+'if net >= 0 else ''}{net}**.",
        ]
        try:
            await a.message.edit(content="\n".join(result_lines), view=None)
        except discord.HTTPException as e:
            logger.error(f"Failed to close auction message: {e}")

    async def _start(self, ctx_or_interaction, starting_bid: int):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild
        channel = ctx_or_interaction.channel
        user = ctx_or_interaction.user if is_slash else ctx_or_interaction.author

        async def reply(content, **kwargs):
            if is_slash:
                await ctx_or_interaction.response.send_message(content, **kwargs)
                return await ctx_or_interaction.original_response()
            return await ctx_or_interaction.send(content, **kwargs)

        if not guild:
            await reply("Server only.")
            return
        if channel.id in self.auctions:
            await reply("An auction is already running in this channel.")
            return
        if starting_bid <= 0:
            await reply("Starting bid must be > 0.")
            return

        a = Auction(guild.id, channel.id, user.id, starting_bid)
        a.deadline = time.time() + INITIAL_SECONDS
        self.auctions[channel.id] = a

        view = AuctionView(self, a)
        msg = await reply(self._render(a), view=view)
        a.message = msg
        a.timer_task = asyncio.create_task(self._auction_timer(a))

    @commands.command(name="auction", aliases=["clownauction", "mysterybox"])
    @commands.guild_only()
    async def auction_prefix(self, ctx, starting_bid: int):
        await self._start(ctx, starting_bid)

    @app_commands.command(name="auction", description="Start a Clown Auction for a mystery box. Anyone can bid.")
    @app_commands.describe(starting_bid="Opening bid — first bidder pays this+increment")
    async def auction_slash(self, interaction: discord.Interaction, starting_bid: int):
        await self._start(interaction, starting_bid)


async def setup(bot):
    await bot.add_cog(ClownAuction(bot))
