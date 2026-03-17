import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
import logging
import economy

logger = logging.getLogger(__name__)

BULLET_EMOJI = "💀"
SAFE_EMOJI = "😅"
CHAMBER_SIZE = 6
TIMEOUT_DURATION = 60  # seconds to timeout the loser
BUY_IN = 25  # coins per player

CLICK_MESSAGES = [
    "*Click.* {user} survives... for now.",
    "*Click.* Nothing. {user} wipes the sweat off their brow.",
    "*Click.* Empty chamber. {user} exhales.",
    "*Click.* {user} lives to meme another day.",
    "*Click.* The crowd gasps. {user} is still standing.",
    "*Click.* {user} laughs nervously. Still alive.",
]

BANG_MESSAGES = [
    "**BANG!** {user} is down! The crowd goes wild!",
    "**BANG!** {user} has been eliminated! Rest in pepperoni.",
    "**BANG!** {user} didn't make it. F in the chat.",
    "**BANG!** {user} has been sent to the shadow realm!",
    "**BANG!** {user} is out! Should've stayed in bed today.",
    "**BANG!** {user} meets their maker. It was inevitable.",
]

VICTORY_MESSAGES = [
    "{winner} collects the pot of **{pot}** coins! What a legend.",
    "{winner} walks away with **{pot}** coins and their dignity intact!",
    "{winner} survives and pockets **{pot}** coins. Cold blooded.",
    "{winner} is the last one standing! **{pot}** coins richer!",
    "{winner} laughs maniacally while collecting **{pot}** coins!",
]


