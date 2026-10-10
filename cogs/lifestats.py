"""/lifestats — a player's live character sheet.

The numbers are the player's *real* economy state, recomputed from the DB on
every call: wealth, play counts, win-rate, favorite game, prestige, splurge
standing and achievements. Nothing on this sheet is stored.

The only bound thing is the portrait: each player gets one randomly-rolled
character image, seeded once and persisted, so the same face comes back forever.
The seed lives in cog_kv (namespace "lifestats", key "char_seed") and is claimed
idempotently — two racing runs can't mint two faces. The image itself is never
cached; it's cheap to redraw from the seed and always matches.

Model for the defer + discord.File flow is cogs/yourmother.py.
"""

import asyncio
import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

import economy
import splurges
import achievements
from character_art import render_character_image

logger = logging.getLogger(__name__)


def _prettify(key: str) -> str:
    """Turn a game key like 'meth_gator' into 'Meth Gator'."""
    return key.replace("_", " ").replace("-", " ").title()


class Lifestats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Lifestats module has been loaded")

    # ---- the bound portrait ------------------------------------------------

    def _char_seed(self, guild_id: int, user_id: int) -> int:
        """The player's permanent character seed — rolled once, reused forever.

        Claim is idempotent: if someone else already wrote a seed (claim returns
        False), we re-read theirs so the face never regenerates."""
        try:
            stored = economy.kv_get(guild_id, user_id, "lifestats", "char_seed")
            if stored is not None:
                return int(stored)
            seed = random.randrange(1, 2**31)
            if economy.kv_claim(guild_id, user_id, "lifestats", "char_seed", seed):
                return seed
            # Lost the race — the first claimer's seed is now authoritative.
            existing = economy.kv_get(guild_id, user_id, "lifestats", "char_seed")
            return int(existing) if existing is not None else seed
        except Exception as e:
            # A broken KV read must never crash the sheet; fall back to a stable
            # per-user seed so the face is at least consistent within the call.
            logger.error("Lifestats seed lookup failed: %s", e)
            return (user_id ^ guild_id) & 0x7FFFFFFF or 1

    async def _render_card(self, display_name: str, seed: int) -> discord.File | None:
        """Draw the portrait off the event loop. None if the render blew up."""
        try:
            buf = await asyncio.to_thread(render_character_image, display_name, seed=seed)
            return discord.File(buf, filename="character.png")
        except Exception as e:
            logger.error("Lifestats render failed, sending embed only: %s", e)
            return None

    # ---- the live stats ----------------------------------------------------

    def _build_embed(self, guild_id: int, target: discord.Member,
                     has_image: bool) -> discord.Embed:
        """Recompute the whole sheet from the DB. Every read is wrapped so
        missing data degrades to a zero default rather than throwing."""

        # Wealth, wallet coins, banked coins.
        try:
            wealth = economy.get_wealth(guild_id, target.id)
        except Exception:
            wealth = 0
        try:
            wallet = economy.get_wallet(guild_id, target.id)
            coins = int(wallet.get("coins", 0))
            total_won = int(wallet.get("total_won", 0))
        except Exception:
            coins, total_won = 0, 0
        try:
            banked = economy.bank_balance(guild_id, target.id)
        except Exception:
            banked = 0

        # Game stats: plays, wins, win-rate, favorite game.
        total_plays = total_wins = 0
        favorite = None
        try:
            stats = economy.get_game_stats(guild_id, target.id) or {}
            for game, rec in stats.items():
                plays = int(rec.get("plays", 0))
                total_plays += plays
                total_wins += int(rec.get("wins", 0))
                if favorite is None or plays > favorite[1]:
                    favorite = (game, plays)
        except Exception:
            pass
        win_rate = (total_wins / total_plays * 100) if total_plays else 0.0
        fav_text = (f"{_prettify(favorite[0])} ({favorite[1]:,} plays)"
                    if favorite and favorite[1] > 0 else "None yet")

        # Prestige: current level, win multiplier, lifetime levels.
        try:
            level = int(economy.prestige_level(guild_id, target.id))
        except Exception:
            level = 0
        try:
            lifetime_levels = int(economy.kv_get(
                guild_id, target.id, "prestige_lifetime", "levels", default=0) or 0)
        except Exception:
            lifetime_levels = 0
        win_mult = 1 + level

        # Splurge tier + burn rank.
        tier_text = splurges.tier_name(0)
        try:
            tiers = splurges.unlocked_tiers(wealth)
            if tiers:
                tier_text = splurges.tier_name(max(tiers))
        except Exception:
            pass
        try:
            total_burned = int(economy.kv_get(
                guild_id, target.id, "splurge", "total_burned", default=0) or 0)
        except Exception:
            total_burned = 0
        try:
            rank_title, rank_emoji = splurges.burn_rank(total_burned)
        except Exception:
            rank_title, rank_emoji = "", ""

        # Achievements: earned / total, points.
        earned_count = 0
        points = 0
        try:
            earned = economy.kv_get_all(guild_id, target.id, "achievements") or {}
            earned_count = len(earned)
            points = sum(achievements.points(a) for a in earned)
        except Exception:
            pass
        try:
            total_achievements = len(achievements.ACHIEVEMENTS)
        except Exception:
            total_achievements = 0

        # Color scales with wealth bracket for a bit of flavor.
        if wealth >= 1_000_000_000:
            color = discord.Color.gold()
        elif wealth >= 1_000_000:
            color = discord.Color.green()
        elif wealth > 0:
            color = discord.Color.blurple()
        else:
            color = discord.Color.light_grey()

        embed = discord.Embed(
            title=f"Character Sheet: {target.display_name}",
            color=color,
        )
        if not has_image:
            embed.set_thumbnail(url=target.display_avatar.url)

        embed.add_field(name="Wealth", value=f"{wealth:,}", inline=True)
        embed.add_field(name="Wallet", value=f"{coins:,}", inline=True)
        embed.add_field(name="Banked", value=f"{banked:,}", inline=True)

        embed.add_field(name="Games Played", value=f"{total_plays:,}", inline=True)
        embed.add_field(name="Wins", value=f"{total_wins:,}", inline=True)
        embed.add_field(name="Win Rate", value=f"{win_rate:.1f}%", inline=True)

        embed.add_field(name="Favorite Game", value=fav_text, inline=True)
        embed.add_field(name="Total Won", value=f"{total_won:,}", inline=True)
        embed.add_field(
            name="Prestige",
            value=f"Level {level} (×{win_mult} wins) · {lifetime_levels:,} lifetime",
            inline=True,
        )

        rank_str = f" · {rank_emoji} {rank_title}".rstrip() if rank_title else ""
        embed.add_field(
            name="Splurge Tier",
            value=f"{tier_text}{rank_str}",
            inline=False,
        )
        embed.add_field(
            name="Achievements",
            value=f"{earned_count}/{total_achievements} · {points:,} pts",
            inline=False,
        )
        return embed

    # ---- shared send -------------------------------------------------------

    async def _do_lifestats(self, ctx_or_interaction, target: discord.Member):
        guild = ctx_or_interaction.guild
        guild_id = guild.id
        seed = self._char_seed(guild_id, target.id)

        is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
        if is_interaction:
            # The render outruns the 3s interaction window — defer first.
            await ctx_or_interaction.response.defer()

        card = await self._render_card(target.display_name, seed)
        embed = self._build_embed(guild_id, target, has_image=card is not None)
        if card is not None:
            embed.set_image(url="attachment://character.png")

        if is_interaction:
            if card is not None:
                await ctx_or_interaction.followup.send(embed=embed, file=card)
            else:
                await ctx_or_interaction.followup.send(embed=embed)
        else:
            if card is not None:
                await ctx_or_interaction.send(embed=embed, file=card)
            else:
                await ctx_or_interaction.send(embed=embed)

    # ---- prefix ------------------------------------------------------------

    @commands.command(name="lifestats")
    @commands.guild_only()
    async def lifestats_prefix(self, ctx, member: discord.Member = None):
        """View a live character sheet. Usage: !lifestats [@user]"""
        await self._do_lifestats(ctx, member or ctx.author)

    # ---- slash -------------------------------------------------------------

    @app_commands.command(name="lifestats",
                          description="View a live character sheet — real stats, a bound portrait")
    @app_commands.describe(member="The user to inspect (defaults to yourself)")
    async def lifestats_slash(self, interaction: discord.Interaction,
                              member: discord.Member = None):
        if interaction.guild is None:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        await self._do_lifestats(interaction, member or interaction.user)


async def setup(bot):
    await bot.add_cog(Lifestats(bot))
