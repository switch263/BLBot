import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio

from economy import (
    get_coins, record_game, get_house_state, casino_payout,
    GREEN_JACKPOT_MIN_PCT, GREEN_JACKPOT_MAX_PCT,
    HOUSE_HEIST_MIN_PCT, HOUSE_HEIST_MAX_PCT, BOT_HEIST_VAULT_ODDS,
)
from game_common import casino_prelude


class CasinoRoulette(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.red_numbers = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
        self.black_numbers = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]

    # Logic shared by both command types to keep code clean
    async def run_bet(self, ctx_or_interaction, bet_type: str, amount):
        start = await casino_prelude(
            ctx_or_interaction, amount,
            zero_msg="Bet more than 0, you cheapskate.",
            no_guild_msg="This command can only be used in a server.",
        )
        if start is None:
            return
        guild, user, amount = start.guild, start.user, start.bet

        bet_type = bet_type.lower()
        winning_number = random.randint(0, 36)
        color = "🟢 GREEN" if winning_number == 0 else ("🔴 RED" if winning_number in self.red_numbers else "⚫ BLACK")

        start_msg = f"🎰 **{user.display_name}** bets **{amount:,}** on **{bet_type}**... Spinning!"
        msg = await start.reply(start_msg)

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

        record_game(guild.id, user.id, "roulette", won)

        await msg.edit(content=f"{final_text}\nBalance: **{get_coins(guild.id, user.id):,}**")

    # --- PREFIX COMMAND ---
    @commands.command(name="bet")
    @commands.guild_only()
    async def bet_prefix(self, ctx, bet_type: str, amount: str):
        await self.run_bet(ctx, bet_type, amount)

    # --- SLASH COMMAND ---
    @app_commands.command(name="bet", description="Bet your hard-earned coins on the roulette wheel")
    @app_commands.describe(bet_type="red, black, even, odd, or a number 0-36", amount="How much you're willing to lose")
    async def bet_slash(self, interaction: discord.Interaction, bet_type: str, amount: str):
        await self.run_bet(interaction, bet_type, amount)

    # --- POT ---
    def _format_pot_message(self, state: dict, slash: bool, bot_name: str) -> str:
        prefix = "/" if slash else "!"
        vault_odds = round(1 / BOT_HEIST_VAULT_ODDS)
        on_hand = state["on_hand"]
        reserve = state["reserve"]
        apr_pct = state["apr"] * 100
        banked = state.get("banked", 0)
        bank_apr_pct = state.get("bank_apr", 0) * 100
        green_lo = int(on_hand * GREEN_JACKPOT_MIN_PCT)
        green_hi = int(on_hand * GREEN_JACKPOT_MAX_PCT)
        heist_lo = int(on_hand * HOUSE_HEIST_MIN_PCT)
        heist_hi = int(on_hand * HOUSE_HEIST_MAX_PCT)
        green_pct_range = f"{int(GREEN_JACKPOT_MIN_PCT*100)}–{int(GREEN_JACKPOT_MAX_PCT*100)}%"
        heist_pct_range = f"{int(HOUSE_HEIST_MIN_PCT*100)}–{int(HOUSE_HEIST_MAX_PCT*100)}%"
        return (
            f"💰 **House Pot**\n"
            f"• **On hand:** **{on_hand:,}** coins — heistable, funds payouts.\n"
            f"• **Safe harbor:** **{reserve + banked:,}** coins total —\n"
            f"   • house reserve **{reserve:,}** earning **{apr_pct:.2f}% APR** — covers payouts when on-hand runs short, auto-refills from on-hand when tapped.\n"
            f"   • safe-deposit boxes **{banked:,}** of player money earning **{bank_apr_pct:.2f}% APR** (`{prefix}bank`).\n"
            f"• **House net worth:** **{on_hand + reserve:,}**\n\n"
            f"**Ways to bleed the on-hand cash:**\n"
            f"• 🟢 Hit **green** on `{prefix}bet` — random **{green_pct_range}** of on-hand (**{green_lo:,}–{green_hi:,}**).\n"
            f"• 🏦 Rob the house with `{prefix}heist @{bot_name}` — 1-in-{vault_odds}, random **{heist_pct_range}** of on-hand (**{heist_lo:,}–{heist_hi:,}**)."
        )

    def _bot_name(self, guild) -> str:
        me = guild.me if guild else None
        return me.display_name if me else (self.bot.user.name if self.bot.user else "bot")

    @commands.command(name="pot")
    @commands.guild_only()
    async def pot_prefix(self, ctx):
        state = get_house_state(ctx.guild.id)
        await ctx.send(self._format_pot_message(state, slash=False, bot_name=self._bot_name(ctx.guild)))

    @app_commands.command(name="pot", description="Show the house pot — on-hand cash vs safe-harbor investments")
    async def pot_slash(self, interaction: discord.Interaction):
        state = get_house_state(interaction.guild_id)
        await interaction.response.send_message(
            self._format_pot_message(state, slash=True, bot_name=self._bot_name(interaction.guild))
        )

async def setup(bot):
    await bot.add_cog(CasinoRoulette(bot))