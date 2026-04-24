import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
import sys
import os

# Ensure root is in path for economy import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from economy import get_coins, add_coins, deduct_coins, record_roulette, get_pot, get_house_id, jail_message

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

        balance = get_coins(guild.id, user.id)

        if amount <= 0:
            msg = "Bet more than 0, you cheapskate."
            return await ctx_or_interaction.send(msg) if not is_slash else await ctx_or_interaction.response.send_message(msg)
        
        if balance < amount:
            msg = f"You're too broke. Balance: **{balance}**"
            return await ctx_or_interaction.send(msg) if not is_slash else await ctx_or_interaction.response.send_message(msg)

        # Start the game
        deduct_coins(guild.id, user.id, amount)
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
        
        house_id = get_house_id()
        if won:
            winnings = amount * multiplier
            add_coins(guild.id, user.id, winnings)
            final_text = f"{result_msg}\n🎉 **WINNER!** You won **{winnings}** coins!"

            if hit_jackpot_shot:
                pot_total = get_coins(guild.id, house_id)
                if pot_total > 0:
                    add_coins(guild.id, user.id, pot_total)
                    deduct_coins(guild.id, house_id, pot_total)
                    final_text += f"\n💰 **JACKPOT!!** You also claimed the house pot of **{pot_total}**!"
        else:
            tax = int(amount * 0.10)
            add_coins(guild.id, house_id, tax)
            final_text = f"{result_msg}\n💀 **L.** {tax} added to the !pot."

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
    @commands.command(name="pot")
    @commands.guild_only()
    async def pot_prefix(self, ctx):
        pot = get_pot(ctx.guild.id)
        await ctx.send(f"💰 **Current pot:** **{pot}** coins. Hit 🟢 green on `!bet` to claim it all.")

    @app_commands.command(name="pot", description="Show the current roulette house pot")
    async def pot_slash(self, interaction: discord.Interaction):
        pot = get_pot(interaction.guild_id)
        await interaction.response.send_message(
            f"💰 **Current pot:** **{pot}** coins. Hit 🟢 green on `/bet` to claim it all."
        )

async def setup(bot):
    await bot.add_cog(CasinoRoulette(bot))