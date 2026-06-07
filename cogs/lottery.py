import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
import logging

from economy import (
    get_coins, jail_message, transfer_to_house, casino_payout,
    record_game, check_bet,
)

logger = logging.getLogger(__name__)

# Instant-win tickets. Each is a fixed-price "bet": the cost goes to the house
# (transfer_to_house) and any prize is paid from the house (casino_payout), so
# the whole thing rides the standard casino money flow — no minting, memorial
# tithe handled automatically, house solvency respected.
#
# `table` is a weighted prize ladder of (weight, multiplier-of-price). mult 0 is
# a loss; mult 1 is your money back; >1 is profit. Every table's expected return
# is < 1.0 (house edge) — the RTP in each comment is sum(w*m)/sum(w).
TICKETS = {
    "pulltab": {
        "emoji": "🎟️",
        "label": "Pull Tab",
        "price": 1_000,
        "blurb": "Cheap thrills. Peel and pray.",
        # RTP 0.86
        "table": [
            (68, 0), (15, 1), (10, 2), (4, 3), (2, 7), (1, 25),
        ],
    },
    "lucky7": {
        "emoji": "🎫",
        "label": "Lucky 7s Scratcher",
        "price": 10_000,
        "blurb": "Match the sevens, take the bread.",
        # RTP 0.83
        "table": [
            (76, 0), (11, 1), (7, 2), (3, 4), (2, 8), (1, 30),
        ],
    },
    "crossword": {
        "emoji": "🧩",
        "label": "Bonus Crossword",
        "price": 25_000,
        "blurb": "More squares, more stakes.",
        # RTP 0.80
        "table": [
            (74, 0), (12, 1), (7, 2), (4, 3), (2, 7), (1, 28),
        ],
    },
    "diamond": {
        "emoji": "💎",
        "label": "Diamond Jackpot",
        "price": 100_000,
        "blurb": "Long odds, life-changing top prize. Usually a paperweight.",
        # RTP 0.71 — high variance, the 30× jackpot pays 3,000,000.
        "table": [
            (88, 0), (5, 1), (3, 2), (2, 5), (1, 20), (1, 30),
        ],
    },
}

# Prefix-command aliases → canonical key.
_ALIASES = {
    "pull": "pulltab", "tab": "pulltab", "pulltab": "pulltab",
    "lucky": "lucky7", "lucky7": "lucky7", "7s": "lucky7", "sevens": "lucky7",
    "crossword": "crossword", "cross": "crossword", "word": "crossword",
    "diamond": "diamond", "jackpot": "diamond", "dia": "diamond",
}

# Reveal symbols. Losers show a mismatched row; winners show three-of-a-kind
# from the tier matching the prize size.
_LOSE_SYMBOLS = ["🍋", "🔔", "🍒", "⭐", "🍀", "💀", "🪙", "🍉", "🃏"]
_WIN_TIERS = [
    (2, "🍒"),    # small win  (mult < 2)
    (8, "🔔"),    # medium     (mult < 8)
    (10**9, "💎"),  # big / jackpot
]


def _resolve(text: str) -> str | None:
    if not text:
        return None
    return _ALIASES.get(text.strip().lower())


def _reveal_row(mult: float) -> str:
    if mult <= 0:
        picks = random.sample(_LOSE_SYMBOLS, 3)
        return " ".join(picks)
    sym = next(s for cap, s in _WIN_TIERS if mult < cap)
    return f"{sym} {sym} {sym}"


