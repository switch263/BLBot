"""Prestige — the all-or-nothing wealth reset gamble.

The one button in the casino that asks for everything you have. Prestige wipes
your entire fortune (wallet + bank) to zero in exchange for a permanent level:
every level multiplies your future winnings (×(1 + level)) but also fattens a
surcharge on what you risk (×(1 + level/4)). The richer you get, the more a
level costs to buy — the threshold to climb FROM your current level is a wealth
gate (economy.prestige_threshold).

The gamble is in the roll, not the price. The wipe IS the cost; there's no
separate charge. On confirm:
  * 2% of the time the house eats everything — your fortune AND your prestige,
    back to level 0, ×1. A total wipe for nothing.
  * Otherwise you leap 1–6 levels in one shot (usually 1), heavily weighted
    toward a single rung but with a long tail that can rocket you up.

Lifetime levels unlocked are banked separately (cog_kv "prestige_lifetime") and
survive a setback and an economy wipe — that's what /legacy ranks.

Commands: /prestige, /legacy (plus !prestige, !legacy). Current level lives in
cog_kv namespace "prestige"/"level"; lifetime count in
"prestige_lifetime"/"levels". All money movement + level changes go through
economy.prestige_buy under one transaction.
"""
import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

import economy

logger = logging.getLogger(__name__)

# The roll that decides a prestige purchase. Kept as a module-level pure
# function (no Discord, no DB) so tests can pin its distribution and clamping.
SETBACK_CHANCE = 0.02
_GAIN_CHOICES = [1, 2, 3, 4, 5, 6]
_GAIN_WEIGHTS = [84, 7, 3, 2, 2, 2]

# Namespaces for the lifetime ledger read by /legacy.
_LIFETIME_NS = "prestige_lifetime"
_LIFETIME_KEY = "levels"

_CONFIRM_TIMEOUT = 60.0


def win_multiplier(level: int) -> int:
    """Winnings multiplier granted by a prestige level: ×(1 + level)."""
    return 1 + level


def surcharge_factor(level: int) -> float:
    """Stake surcharge: ×(1 + level/4) — the cost of carrying the multiplier."""
    return 1 + level / 4


def roll_prestige(level: int, rng: random.Random):
    """Decide the outcome of a prestige purchase.

    Returns (new_level, lifetime_gain, is_setback). A setback (2%) drops the
    player to level 0 and banks no lifetime levels. Otherwise the player gains
    1–6 levels in one roll (heavily weighted toward 1), clamped so the new
    level never exceeds economy.PRESTIGE_MAX_LEVEL; lifetime_gain is the rolled
    gain.
    """
    if rng.random() < SETBACK_CHANCE:
        return 0, 0, True
    gain = rng.choices(_GAIN_CHOICES, weights=_GAIN_WEIGHTS)[0]
    new_level = min(level + gain, economy.PRESTIGE_MAX_LEVEL)
    return new_level, gain, False


class ConfirmPrestige(discord.ui.View):
    """The single confirm button for a prestige purchase. Gated on the invoking
    user; the wipe of their entire fortune is the stated cost."""

    def __init__(self, cog, user_id: int, guild_id: int, level: int, threshold: int):
        super().__init__(timeout=_CONFIRM_TIMEOUT)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.level = level
        self.threshold = threshold
        self.message = None
        self._settled = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This isn't your prestige to gamble.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="WIPE EVERYTHING & PRESTIGE", style=discord.ButtonStyle.danger, emoji="🔥")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._settled:
            await interaction.response.send_message("Already rolled.", ephemeral=True)
            return
        self._settled = True
        for child in self.children:
            child.disabled = True

        gid, uid, level = self.guild_id, self.user_id, self.level
        new_level, lifetime_gain, is_setback = roll_prestige(level, random.Random())

        res = economy.prestige_buy(
            gid, uid,
            threshold=self.threshold,
            new_level=new_level,
            lifetime_gain=lifetime_gain,
        )
        if not res.get("ok"):
            have = res.get("have", 0)
            await interaction.response.edit_message(
                content=(f"💸 You can't afford it anymore — someone moved the goalposts "
                         f"or you spent in between. You need **{self.threshold:,}** wealth, "
                         f"you have **{have:,}**."),
                view=self)
            return

        economy.record_game(gid, uid, "prestige", not is_setback)

        if is_setback:
            embed = discord.Embed(
                title="💀 CATASTROPHE",
                description=(
                    "The house ate your fortune **AND** your prestige.\n"
                    "You are back to **level 0** — win multiplier **×1**.\n"
                    "Everything you built, gone. The 2% came for you."),
                color=discord.Color.dark_red(),
            )
        elif lifetime_gain <= 1:
            n = res.get("new_level", new_level)
            embed = discord.Embed(
                title="✨ ASCENSION",
                description=(
                    f"Your fortune is ash — and you rise.\n"
                    f"You ascend to **level {n}** — win multiplier **×{win_multiplier(n)}**."),
                color=discord.Color.gold(),
            )
        else:
            n = res.get("new_level", new_level)
            embed = discord.Embed(
                title="🚀 JACKPOT ASCENSION",
                description=(
                    f"Your fortune is ash — and you *rocket* upward.\n"
                    f"You leapt **{lifetime_gain} levels** to **level {n}** — "
                    f"win multiplier **×{win_multiplier(n)}**!"),
                color=discord.Color.gold(),
            )
        if not is_setback:
            embed.add_field(
                name="Surcharge",
                value=f"Your stakes now carry **+{int((surcharge_factor(res.get('new_level', new_level)) - 1) * 100)}%**.",
                inline=True)
        embed.set_footer(text="Your wallet and bank are now zero. That was the cost.")
        await interaction.response.edit_message(content=None, embed=embed, view=self)


