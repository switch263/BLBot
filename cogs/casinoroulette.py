import discord
from discord.ext import commands
import random
import asyncio
# Import from the root directory economy.py
from economy import get_coins, update_coins 

class CasinoRoulette(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.red_numbers = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
        self.black_numbers = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]

    @commands.command(name="bet")
    async def play_roulette(self, ctx, bet_type: str, amount: int):
        """
        Standard Casino Roulette.
        Usage: !bet [red/black/even/odd/0-36] [amount]
        """
        user_id = str(ctx.author.id)
        current_balance = get_coins(user_id)

        # 1. Validation: No broke-boy behavior
        if amount <= 0:
            return await ctx.send("You trying to bet thin air? Put some real coins up.")
        
        if current_balance < amount:
            return await ctx.send(f"You're too broke. You only have **{current_balance}** coins.")

        # 2. Take the money upfront
        update_coins(user_id, -amount)
        
        bet_type = bet_type.lower()
        winning_number = random.randint(0, 36)
        
        # Determine color for the result message
        if winning_number == 0:
            color = "🟢 GREEN"
        elif winning_number in self.red_numbers:
            color = "🔴 RED"
        else:
            color = "⚫ BLACK"
        
        msg = await ctx.send(f"🎰 **{ctx.author.display_name}** bets **{amount}** on **{bet_type}**... The wheel is spinning!")
        await asyncio.sleep(3)
        
        # 3. Winning Logic
        won = False
        multiplier = 0
        hit_jackpot = False

        # Check for Jackpot hit (Specific 0 or 'green' bet)
        if winning_number == 0:
            if bet_type in ["0", "green"]:
                won, multiplier = True, 35
                hit_jackpot = True
        # Standard bets
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

        # 4. Results and Payouts
        result_msg = f"The ball landed on **{winning_number} ({color})**!"
        
        if won:
            payout = amount * multiplier
            update_coins(user_id, payout)
            
            final_text = f"{result_msg}\n🎉 **WINNER!** You won **{payout}** coins!"
            
            if hit_jackpot:
                # Claim the house pot
                pot_total = get_coins("jackpot_fund")
                update_coins(user_id, pot_total)
                update_coins("jackpot_fund", -pot_total) # Reset pot to 0
                final_text += f"\n💰 **JACKPOT!!** You also claimed the house pot of **{pot_total}** coins!"
            
            await msg.edit(content=f"{final_text}\nNew Balance: **{get_coins(user_id)}**")
        
        else:
            # 10% House tax for the Jackpot fund
            tax = int(amount * 0.10)
            update_coins("jackpot_fund", tax)
            await msg.edit(content=f"{result_msg}\n💀 **L.** House took it all. {tax} added to the !pot.\nBalance: **{get_coins(user_id)}**")

    @commands.command(name="pot")
    async def check_pot(self, ctx):
        """Check the current Jackpot fund."""
        pot = get_coins("jackpot_fund")
        await ctx.send(f"💰 The current Jackpot is **{pot}** coins. Bet on **0** or **green** to claim it!")

async def setup(bot):
    await bot.add_cog(CasinoRoulette(bot))