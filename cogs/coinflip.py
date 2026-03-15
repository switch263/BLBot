import discord
from discord.ext import commands
from discord import app_commands
from config import DATA_DIR
import os
import random
import sqlite3
import logging

logger = logging.getLogger(__name__)

MIN_BET = 1
MAX_BET = 5000

HEADS_EMOJIS = ["🪙", "👑", "🦅"]
TAILS_EMOJIS = ["🪙", "🏛️", "🔢"]

WIN_MESSAGES = [
    "Lady luck smiles upon you!",
    "Winner winner chicken dinner!",
    "The coin gods are pleased!",
    "Nailed it!",
    "Easy money!",
    "You called it!",
]

LOSE_MESSAGES = [
    "The coin has spoken. Not in your favor.",
    "Better luck next time!",
    "Oof. The coin gods are cruel.",
    "So close, yet so far.",
    "That's rough, buddy.",
    "The house always wins. Wait, there's no house here.",
]


class CoinFlip(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_file = os.path.join(DATA_DIR, "slots.db")

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("CoinFlip module has been loaded")

    def _get_coins(self, guild_id: int, user_id: int) -> int:
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO wallets (guild_id, user_id, coins) VALUES (?, ?, 100)",
                    (guild_id, user_id)
                )
                conn.commit()
                cursor = conn.execute(
                    "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                    (guild_id, user_id)
                )
                return cursor.fetchone()[0]
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return 0

    def _update_coins(self, guild_id: int, user_id: int, delta: int):
        try:
            with sqlite3.connect(self.db_file) as conn:
                if delta > 0:
                    conn.execute(
                        "UPDATE wallets SET coins = coins + ?, total_won = total_won + ? WHERE guild_id = ? AND user_id = ?",
                        (delta, delta, guild_id, user_id)
                    )
                else:
                    conn.execute(
                        "UPDATE wallets SET coins = coins + ?, total_lost = total_lost + ? WHERE guild_id = ? AND user_id = ?",
                        (delta, abs(delta), guild_id, user_id)
                    )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")

    async def _flip(self, guild_id: int, user_id: int, bet: int, call: str) -> discord.Embed:
        call = call.lower()
        if call not in ("heads", "tails", "h", "t"):
            return discord.Embed(description="Pick **heads** or **tails**!", color=discord.Color.red())

        if bet < MIN_BET or bet > MAX_BET:
            return discord.Embed(description=f"Bet must be between **{MIN_BET}** and **{MAX_BET}** coins.", color=discord.Color.red())

        balance = self._get_coins(guild_id, user_id)
        if balance < bet:
            return discord.Embed(description=f"You only have **{balance}** coins!", color=discord.Color.red())

        # Normalize call
        call_full = "heads" if call in ("heads", "h") else "tails"
        result = random.choice(["heads", "tails"])
        won = call_full == result

        result_emoji = random.choice(HEADS_EMOJIS) if result == "heads" else random.choice(TAILS_EMOJIS)

        if won:
            self._update_coins(guild_id, user_id, bet)
            new_bal = balance + bet
            embed = discord.Embed(
                title=f"{result_emoji} {result.upper()}!",
                description=f"You called **{call_full}** and won **{bet}** coins! {random.choice(WIN_MESSAGES)}",
                color=discord.Color.green()
            )
        else:
            self._update_coins(guild_id, user_id, -bet)
            new_bal = balance - bet
            embed = discord.Embed(
                title=f"{result_emoji} {result.upper()}!",
                description=f"You called **{call_full}** and lost **{bet}** coins. {random.choice(LOSE_MESSAGES)}",
                color=discord.Color.red()
            )

        embed.set_footer(text=f"Balance: {new_bal} coins")
        return embed

    @commands.command(aliases=['flip', 'cf'])
    async def coinflip(self, ctx, bet: int = None, call: str = None):
        """Flip a coin! Usage: !coinflip <bet> <heads/tails>"""
        if bet is None or call is None:
            await ctx.send("Usage: `!coinflip 50 heads` or `!cf 100 tails`")
            return
        embed = await self._flip(ctx.guild.id, ctx.author.id, bet, call)
        await ctx.send(embed=embed)

    @app_commands.command(name="coinflip", description="Flip a coin - double or nothing!")
    @app_commands.describe(bet="Amount to bet", call="Heads or tails")
    @app_commands.choices(call=[
        app_commands.Choice(name="Heads", value="heads"),
        app_commands.Choice(name="Tails", value="tails"),
    ])
    async def coinflip_slash(self, interaction: discord.Interaction, bet: int, call: app_commands.Choice[str]):
        embed = await self._flip(interaction.guild_id, interaction.user.id, bet, call.value)
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(CoinFlip(bot))
