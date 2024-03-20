import discord
from discord.ext import commands
import json
import random
import logging

class BDSMData:
    def __init__(self, file_path):
        # Initialize logger for BDSMData
        self.logger = logging.getLogger(__name__)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
            self.logger.info("BDSM data loaded successfully.")
        except FileNotFoundError as e:
            self.logger.error(f"File not found: {e}")
            self.data = None
        except json.JSONDecodeError as e:
            self.logger.error(f"Error decoding JSON: {e}")
            self.data = None

    def generate_message(self, victim_name):
        if not self.data:
            self.logger.warning("Data not loaded. Cannot generate message.")
            return "Data loading error."

        template = random.choice(self.data["templates"])
        bdsm = random.choice(self.data["parts"]["bdsm"])
        toy = random.choice(self.data["parts"]["toy"])
        trap = random.choice(self.data["parts"]["trap"])

        return template.format(bdsm=bdsm, user=victim_name, toy=toy, trap=trap)

class BDSM(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.bdsm_data = BDSMData("data/bdsm.json")
        self.stats = bot.get_cog('Stats')

    @commands.Cog.listener()
    async def on_ready(self):
        self.logger.info("BDSM cog loaded and ready.")
        try:
            if self.stats:
                self.stats.register_cog("bdsm", ["victim", "offender"])
                self.logger.info("Registering bdsm with stats")
            else:
                self.logger.warning("Stats cog not found.")
        except Exception as e:
            self.logger.error(f"Error registering bdsm with stats: {e}", exc_info=True)

    @commands.command(aliases=['bdsm'])
    async def BDSM(self, ctx, member: discord.Member = None):
        if member:
            victim_mention = member.mention
            message = self.bdsm_data.generate_message(victim_mention)
            await ctx.send(f"{ctx.author.mention} {message}")
            # Call update_stats to track the usage of the BDSM command
            if self.stats:
                await self.stats.update_stats("bdsm", userid=str(ctx.author.id).strip("<!@>"), offender=1)
                await self.stats.update_stats("bdsm", userid=str(member.id).strip("<!@>"), victim=1)
                self.logger.debug("Updating BDSM stats")
            else:
                self.logger.warning("Stats cog not found.")
        else:
            await ctx.send(f"{ctx.author.mention} is pro-pain and pro pro-pain-accessories!")

def setup(bot):
    bot.add_cog(BDSM(bot))

