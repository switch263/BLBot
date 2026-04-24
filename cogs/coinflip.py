import discord
from discord.ext import commands
from discord import app_commands
import random
import logging
import economy

logger = logging.getLogger(__name__)

MIN_BET = 1

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

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("CoinFlip module has been loaded")

    async def _flip(self, guild_id: int, user_id: int, bet: int, call: str) -> discord.Embed:
        jmsg = economy.jail_message(guild_id, user_id)
        if jmsg:
            return discord.Embed(title="🚔 Jailed", description=jmsg, color=discord.Color.red())

        call = call.lower()
        if call not in ("heads", "tails", "h", "t"):
            return discord.Embed(description="Pick **heads** or **tails**!", color=discord.Color.red())

        if bet < MIN_BET:
            return discord.Embed(description=f"Bet must be at least **{MIN_BET}** coin.", color=discord.Color.red())

        balance = economy.get_coins(guild_id, user_id)
        if balance < bet:
            return discord.Embed(description=f"You only have **{balance}** coins!", color=discord.Color.red())

        # Normalize call
        call_full = "heads" if call in ("heads", "h") else "tails"
        result = random.choice(["heads", "tails"])
        won = call_full == result

        result_emoji = random.choice(HEADS_EMOJIS) if result == "heads" else random.choice(TAILS_EMOJIS)

        if won:
            economy.update_wallet(guild_id, user_id, bet)
            new_bal = balance + bet
            embed = discord.Embed(
                title=f"{result_emoji} {result.upper()}!",
                description=f"You called **{call_full}** and won **{bet}** coins! {random.choice(WIN_MESSAGES)}",
                color=discord.Color.green()
            )
        else:
            economy.update_wallet(guild_id, user_id, -bet)
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
