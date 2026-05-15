import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio

# Ensure root is in path for economy import

from economy import (
    get_coins, record_roulette, get_house_state, jail_message,
    transfer_to_house, casino_payout,
    GREEN_JACKPOT_MIN_PCT, GREEN_JACKPOT_MAX_PCT,
    HOUSE_HEIST_MIN_PCT, HOUSE_HEIST_MAX_PCT,
)


class CasinoRoulette(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.red_numbers = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
        self.black_numbers = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]

    # Logic shared by both command types to keep code clean
    async def run_bet(self, ctx_or_interaction, bet_type: str, amount: int):
        # Determine if this is a Prefix context or a Slash interaction
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        
        guild = ctx_or_interaction.guild if not is_slash else ctx_or_interaction.guild
        user = ctx_or_interaction.author if not is_slash else ctx_or_interaction.user

        if not guild:
            msg = "This command can only be used in a server."
            return await ctx_or_interaction.send(msg) if not is_slash else await ctx_or_interaction.response.send_message(msg)

        jmsg = jail_message(guild.id, user.id)
        if jmsg:
            return await ctx_or_interaction.send(jmsg) if not is_slash else await ctx_or_interaction.response.send_message(jmsg)

        if amount <= 0:
            msg = "Bet more than 0, you cheapskate."
            return await ctx_or_interaction.send(msg) if not is_slash else await ctx_or_interaction.response.send_message(msg)

        # Collect the bet atomically into the house pot. If the player is broke,
        # this fails and nothing else happens.
        bet_result = transfer_to_house(guild.id, user.id, amount)
        if not bet_result.get("ok"):
            if bet_result.get("error") == "broke":
                msg = f"You're too broke. Balance: **{bet_result.get('have', 0)}**"
            else:
                msg = "Bet failed. Try again in a moment."
            return await ctx_or_interaction.send(msg) if not is_slash else await ctx_or_interaction.response.send_message(msg)
        bet_type = bet_type.lower()
        winning_number = random.randint(0, 36)
        color = "🟢 GREEN" if winning_number == 0 else ("🔴 RED" if winning_number in self.red_numbers else "⚫ BLACK")
        
        start_msg = f"🎰 **{user.display_name}** bets **{amount}** on **{bet_type}**... Spinning!"
        
        if is_slash:
            await ctx_or_interaction.response.send_message(start_msg)
            # Fetch the message object so we can edit it later
            msg = await ctx_or_interaction.original_response()
        else:
            msg = await ctx_or_interaction.send(start_msg)

        await asyncio.sleep(3)
        
        won = False
        multiplier = 0
        hit_jackpot_shot = False

        if winning_number == 0:
            if bet_type in ["0", "green"]:
                won, multiplier = True, 35
                hit_jackpot_shot = True
        elif bet_type == "red" and winning_number in self.red_numbers:
            won, multiplier = True, 2
        elif bet_type == "black" and winning_number in self.black_numbers:
            won, multiplier = True, 2
        elif bet_type == "even" and winning_number != 0 and winning_number % 2 == 0:
            won, multiplier = True, 2
        elif bet_type == "odd" and winning_number % 2 != 0:
            won, multiplier = True, 2
        elif bet_type.isdigit() and int(bet_type) == winning_number:
            won, multiplier = True, 35

        result_msg = f"The ball landed on **{winning_number} ({color})**!"

        if won:
            winnings = amount * multiplier
            paid = casino_payout(guild.id, user.id, winnings)
            if paid < winnings:
                final_text = (
                    f"{result_msg}\n🎉 **WINNER!** Owed **{winnings:,}** — house only had **{paid:,}**. "
                    f"You got what was there."
                )
            else:
                final_text = f"{result_msg}\n🎉 **WINNER!** You won **{paid:,}** coins!"

            if hit_jackpot_shot:
                on_hand = get_house_state(guild.id)["on_hand"]
                jackpot_pct = random.uniform(GREEN_JACKPOT_MIN_PCT, GREEN_JACKPOT_MAX_PCT)
                jackpot_cap = int(on_hand * jackpot_pct)
                if jackpot_cap > 0:
                    jackpot_paid = casino_payout(guild.id, user.id, jackpot_cap)
                    if jackpot_paid > 0:
                        final_text += (
                            f"\n💰 **JACKPOT!!** You raked **{jackpot_paid:,}** — "
                            f"**{int(round(jackpot_pct * 100))}%** of on-hand. Safe harbor untouched."
                        )
        else:
            # Bet already went to house above; nothing more to do on a loss.
            final_text = f"{result_msg}\n💀 **L.** Your **{amount:,}** is in the pot now."

        record_roulette(guild.id, user.id, won)

        await msg.edit(content=f"{final_text}\nBalance: **{get_coins(guild.id, user.id)}**")

    # --- PREFIX COMMAND ---
    @commands.command(name="bet")
    @commands.guild_only()
    async def bet_prefix(self, ctx, bet_type: str, amount: int):
        await self.run_bet(ctx, bet_type, amount)

    # --- SLASH COMMAND ---
    @app_commands.command(name="bet", description="Bet your hard-earned coins on the roulette wheel")
    @app_commands.describe(bet_type="red, black, even, odd, or a number 0-36", amount="How much you're willing to lose")
    async def bet_slash(self, interaction: discord.Interaction, bet_type: str, amount: int):
        await self.run_bet(interaction, bet_type, amount)

    # --- POT ---
    def _format_pot_message(self, state: dict, slash: bool) -> str:
        prefix = "/" if slash else "!"
        on_hand = state["on_hand"]
        reserve = state["reserve"]
        apr_pct = state["apr"] * 100
        green_lo = int(on_hand * GREEN_JACKPOT_MIN_PCT)
        green_hi = int(on_hand * GREEN_JACKPOT_MAX_PCT)
        heist_lo = int(on_hand * HOUSE_HEIST_MIN_PCT)
        heist_hi = int(on_hand * HOUSE_HEIST_MAX_PCT)
        green_pct_range = f"{int(GREEN_JACKPOT_MIN_PCT*100)}–{int(GREEN_JACKPOT_MAX_PCT*100)}%"
        heist_pct_range = f"{int(HOUSE_HEIST_MIN_PCT*100)}–{int(HOUSE_HEIST_MAX_PCT*100)}%"
        return (
            f"💰 **House Pot**\n"
            f"• **On hand:** **{on_hand:,}** coins — heistable, funds payouts.\n"
            f"• **Safe harbor:** **{reserve:,}** coins — earning **{apr_pct:.2f}% APR**, taps to cover payouts when on-hand runs short.\n"
            f"• **Total net worth:** **{on_hand + reserve:,}**\n\n"
            f"**Ways to bleed the on-hand cash:**\n"
            f"• 🟢 Hit **green** on `{prefix}bet` — random **{green_pct_range}** of on-hand (**{green_lo:,}–{green_hi:,}**).\n"
            f"• 🏦 Rob the house with `{prefix}heist @<bot>` — 1-in-100, random **{heist_pct_range}** of on-hand (**{heist_lo:,}–{heist_hi:,}**)."
        )

    @commands.command(name="pot")
    @commands.guild_only()
    async def pot_prefix(self, ctx):
        state = get_house_state(ctx.guild.id)
        await ctx.send(self._format_pot_message(state, slash=False))

    @app_commands.command(name="pot", description="Show the house pot — on-hand cash vs safe-harbor investments")
    async def pot_slash(self, interaction: discord.Interaction):
        state = get_house_state(interaction.guild_id)
        await interaction.response.send_message(self._format_pot_message(state, slash=True))

async def setup(bot):
    await bot.add_cog(CasinoRoulette(bot))