import discord
from discord.ext import commands
from discord import app_commands
import random
import re
import os
import logging

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data_files")


def _load_lines(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.error(f"Data file not found: {filepath}")
        return []


class BDSM(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.templates = _load_lines(os.path.join(DATA_DIR, "bdsm_templates.txt"))
        self.parts = {
            "bdsm": _load_lines(os.path.join(DATA_DIR, "bdsm_actions.txt")),
            "toy": _load_lines(os.path.join(DATA_DIR, "bdsm_toys.txt")),
            "trap": _load_lines(os.path.join(DATA_DIR, "bdsm_traps.txt")),
        }

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("BDSM module has been loaded")

    def _generate(self, victim_mention: str) -> str:
        """Generate a BDSM scenario string using templates and parts."""
        if not self.templates:
            return "Error: BDSM template data not loaded."

        template = random.choice(self.templates)

        # Replace {part} placeholders with random choices
        def replace_part(match):
            key = match.group(1)
            if key == "user":
                return victim_mention
            part_list = self.parts.get(key)
            if part_list:
                return random.choice(part_list)
            return match.group(0)

        return re.sub(r"\{(.+?)\}", replace_part, template)

    def _generate_bdsm(self, user_mention: str, victim_mention: str = None) -> str:
        if victim_mention:
            return f"{user_mention} {self._generate(victim_mention)}"
        else:
            return f"{user_mention} is pro-pain and pro pro-pain-accessories!"

    @commands.command(name="bdsm", aliases=['BDSM'])
    async def bdsm_cmd(self, ctx, member: discord.Member = None):
        """Generate a BDSM scenario."""
        victim_mention = member.mention if member else None
        await ctx.send(self._generate_bdsm(ctx.author.mention, victim_mention))

    @app_commands.command(name="bdsm", description="Generate a BDSM scenario")
    @app_commands.describe(member="Target of the scenario (optional)")
    async def bdsm_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        victim_mention = member.mention if member else None
        await interaction.response.send_message(self._generate_bdsm(interaction.user.mention, victim_mention))


async def setup(bot):
    await bot.add_cog(BDSM(bot))
