import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
import logging

logger = logging.getLogger(__name__)

rekt_list = ['Rekt', 'Really Rekt', 'Tyrannosaurus Rekt', 'Cash4Rekt.com', 'Grapes of Rekt', 'Ship Rekt', 'Rekt markes the spot', 'Caught rekt handed', 'The Rekt Side Story', 'Singin\' In The Rekt', 'Painting The Roses Rekt', 'Rekt Van Winkle', 'Parks and Rekt', 'Lord of the Rekts: The Reking of the King', 'Star Trekt', 'The Rekt Prince of Bel-Air', 'A Game of Rekt', 'Rektflix', 'Rekt it like it\'s hot', 'RektBox 360', 'The Rekt-men', 'School Of Rekt', 'I am Fire, I am Rekt', 'Rekt and Roll', 'Professor Rekt', 'Catcher in the Rekt', 'Rekt-22', 'Harry Potter: The Half-Rekt Prince', 'Great Rektspectations', 'Paper Scissors Rekt', 'RektCraft', 'Grand Rekt Auto V', 'Call of Rekt: Modern Reking 2', 'Legend Of Zelda: Ocarina of Rekt', 'Rekt It Ralph', 'Left 4 Rekt', 'Pokemon: Fire Rekt',
        'The Shawshank Rektemption', 'The Rektfather', 'The Rekt Knight', 'Fiddler on the Rekt', 'The Rekt Files', 'The Good, the Bad, and The Rekt', 'Forrekt Gump', 'The Silence of the Rekts', 'The Green Rekt', 'Gladirekt', 'Spirekted Away', 'Terminator 2: Rektment Day', 'The Rekt Knight Rises', 'The Rekt King', 'REKT-E', 'Citizen Rekt', 'Requiem for a Rekt', 'REKT TO REKT ass to ass', 'Star Wars: Episode VI - Return of the Rekt', 'Braverekt', 'Batrekt Begins', '2001: A Rekt Odyssey', 'The Wolf of Rekt Street', 'Rekt\'s Labyrinth', '12 Years a Rekt', 'Gravirekt', 'Finding Rekt', 'The Arekters', 'There Will Be Rekt', 'Christopher Rektellston', 'Hachi: A Rekt Tale', 'The Rekt Ultimatum', 'Shrekt', 'Rektal Exam', 'Rektium for a Dream', 'The Hunt for Rekt October', 'Oedipus rekt']

COMBO_CHANCE = 0.10  # 10% chance for a combo

COMBO_INTROS = [
    "**WAIT THERE'S MORE—**",
    "**COMBO BREAKER—**",
    "**DOUBLE DOWN—**",
    "**CRITICAL HIT—**",
    "**REKT MULTIPLIER ACTIVATED—**",
    "**THE REKTONING CONTINUES—**",
    "**FATALITY—**",
]


class Rekt(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Rekt module has been loaded")

    async def _send_rekt(self, send_func, followup_func, member_mention: str = None):
        """Core rekt logic with combo support."""
        first = random.choice(rekt_list)
        if member_mention:
            await send_func(f"{member_mention} {first}")
        else:
            await send_func(first)

        # Combo chance
        if random.random() < COMBO_CHANCE:
            combo_count = random.randint(1, 2)
            await asyncio.sleep(1)
            await followup_func(random.choice(COMBO_INTROS))
            for i in range(combo_count):
                await asyncio.sleep(0.8)
                extra = random.choice(rekt_list)
                if member_mention:
                    await followup_func(f"{member_mention} {extra}")
                else:
                    await followup_func(extra)

    @commands.command(aliases=['Rekt'])
    async def rekt(self, ctx, member: discord.Member = None):
        """ Get Riggity Rekt """
        mention = member.mention if member else None
        await self._send_rekt(ctx.send, ctx.send, mention)

    @app_commands.command(name="rekt", description="Get Riggity Rekt")
    @app_commands.describe(member="Person to rekt (optional)")
    async def rekt_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        mention = member.mention if member else None
        await self._send_rekt(interaction.response.send_message, interaction.channel.send, mention)


async def setup(bot):
    await bot.add_cog(Rekt(bot))