class Lottery(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Lottery / instant tickets loaded.")

    def _pick_mult(self, table):
        total = sum(w for w, _ in table)
        roll = random.uniform(0, total)
        running = 0.0
        for weight, mult in table:
            running += weight
            if roll <= running:
                return mult
        return table[-1][1]

    def _ticket_list(self) -> str:
        lines = ["🎰 **Instant Tickets** — buy with `/scratch` or `!scratch <type>`:\n"]
        for key, t in TICKETS.items():
            top = max(m for _, m in t["table"])
            lines.append(
                f"{t['emoji']} **{t['label']}** (`{key}`) — **{t['price']:,}** coins · "
                f"top prize **{int(t['price'] * top):,}**\n   _{t['blurb']}_"
            )
        return "\n".join(lines)

    async def _play(self, ctx_or_interaction, ticket_key: str):
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

        key = _resolve(ticket_key)
        if not key:
            await reply(
                f"❓ Unknown ticket **{ticket_key}**.\n\n{self._ticket_list()}"
            )
            return

        jmsg = jail_message(guild.id, user.id)
        if jmsg:
            await reply(jmsg)
            return

        ticket = TICKETS[key]
        price = ticket["price"]

        bet_err = check_bet(price)
        if bet_err:
            await reply(bet_err)
            return

        bet_result = transfer_to_house(guild.id, user.id, price)
        if not bet_result.get("ok"):
            if bet_result.get("error") == "broke":
                await reply(
                    f"Too broke for a **{ticket['label']}** (**{price:,}** coins). "
                    f"Balance: **{bet_result.get('have', 0):,}**"
                )
            else:
                await reply("Purchase failed. Try again.")
            return

        mult = self._pick_mult(ticket["table"])
        won = mult > 1

        # Suspense: show the ticket bought, then reveal after a beat.
        msg = await reply(
            f"{ticket['emoji']} **{user.display_name}** buys a **{ticket['label']}** "
            f"for **{price:,}**...\n\n`▒ ▒ ▒`  *scratching...*"
        )

        row = _reveal_row(mult)
        if mult > 0:
            requested = int(price * mult)
            paid = casino_payout(guild.id, user.id, requested)
            short = f" *(house was short — owed {requested:,})*" if paid < requested else ""
            if mult >= 1:
                net = paid - price
                if net > 0:
                    outcome = f"🟢 **WINNER ×{mult:g}** → **+{net:,}** coins!{short}"
                else:
                    outcome = f"⚪ Money back (**×{mult:g}**). Broke even.{short}"
            else:
                outcome = (
                    f"🟡 Partial **×{mult:g}** → got **{paid:,}** back, "
                    f"lost **{price - paid:,}**.{short}"
                )
        else:
            outcome = f"🔴 **No win.** Down **{price:,}**."

        record_game(guild.id, user.id, "lottery", won)

        final = (
            f"{ticket['emoji']} **{ticket['label']}** — {user.display_name}\n\n"
            f"`{row}`\n\n"
            f"{outcome}\n"
            f"Balance: **{get_coins(guild.id, user.id):,}**"
        )
        try:
            await asyncio.sleep(1.3)
            await msg.edit(content=final)
        except discord.HTTPException:
            # If the edit fails, make sure the result still lands.
            await reply(final)

    # ----- play command -----
    @commands.command(name="scratch", aliases=["ticket", "lotto"])
    @commands.guild_only()
    async def scratch_prefix(self, ctx, ticket: str = None):
        if ticket is None:
            await ctx.send(self._ticket_list())
            return
        await self._play(ctx, ticket)

    @app_commands.command(name="scratch", description="Buy an instant-win lottery ticket and scratch it.")
    @app_commands.describe(ticket="Which ticket to buy")
    @app_commands.choices(ticket=[
        app_commands.Choice(name=f"{t['emoji']} {t['label']} — {t['price']:,}", value=key)
        for key, t in TICKETS.items()
    ])
    async def scratch_slash(self, interaction: discord.Interaction, ticket: app_commands.Choice[str]):
        await self._play(interaction, ticket.value)

    # ----- browse command -----
    @commands.command(name="tickets")
    @commands.guild_only()
    async def tickets_prefix(self, ctx):
        await ctx.send(self._ticket_list())

    @app_commands.command(name="tickets", description="List the instant lottery tickets you can buy.")
    async def tickets_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(self._ticket_list())


async def setup(bot):
    await bot.add_cog(Lottery(bot))
