import discord
from discord.ext import commands
import random
import asyncio
import sys
import os

# Ensure root is in path for economy import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from economy import get_coins, update_wallet, add_coins, deduct_coins

class CasinoRoulette(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.red_numbers = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
        self.black_numbers = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]
        # Use 0 as a reserved ID for the house jackpot fund
        self.JACKPOT_ID = 0

    @commands.command(name="bet")
    async def play_roulette(self, ctx, bet_type: str, amount: int):
        guild_id = ctx.guild.id
        user_id = ctx.author.id
        
        balance = get_coins(guild_id, user_id)

        if amount <= 0:
            return await ctx.send("You can't bet nothing. Stop being weird.")
        
        if balance < amount:
            return await ctx.send(f"You're too broke. Balance: **{balance}**")

        # Deduct upfront using your economy utility
        deduct_coins(guild_id, user_id, amount)
        
        bet_type = bet_type.lower()
        winning_number = random.randint(0, 36)
        color = "🟢 GREEN" if winning_number == 0 else ("🔴 RED" if winning_number in self.red_numbers else "⚫ BLACK")
        
        msg = await ctx.send(f"🎰 **{ctx.author.display_name}** bets **{amount}** on **{bet_type}**... Spinning!")
        await asyncio.sleep(3)
        
        won = False
        multiplier = 0
        hit_jackpot_shot = False

        # Winning Logic
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
            # update_wallet handles coins + stats (spins, total won)
            update_wallet(guild_id, user_id, winnings, is_jackpot=hit_jackpot_shot)
            
            final_text = f"{result_msg}\n🎉 **WINNER!** You won **{winnings}** coins!"
            
            if hit_jackpot_shot:
                pot_total = get_coins(guild_id, self.JACKPOT_ID)
                if pot_total > 0:
                    add_coins(guild_id, user_id, pot_total)
                    deduct_coins(guild_id, self.JACKPOT_ID, pot_total)
                    final_text += f"\n💰 **JACKPOT!!** You also claimed the house pot of **{pot_total}**!"
            
            await msg.edit(content=f"{final_text}\nBalance: **{get_coins(guild_id, user_id)}**")
        else:
            # 10% tax goes to jackpot fund
            tax = int(amount * 0.10)
            add_coins(guild_id, self.JACKPOT_ID, tax)
            # update_wallet with negative delta to track the loss in stats
            update_wallet(guild_id, user_id, 0) # Just to increment the 'spins' stat
            await msg.edit(content=f"{result_msg}\n💀 **L.** {tax} added to the !pot.\nBalance: **{get_coins(guild_id, user_id)}**")

    @commands.command(name="pot")
    async def check_pot(self, ctx):
        pot = get_coins(ctx.guild.id, self.JACKPOT_ID)
        await ctx.send(f"💰 Current Jackpot: **{pot}** coins. Bet on **0** or **green** to win it!")

async def setup(bot):
    await bot.add_cog(CasinoRoulette(bot))