class RussianRoulette(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}  # channel_id -> game state

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Russian Roulette module has been loaded")

    @commands.command(aliases=['rr'])
    async def roulette(self, ctx):
        """Start or join a Russian Roulette game! Players take turns pulling the trigger."""
        channel = ctx.channel
        guild_id = ctx.guild.id
        author = ctx.author

        # If there's already a game in join phase
        if channel.id in self.active_games:
            game = self.active_games[channel.id]
            if game["phase"] == "joining":
                if author.id in [p.id for p in game["players"]]:
                    await ctx.send(f"{author.mention}, you're already in the game!")
                    return
                # Check coins
                if economy.get_coins(guild_id, author.id) < BUY_IN:
                    await ctx.send(f"{author.mention}, you need at least **{BUY_IN}** coins to play!")
                    return
                economy.deduct_coins(guild_id, author.id, BUY_IN)
                game["players"].append(author)
                game["pot"] += BUY_IN
                await ctx.send(f"{author.mention} joins the roulette! ({len(game['players'])} players, pot: **{game['pot']}** coins)\nType `!roulette` to join. Starter: type `!pull` when ready to begin.")
                return
            else:
                await ctx.send("A game is already in progress in this channel!")
                return

        # Check coins
        if economy.get_coins(guild_id, author.id) < BUY_IN:
            await ctx.send(f"You need at least **{BUY_IN}** coins to play! (Buy-in: **{BUY_IN}**)")
            return

        economy.deduct_coins(guild_id, author.id, BUY_IN)

        # Start new game
        self.active_games[channel.id] = {
            "phase": "joining",
            "players": [author],
            "pot": BUY_IN,
            "guild_id": guild_id,
            "starter": author.id,
        }

        embed = discord.Embed(
            title="Russian Roulette",
            description=(
                f"{author.mention} has started a game of Russian Roulette!\n\n"
                f"Buy-in: **{BUY_IN}** coins per player\n"
                f"Type `!roulette` to join!\n"
                f"{author.display_name}: type `!pull` when everyone is in."
            ),
            color=discord.Color.dark_red()
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def pull(self, ctx):
        """Start the shooting phase of roulette (game starter only)."""
        channel = ctx.channel
        game = self.active_games.get(channel.id)

        if not game or game["phase"] != "joining":
            return

        if ctx.author.id != game["starter"]:
            await ctx.send("Only the person who started the game can begin it!")
            return

        if len(game["players"]) < 2:
            await ctx.send("Need at least 2 players! Waiting for more to `!roulette`...")
            return

        game["phase"] = "playing"
        players = list(game["players"])
        random.shuffle(players)
        pot = game["pot"]
        guild_id = game["guild_id"]

        await ctx.send(f"**The cylinder spins...** {CHAMBER_SIZE} chambers, 1 bullet. {len(players)} players.\nLet's go.")
        await asyncio.sleep(2)

        # Game loop
        turn = 0
        bullet_chamber = random.randint(1, CHAMBER_SIZE)  # Randomly place the bullet at start
        current_shot = 0
        
        while len(players) > 1:
            current = players[turn % len(players)]
            current_shot += 1

            # Safety: if we've gone through all 6 chambers, spin again
            if current_shot > CHAMBER_SIZE:
                await ctx.send("*The cylinder empties and spins again...*")
                await asyncio.sleep(2)
                bullet_chamber = random.randint(1, CHAMBER_SIZE)
                current_shot = 1

            await ctx.send(f"{current.mention} raises the gun... and pulls the trigger...")
            await asyncio.sleep(2)

            if current_shot == bullet_chamber:
                # BANG
                await ctx.send(random.choice(BANG_MESSAGES).format(user=current.mention))

                # Try to timeout
                try:
                    await current.timeout(discord.utils.utcnow() + __import__('datetime').timedelta(seconds=TIMEOUT_DURATION))
                    await ctx.send(f"{current.display_name} has been timed out for {TIMEOUT_DURATION} seconds!")
                except (discord.Forbidden, discord.HTTPException):
                    await ctx.send(f"(Couldn't timeout {current.display_name} - missing permissions)")

                players.remove(current)
                await asyncio.sleep(1)

                if len(players) > 1:
                    remaining = ", ".join(p.display_name for p in players)
                    await ctx.send(f"**{len(players)} players remain:** {remaining}\n*The cylinder spins again...*")
                    await asyncio.sleep(2)
                    # New round - completely restart
                    bullet_chamber = random.randint(1, CHAMBER_SIZE)
                    current_shot = 0
                    turn = 0  # Start from first remaining player
            else:
                await ctx.send(random.choice(CLICK_MESSAGES).format(user=current.mention))
                await asyncio.sleep(1)
                # Only increment turn when player survives
                turn += 1

        # Winner!
        winner = players[0]
        economy.award_coins(guild_id, winner.id, pot)
        await ctx.send(random.choice(VICTORY_MESSAGES).format(winner=winner.mention, pot=pot))

        del self.active_games[channel.id]

    @app_commands.command(name="roulette", description="Start or join a Russian Roulette game!")
    async def roulette_slash(self, interaction: discord.Interaction):
        """Slash command entry point - creates or joins game, then uses prefix flow."""
        channel = interaction.channel
        guild_id = interaction.guild_id
        author = interaction.user

        if channel.id in self.active_games:
            game = self.active_games[channel.id]
            if game["phase"] == "joining":
                if author.id in [p.id for p in game["players"]]:
                    await interaction.response.send_message("You're already in the game!", ephemeral=True)
                    return
                if economy.get_coins(guild_id, author.id) < BUY_IN:
                    await interaction.response.send_message(f"You need at least **{BUY_IN}** coins to play!", ephemeral=True)
                    return
                economy.deduct_coins(guild_id, author.id, BUY_IN)
                game["players"].append(author)
                game["pot"] += BUY_IN
                await interaction.response.send_message(
                    f"{author.mention} joins the roulette! ({len(game['players'])} players, pot: **{game['pot']}** coins)\n"
                    f"Use `/roulette` to join. Starter: type `!pull` when ready."
                )
                return
            else:
                await interaction.response.send_message("A game is already in progress!", ephemeral=True)
                return

        if economy.get_coins(guild_id, author.id) < BUY_IN:
            await interaction.response.send_message(f"You need at least **{BUY_IN}** coins to play! (Buy-in: **{BUY_IN}**)", ephemeral=True)
            return

        economy.deduct_coins(guild_id, author.id, BUY_IN)

        self.active_games[channel.id] = {
            "phase": "joining",
            "players": [author],
            "pot": BUY_IN,
            "guild_id": guild_id,
            "starter": author.id,
        }

        embed = discord.Embed(
            title="Russian Roulette",
            description=(
                f"{author.mention} has started a game of Russian Roulette!\n\n"
                f"Buy-in: **{BUY_IN}** coins per player\n"
                f"Use `!roulette` or `/roulette` to join!\n"
                f"{author.display_name}: type `!pull` when everyone is in."
            ),
            color=discord.Color.dark_red()
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(RussianRoulette(bot))
