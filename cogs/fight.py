import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

logger = logging.getLogger(__name__)


class Fight(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bang = ["BANG", "POW", "SLAM", "WHACK", "SLAP", "KAPOW", "ZAM", "BOOM"]
        self.blow_type = ["devastating", "destructive", "ruthless", "damaging", "ruinous", "catastrophic",
                     "traumatic", "shattering", "overwhelming", "crushing", "fierce", "deadly", "lethal",
                     "fatal", "savage", "violent"]
        self.victory = ["wins", "stands victorious", "triumphs", "conquers", "is the champion", "is the victor"]
        self.blow = ["uppercut", "hammerfist", "elbow strike", "shoulder strike", "front kick", "side kick",
                "roundhouse kick", "knee strike", "butt strike", "headbutt", "haymaker punch", "palm strike",
                "pocket bees"]

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Fight module has been loaded")

    def _generate_fight(self, fighter1: str, fighter2: str) -> str:
        """Generate a fight result message."""
        if random.random() < .5:
            winner, loser = fighter1, fighter2
        else:
            winner, loser = fighter2, fighter1
        return "{}! {}! {}! {} {} over {} with a {} {}.".format(
            random.choice(self.bang), random.choice(self.bang), random.choice(self.bang),
            winner, random.choice(self.victory), loser,
            random.choice(self.blow_type), random.choice(self.blow))

    @commands.command(aliases=['Fight'])
    async def fight(self, ctx, member: discord.Member = None, member2: discord.Member = None):
        fighter1 = member2.mention if member2 else ctx.message.author.mention
        fighter2 = member.mention if member else random.choice(ctx.message.channel.members).mention
        await ctx.send(self._generate_fight(fighter1, fighter2))

    @app_commands.command(name="fight", description="Start a fight between two people")
    @app_commands.describe(opponent="Who to fight", fighter2="Optional second fighter (defaults to you)")
    async def fight_slash(self, interaction: discord.Interaction, opponent: discord.Member, fighter2: discord.Member = None):
        f1 = fighter2.mention if fighter2 else interaction.user.mention
        f2 = opponent.mention
        await interaction.response.send_message(self._generate_fight(f1, f2))


async def setup(bot):
    await bot.add_cog(Fight(bot))
