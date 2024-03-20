import discord
from discord.ext import commands
import random
import logging


class RektCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.stats = bot.get_cog('Stats')
        self.logger = logging.getLogger(__name__)
        self.rekt_list = [
            '12 Years a Rekt', '2001: A Rekt Odyssey', 'A Game of Rekt', 'Batrekt Begins', 'Braverekt', 'Call of Rekt: Modern Reking 2',
            'Catcher in the Rekt', 'Cash4Rekt.com', 'Christopher Rektellston', 'Citizen Rekt', 'Finding Rekt', 'Fiddler on the Rekt',
            'Forrekt Gump', 'Gladirekt', 'Grapes of Rekt', 'Grand Rekt Auto V', 'Great Rektspectations', 'Gravirekt', 'Hachi: A Rekt Tale',
            'Harry Potter: The Half-Rekt Prince', 'I am Fire, I am Rekt', 'Left 4 Rekt', 'Legend Of Zelda: Ocarina of Rekt', 'Lord of the Rekts: The Reking of the King',
            'Oedipus rekt', 'Painting The Roses Rekt', 'Paper Scissors Rekt', 'Parks and Rekt', 'Pokemon: Fire Rekt', 'Professor Rekt',
            'Rekt', 'Rekt Box 360', 'Rekt It Ralph', 'Rekt TO REKT ass to ass', 'Rekt and Roll', 'Rekt markes the spot', 'Rekt-22',
            'RektCraft', 'RektE', 'Rektflix', 'Rektal Exam', 'Requiem for a Rekt', 'REKT-E', 'REKT TO REKT ass to ass', 'Shrekt',
            'Ship Rekt', 'Singin\' In The Rekt', 'Spirekted Away', 'Star Trekt', 'Star Wars: Episode VI - Return of the Rekt', 'Terminator 2: Rektment Day',
            'The Arekters', 'The Good, the Bad, and The Rekt', 'The Green Rekt', 'The Hunt for Rekt October', 'The Rekt Files', 'The Rekt Knight',
            'The Rekt Knight Rises', 'The Rekt Side Story', 'The Rekt Ultimatum', 'The Rektfather', 'The Shawshank Rektemption', 'The Silence of the Rekts',
            'There Will Be Rekt', 'Tyrannosaurus Rekt'
        ]

        self.rekt_templates = [
            "{user} just got {title}!",
            "{user}, how does it feel to be {title}?"
        ]

    @commands.Cog.listener()
    async def on_ready(self):
        self.logger.info("Rekt module has been loaded")
        try:
            if self.stats:
                self.stats.register_cog("rekt", ["actor", "target"])
            else:
                self.logger.warning("Stats cog not found.")
        except Exception as e:
            self.logger.error(f"Error registering submodule with stats: {e}")

    @commands.command(help="Rekts another user. Example: !rekt <@username>")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def rekt(self, ctx, member: discord.Member = None):
        if not member:
            await ctx.send("You need to specify a user to rekt!")
            return

        title = random.choice(self.rekt_list)
        template = random.choice(self.rekt_templates)
        message = template.format(user=member.mention, title=title)
        await ctx.send(message)

        if self.stats:
            self.logger.info(f"Recording stats for Rekt")
            await self.stats.update_stats("rekt", userid=str(ctx.author.id), actor=1)
            await self.stats.update_stats("rekt", userid=str(member.id), target=1)

def setup(bot):
    bot.add_cog(RektCommand(bot))

