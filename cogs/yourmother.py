"""/yourmother — 1,300+ hand-written yo-mama combos, often illustrated.

The jokes live in yomama.py (repo root, pure data) and the portrait renderer in
yomama_art.py, so this file is only the Discord plumbing. Not a game — no
prelude, nothing recorded — but like /roast it isn't free: YOURMOTHER_FEE goes
into the house pot for every delivered joke.

When a joke arrives as art, the art plays the joke: the category is plumbed
into the renderer, which draws the mother to match — a "fat" mama is drawn
wide, a "tall" mama long, a "nasty" mama green and buzzing with flies.
"""

import asyncio
import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

import yomama
from economy import is_memorial, prestige_surcharge
from game_common import charge_fee, fee_trailer
from yomama_art import render_joke_image

logger = logging.getLogger(__name__)

# How often a joke arrives as a commissioned oil painting instead of text.
# The portrait is drawn to match the category — a different disaster every
# time — and the fee is the same whether the joke ships as pixels or words.
IMAGE_CHANCE = 0.30

# Flat fee per delivered joke, paid into the house pot. The memorial refusal
# is free; a broke joker pays nothing and gets roasted for being poor instead.
YOURMOTHER_FEE = 100_000

MEMORIAL_RESPONSES = [
    "His mother raised a legend. Pick someone else. o7",
]

# Shown above the drawing so the render reads as a bit, not a glitch.
ART_INTROS = [
    "I had this commissioned:",
    "Forensics provided a sketch:",
    "The gallery sent over the piece:",
    "Attached: the only known likeness.",
    "I hired an artist. He's still in therapy.",
    "Evidence submitted to the court:",
]


class YourMother(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Your Mother module loaded (%d combos).", yomama.combo_count())

    # ---- shared logic -----------------------------------------------------

    def _joke_for(self, guild_id: int, joker_id: int, target: discord.abc.User,
                  category: str | None) -> tuple[str, str, str, str] | str:
        """(chat text, caption text, art flavor) for a paid joke, or the plain
        refusal string to send instead (memorial target: free; broke joker:
        unpaid).

        Chat gets the mention so Discord renders it as a name; the portrait
        gets the display name, since the renderer would draw a raw `<@id>`.
        The flavor is the joke's actual category — the renderer draws the
        mother to match it.
        """
        if is_memorial(target.id):
            return random.choice(MEMORIAL_RESPONSES)
        refusal = charge_fee(guild_id, joker_id, YOURMOTHER_FEE, "A joke about someone's mother")
        if refusal:
            return refusal
        flavor, body = yomama.joke_with_category(category)
        receipt = fee_trailer(prestige_surcharge(guild_id, joker_id, YOURMOTHER_FEE))
        return f"{target.mention} {body}", f"{target.display_name} {body}", flavor, receipt

    async def _render(self, joke_text: str, flavor: str) -> discord.File | None:
        """Draw the joke off the event loop with the portrait matched to its flavor.
        None if rendering blew up."""
        try:
            buf = await asyncio.to_thread(render_joke_image, joke_text, flavor)
            return discord.File(buf, filename="yourmother.png")
        except Exception as e:
            # A busted render must never eat the joke — fall back to text.
            logger.error("Your Mother render failed, sending text only: %s", e)
            return None

    # ---- prefix -----------------------------------------------------------

    @commands.command(name="yourmother", aliases=["yomama", "yomomma", "urmom"])
    @commands.guild_only()
    async def yourmother_prefix(self, ctx, *, arg: str = ""):
        """`!yomama @someone fat` — both parts optional, in any order. Costs 100k."""
        target = ctx.message.mentions[0] if ctx.message.mentions else ctx.author
        category = next((w.lower() for w in arg.split()
                         if w.lower() in yomama.CATEGORIES), None)
        result = self._joke_for(ctx.guild.id, ctx.author.id, target, category)
        if isinstance(result, str):
            await ctx.send(result)
            return
        joke, caption, flavor, receipt = result

        if random.random() < IMAGE_CHANCE:
            async with ctx.typing():
                card = await self._render(caption, flavor)
            if card is not None:
                await ctx.send(f"{joke}\n*{random.choice(ART_INTROS)}*{receipt}", file=card)
                return
        await ctx.send(joke + receipt)

    # ---- slash ------------------------------------------------------------

    @app_commands.command(name="yourmother",
                          description=f"A joke about someone's mother. 1,300+ of them. {YOURMOTHER_FEE:,} coins.")
    @app_commands.describe(member="Whose mother (leave empty to insult your own)",
                           category="Pick the flavor, or leave it to chance")
    @app_commands.choices(category=[
        app_commands.Choice(name=name, value=name) for name in yomama.category_names()
    ])
    async def yourmother_slash(self, interaction: discord.Interaction,
                               member: discord.Member = None,
                               category: app_commands.Choice[str] = None):
        if interaction.guild is None:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        target = member or interaction.user
        result = self._joke_for(interaction.guild.id, interaction.user.id, target,
                                category.value if category else None)
        if isinstance(result, str):
            await interaction.response.send_message(result)
            return
        joke, caption, flavor, receipt = result

        if random.random() < IMAGE_CHANCE:
            # Rendering outruns the 3s interaction window on a slow host.
            await interaction.response.defer()
            card = await self._render(caption, flavor)
            if card is not None:
                await interaction.followup.send(
                    f"{joke}\n*{random.choice(ART_INTROS)}*{receipt}", file=card)
            else:
                await interaction.followup.send(joke + receipt)
            return
        await interaction.response.send_message(joke + receipt)


async def setup(bot):
    await bot.add_cog(YourMother(bot))
