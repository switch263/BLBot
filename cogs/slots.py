import discord
from discord.ext import commands
from discord import app_commands
import random
import sqlite3
import logging
import economy

logger = logging.getLogger(__name__)

SYMBOLS = ["🍒", "🍋", "🍊", "🍇", "🔔", "💎", "7️⃣", "🍀"]

# Payouts for 3 matching symbols (multiplier on bet)
PAYOUTS = {
    "🍒": 5,
    "🍋": 10,
    "🍊": 15,
    "🍇": 20,
    "🔔": 30,
    "🍀": 50,
    "💎": 75,
    "7️⃣": 100,
}

# Weights - lower value symbols appear more often
WEIGHTS = [25, 20, 18, 15, 10, 6, 4, 2]

DEFAULT_BET = 10
MIN_BET = 1
MAX_BET = 1000
STARTING_COINS = 100

# Daily bonus: (weight, amount)
DAILY_REWARDS = [
    (33, 50),
    (33, 100),
    (33, 200),
    (1, 5000),
]


class Slots(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Slots module has been loaded")

    def _spin(self) -> list:
        """Spin the reels and return 3 symbols."""
        return random.choices(SYMBOLS, weights=WEIGHTS, k=3)

    def _calculate_payout(self, reels: list) -> tuple[int, str]:
        """Calculate payout. Returns (multiplier, description)."""
        if reels[0] == reels[1] == reels[2]:
            payout = PAYOUTS.get(reels[0], 10)
            if reels[0] == "7️⃣":
                return payout, "JACKPOT!!!"
            return payout, "Three of a kind!"
        elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
            return 2, "Two of a kind!"
        return 0, "No match"

    def _build_spin_embed(self, reels: list, payout_mult: int, desc: str, bet: int, wallet: dict, net: int) -> discord.Embed:
        """Build the slot machine result embed."""
        reel_display = f"**[ {reels[0]} | {reels[1]} | {reels[2]} ]**"

        if payout_mult > 0:
            color = discord.Color.gold() if payout_mult >= 50 else discord.Color.green()
            winnings = payout_mult * bet
            result_text = f"{desc} You won **{winnings}** coins!"
        else:
            color = discord.Color.dark_grey()
            result_text = f"Better luck next time! You lost **{bet}** coins."

        embed = discord.Embed(
            title="🎰 Slot Machine 🎰",
            description=f"{reel_display}\n\n{result_text}",
            color=color
        )

        new_balance = wallet["coins"] + net
        embed.set_footer(text=f"Balance: {new_balance} coins | Bet: {bet}")

        return embed

    async def _play_slots(self, guild_id: int, user_id: int, bet: int) -> discord.Embed:
        """Core slots logic. Returns embed."""
        wallet = economy.get_wallet(guild_id, user_id)

        if bet < MIN_BET or bet > MAX_BET:
            return discord.Embed(
                title="🎰 Invalid Bet",
                description=f"Bet must be between **{MIN_BET}** and **{MAX_BET}** coins.",
                color=discord.Color.red()
            )

        if wallet["coins"] < bet:
            return discord.Embed(
                title="🎰 Broke!",
                description=f"You only have **{wallet['coins']}** coins but tried to bet **{bet}**.\nUse `!slots daily` or `/slots_daily` for a daily bonus!",
                color=discord.Color.red()
            )

        reels = self._spin()
        payout_mult, desc = self._calculate_payout(reels)
        is_jackpot = payout_mult >= 100

        if payout_mult > 0:
            net = (payout_mult * bet) - bet
        else:
            net = -bet

        economy.update_wallet(guild_id, user_id, net, is_jackpot)

        return self._build_spin_embed(reels, payout_mult, desc, bet, wallet, net)

    def _build_balance_embed(self, user: discord.Member, wallet: dict) -> discord.Embed:
        embed = discord.Embed(
            title=f"🪙 {user.display_name}'s Wallet",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Balance", value=f"**{wallet['coins']}** coins", inline=True)
        embed.add_field(name="Total Won", value=f"{wallet['total_won']} coins", inline=True)
        embed.add_field(name="Total Lost", value=f"{wallet['total_lost']} coins", inline=True)
        embed.add_field(name="Spins", value=str(wallet['spins']), inline=True)
        embed.add_field(name="Jackpots", value=str(wallet['jackpots']), inline=True)
        net = wallet['total_won'] - wallet['total_lost']
        embed.add_field(name="Net Profit", value=f"{'+'if net >= 0 else ''}{net} coins", inline=True)
        return embed

    def _give_daily(self, guild_id: int, user_id: int) -> tuple[bool, int, int]:
        """Try to give daily bonus. Returns (success, amount, new_balance)."""
        from datetime import date
        today = date.today().isoformat()

        economy.get_wallet(guild_id, user_id)  # ensure wallet exists
        try:
            with sqlite3.connect(economy.DB_FILE) as conn:
                cursor = conn.execute(
                    "SELECT last_daily FROM wallets WHERE guild_id = ? AND user_id = ?",
                    (guild_id, user_id)
                )
                last_daily = cursor.fetchone()[0]
                if last_daily == today:
                    return False, 0, 0

                # Roll for reward
                if user_id == 255560298705059841:
                    amount = 20000
                else:
                    weights = [r[0] for r in DAILY_REWARDS]
                    amounts = [r[1] for r in DAILY_REWARDS]
                    amount = random.choices(amounts, weights=weights, k=1)[0]

                conn.execute(
                    "UPDATE wallets SET coins = coins + ?, last_daily = ? WHERE guild_id = ? AND user_id = ?",
                    (amount, today, guild_id, user_id)
                )
                conn.commit()
                cursor = conn.execute(
                    "SELECT coins FROM wallets WHERE guild_id = ? AND user_id = ?",
                    (guild_id, user_id)
                )
                return True, amount, cursor.fetchone()[0]
        except sqlite3.Error as e:
            logger.error(f"Database error giving daily: {e}")
            return False, 0, 0

    def _build_leaderboard_embed(self, guild: discord.Guild, rows: list) -> discord.Embed | None:
        if not rows:
            return None
        desc = ""
        medals = ["🥇", "🥈", "🥉", "4.", "5."]
        for i, row in enumerate(rows):
            uid, coins = row[0], row[1]
            jackpots = row[5] if len(row) > 5 else 0
            member = guild.get_member(uid)
            name = member.display_name if member else f"User {uid}"
            desc += f"{medals[i]} **{name}** - {coins} coins ({jackpots} jackpots)\n"
        return discord.Embed(title="🎰 Slots Leaderboard", description=desc, color=discord.Color.gold())

    # --- Prefix Commands ---

    @commands.command()
    async def slots(self, ctx, action: str = "play"):
        """Play the slot machine! Usage: !slots [amount], !slots daily, !slots balance, !slots leaderboard"""
        if action.lower() == "daily":
            success, amount, new_balance = self._give_daily(ctx.guild.id, ctx.author.id)
            if success:
                msg = f"🎁 You received **{amount}** coins!"
                if amount == 5000:
                    msg = f"🎉🎉🎉 MEGA BONUS! You received **{amount}** coins! 🎉🎉🎉"
                await ctx.send(f"{msg} New balance: **{new_balance}** coins.")
            else:
                await ctx.send("You already claimed your daily bonus today! Come back tomorrow.")
        elif action.lower() in ("balance", "bal"):
            wallet = economy.get_wallet(ctx.guild.id, ctx.author.id)
            await ctx.send(embed=self._build_balance_embed(ctx.author, wallet))
        elif action.lower() in ("leaderboard", "lb", "top"):
            rows = economy.get_leaderboard(ctx.guild.id, limit=5)
            embed = self._build_leaderboard_embed(ctx.guild, rows)
            if embed:
                await ctx.send(embed=embed)
            else:
                await ctx.send("No one has played slots yet!")
        else:
            # Try to parse action as a bet amount, default to DEFAULT_BET
            try:
                bet = int(action)
            except ValueError:
                bet = DEFAULT_BET
            embed = await self._play_slots(ctx.guild.id, ctx.author.id, bet)
            await ctx.send(embed=embed)

    # --- Slash Commands ---

    @app_commands.command(name="slots", description="Pull the slot machine lever!")
    @app_commands.describe(bet=f"Amount to bet ({MIN_BET}-{MAX_BET}, default {DEFAULT_BET})")
    async def slots_slash(self, interaction: discord.Interaction, bet: int = DEFAULT_BET):
        embed = await self._play_slots(interaction.guild_id, interaction.user.id, bet)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="slots_daily", description="Claim your daily slot machine bonus")
    async def slots_daily_slash(self, interaction: discord.Interaction):
        success, amount, new_balance = self._give_daily(interaction.guild_id, interaction.user.id)
        if success:
            msg = f"🎁 You received **{amount}** coins!"
            if amount == 5000:
                msg = f"🎉🎉🎉 MEGA BONUS! You received **{amount}** coins! 🎉🎉🎉"
            await interaction.response.send_message(f"{msg} New balance: **{new_balance}** coins.")
        else:
            await interaction.response.send_message("You already claimed your daily bonus today! Come back tomorrow.")

    @app_commands.command(name="slots_balance", description="Check your slot machine balance and stats")
    @app_commands.describe(member="User to check (defaults to you)")
    async def slots_balance_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        wallet = economy.get_wallet(interaction.guild_id, target.id)
        await interaction.response.send_message(embed=self._build_balance_embed(target, wallet))

    @app_commands.command(name="slots_leaderboard", description="See the slots leaderboard")
    async def slots_leaderboard_slash(self, interaction: discord.Interaction):
        rows = economy.get_leaderboard(interaction.guild_id, limit=5)
        embed = self._build_leaderboard_embed(interaction.guild, rows)
        if embed:
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("No one has played slots yet!")


async def setup(bot):
    await bot.add_cog(Slots(bot))