class Prestige(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Prestige loaded.")

    @staticmethod
    def _ctx_bits(ctx_or_interaction):
        """(guild, user, reply) for either a prefix ctx or a slash interaction."""
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild
        user = ctx_or_interaction.user if is_slash else ctx_or_interaction.author

        async def reply(content=None, **kwargs):
            if not is_slash:
                kwargs.pop("ephemeral", None)
                return await ctx_or_interaction.send(content, **kwargs)
            if ctx_or_interaction.response.is_done():
                return await ctx_or_interaction.followup.send(content, **kwargs)
            return await ctx_or_interaction.response.send_message(content, **kwargs)

        return guild, user, reply

    # --- /prestige ----------------------------------------------------------

    async def _prestige(self, ctx_or_interaction):
        guild, user, reply = self._ctx_bits(ctx_or_interaction)
        if guild is None:
            await reply("Server only.", ephemeral=True)
            return

        gid, uid = guild.id, user.id
        level = economy.prestige_level(gid, uid)
        lifetime = int(economy.kv_get(gid, uid, _LIFETIME_NS, _LIFETIME_KEY, 0) or 0)
        wealth = economy.get_wealth(gid, uid)
        mult = win_multiplier(level)
        surcharge_pct = int((surcharge_factor(level) - 1) * 100)

        embed = discord.Embed(
            title=f"🏅 Prestige — Level {level}",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Win multiplier", value=f"**×{mult}**", inline=True)
        embed.add_field(name="Stake surcharge",
                        value=f"**+{surcharge_pct}%** per level", inline=True)
        embed.add_field(name="Lifetime levels unlocked",
                        value=f"**{lifetime}**", inline=True)

        maxed = level >= economy.PRESTIGE_MAX_LEVEL
        threshold = economy.prestige_threshold(level)

        if maxed or threshold is None:
            embed.add_field(
                name="🔒 MAXED",
                value="You have maxed prestige. There is no level above you.",
                inline=False)
            embed.set_footer(text="Nothing left to ascend to.")
            await reply(embed=embed)
            return

        can_afford = wealth >= threshold
        short = max(0, threshold - wealth)
        embed.add_field(
            name=f"Next level ({level + 1})",
            value=(
                f"Costs your **entire fortune** (wallet + bank, now **{wealth:,}**) "
                f"wiped to **0**.\n"
                f"Gate: **{threshold:,}** wealth — "
                + ("✅ you qualify." if can_afford
                   else f"❌ you're **{short:,}** short.")),
            inline=False)

        if can_afford:
            embed.set_footer(
                text="Confirm to WIPE everything for a prestige level. "
                     "2% of the time it takes your levels too.")
            view = ConfirmPrestige(self, uid, gid, level, threshold)
            msg = await reply(embed=embed, view=view)
            # reply() returns the Message for prefix sends; for slash the first
            # response has no return, so fetch the original.
            if msg is None and isinstance(ctx_or_interaction, discord.Interaction):
                try:
                    msg = await ctx_or_interaction.original_response()
                except discord.HTTPException:
                    msg = None
            view.message = msg
        else:
            embed.set_footer(text="Go win more. Prestige is for the already-rich.")
            await reply(embed=embed)

    # --- /legacy ------------------------------------------------------------

    async def _legacy(self, ctx_or_interaction):
        guild, user, reply = self._ctx_bits(ctx_or_interaction)
        if guild is None:
            await reply("Server only.", ephemeral=True)
            return
        top = economy.kv_top(guild.id, _LIFETIME_NS, _LIFETIME_KEY, limit=10)
        if not top:
            await reply("🏅 Nobody in this server has ever prestiged. "
                        "The ladder is untouched. `/prestige`.")
            return
        lines = []
        for i, (uid, levels) in enumerate(top, 1):
            member = guild.get_member(uid)
            name = member.display_name if member else f"<@{uid}>"
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"**{i}.**")
            lines.append(f"{medal} {name} — **{int(levels):,}** lifetime level(s)")
        embed = discord.Embed(
            title="🏅 The Legacy — Lifetime Prestige",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        embed.set_footer(text="Levels unlocked over a lifetime — they survive every wipe.")
        await reply(embed=embed)

    # --- prefix commands ----------------------------------------------------

    @commands.command(name="prestige")
    @commands.guild_only()
    async def prestige_prefix(self, ctx):
        await self._prestige(ctx)

    @commands.command(name="legacy")
    @commands.guild_only()
    async def legacy_prefix(self, ctx):
        await self._legacy(ctx)

    # --- slash commands -----------------------------------------------------

    @app_commands.command(name="prestige",
                          description="Wipe your entire fortune for a permanent winnings multiplier")
    @app_commands.guild_only()
    async def prestige_slash(self, interaction: discord.Interaction):
        await self._prestige(interaction)

    @app_commands.command(name="legacy", description="Lifetime prestige leaderboard")
    @app_commands.guild_only()
    async def legacy_slash(self, interaction: discord.Interaction):
        await self._legacy(interaction)


async def setup(bot):
    await bot.add_cog(Prestige(bot))
