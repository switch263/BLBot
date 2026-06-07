import discord
from discord.ext import commands
from discord import app_commands
import time
import logging

import economy
from achievements import ACHIEVEMENTS, TOTAL_POINTS, points, reward

logger = logging.getLogger(__name__)

NS = "achievements"  # cog_kv namespace: key = achievement id, value = unlock ts


class Achievements(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Achievements loaded.")

    # ----- evaluation -----
    def _ctx(self, guild_id: int, user_id: int) -> dict:
        """Build the stats snapshot every achievement condition reads."""
        w = economy.get_wallet(guild_id, user_id)
        games = economy.get_game_stats(guild_id, user_id)
        inv = economy.get_inventory(guild_id, user_id)
        top = economy.get_leaderboard(guild_id, limit=1)
        rank = 1 if top and top[0][0] == user_id else 0
        return {
            "balance": w["coins"],
            "total_won": w["total_won"],
            "total_lost": w["total_lost"],
            "spins": w["spins"],
            "jackpots": w["jackpots"],
            "games": games,
            "total_plays": sum(g["plays"] for g in games.values()),
            "total_wins": sum(g["wins"] for g in games.values()),
            "distinct_games": len(games),
            "items_owned": len(inv),
            "rank": rank,
        }

    async def _sync(self, guild_id, user, channel):
        """Award any newly-earned achievements for `user` and announce them in
        `channel`. Idempotent — kv_claim makes each award fire exactly once even
        under the per-command listener firing repeatedly."""
        if user.bot or economy.is_memorial(user.id):
            return
        try:
            ctx = self._ctx(guild_id, user.id)
            earned = economy.kv_get_all(guild_id, user.id, NS)
            newly = []
            for aid, a in ACHIEVEMENTS.items():
                if aid in earned:
                    continue
                try:
                    if not a["cond"](ctx):
                        continue
                except Exception as e:
                    logger.error(f"Achievement cond {aid} errored: {e}")
                    continue
                # Claim atomically so a racing command can't double-pay.
                if economy.kv_claim(guild_id, user.id, NS, aid, int(time.time())):
                    rwd = reward(aid)
                    paid = economy.casino_payout(guild_id, user.id, rwd) if rwd > 0 else 0
                    newly.append((aid, a, paid))
        except Exception as e:
            logger.error(f"Achievement sync failed for {user.id}: {e}")
            return

        if not newly or channel is None:
            return
        lines = [f"🏆 **{user.display_name}** unlocked a new achievement!" if len(newly) == 1
                 else f"🏆 **{user.display_name}** unlocked {len(newly)} achievements!"]
        for aid, a, paid in newly:
            reward_note = f" — **+{paid:,}** coins" if paid > 0 else ""
            lines.append(f"{a['emoji']} **{a['name']}** ({points(aid)} pts){reward_note}\n   _{a['desc']}_")
        try:
            await channel.send("\n".join(lines))
        except discord.HTTPException:
            pass

    # ----- listeners: re-sync after ANY command, no per-cog edits needed -----
    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        if ctx.guild:
            await self._sync(ctx.guild.id, ctx.author, ctx.channel)

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command):
        if interaction.guild:
            await self._sync(interaction.guild_id, interaction.user, interaction.channel)

    # ----- display -----
    def _profile_embed(self, guild_id: int, member) -> discord.Embed:
        # Sync-on-view too, so a player who reads their list sees it current.
        earned = economy.kv_get_all(guild_id, member.id, NS)
        got = sum(points(a) for a in earned)
        embed = discord.Embed(
            title=f"🏆 {member.display_name}'s Achievements",
            description=f"**{len(earned)}/{len(ACHIEVEMENTS)}** unlocked · "
                        f"**{got}/{TOTAL_POINTS}** points",
            color=discord.Color.gold(),
        )
        unlocked_lines, locked_lines = [], []
        for aid, a in ACHIEVEMENTS.items():
            if aid in earned:
                unlocked_lines.append(f"{a['emoji']} **{a['name']}** ({points(aid)}) — {a['desc']}")
            else:
                locked_lines.append(f"🔒 {a['emoji']} {a['name']} — {a['desc']}")
        if unlocked_lines:
            embed.add_field(name="✅ Unlocked", value="\n".join(unlocked_lines)[:1024], inline=False)
        if locked_lines:
            embed.add_field(name="🔒 Locked", value="\n".join(locked_lines)[:1024], inline=False)
        return embed

    def _board_embed(self, guild) -> discord.Embed:
        data = economy.kv_all_in_namespace(guild.id, NS)  # {user_id: {id: ts}}
        ranked = []
        for uid, keys in data.items():
            pts = sum(points(k) for k in keys)
            if pts > 0:
                ranked.append((uid, len(keys), pts))
        ranked.sort(key=lambda r: (r[2], r[1]), reverse=True)
        embed = discord.Embed(
            title="🏆 Achievement Leaderboard",
            color=discord.Color.gold(),
        )
        if not ranked:
            embed.description = "Nobody's earned an achievement yet. Be the first!"
            return embed
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, (uid, count, pts) in enumerate(ranked[:10]):
            member = guild.get_member(uid)
            name = member.display_name if member else f"User {uid}"
            tag = medals[i] if i < 3 else f"**{i + 1}.**"
            lines.append(f"{tag} {name} — **{pts}** pts ({count}/{len(ACHIEVEMENTS)})")
        embed.description = "\n".join(lines)
        return embed

    # ----- slash group: /achievements view | top -----
    ach_group = app_commands.Group(name="achievements", description="Track your achievements")

    @ach_group.command(name="view", description="View your (or someone's) achievements")
    @app_commands.describe(member="Whose achievements to view (defaults to you)")
    async def view_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        member = member or interaction.user
        await interaction.response.send_message(embed=self._profile_embed(interaction.guild_id, member))

    @ach_group.command(name="top", description="The achievement leaderboard")
    async def top_slash(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        await interaction.response.send_message(embed=self._board_embed(interaction.guild))

    # ----- prefix: !achievements [top | @member] -----
    @commands.command(name="achievements", aliases=["ach", "achievement"])
    @commands.guild_only()
    async def ach_prefix(self, ctx, *, arg: str = None):
        if arg and arg.strip().lower() in ("top", "leaderboard", "lb", "board"):
            await ctx.send(embed=self._board_embed(ctx.guild))
            return
        member = ctx.message.mentions[0] if ctx.message.mentions else ctx.author
        await ctx.send(embed=self._profile_embed(ctx.guild.id, member))


async def setup(bot):
    await bot.add_cog(Achievements(bot))
