"""Command-usage telemetry — the data behind "which cogs can we archive?"

game_stats covers casino games; this covers EVERYTHING. Two listeners bump a
per-guild counter (+ last-used timestamp) every time any prefix or slash
command completes successfully. Keys are prefix-marked so both invocation
styles are visible: "!roast" and "/roast" count separately.

`!usage` (admin channel only) renders the report: the most-used commands,
busiest cogs, top users, and — the archival shortlist — cogs whose commands
have ALL gone unused since tracking began. `!usage <command>` (e.g.
`!usage /slots` or `!usage roast`) drills into one command's top users.
Tracking starts the first time a command runs after this cog deploys; the
report shows its own start date, so give it a few weeks of data before
swinging the axe.

State: cog_kv namespace "cmdstats": guild rows (user_id=0) hold per-command
totals; per-user rows hold that user's per-command counts plus a "__total__"
key. Namespace "cmdstats_ts" (guild rows) holds last-used epochs and the
"__since__" anchor. Leaderboards come from economy.kv_top.
"""
import time
import logging

import discord
from discord.ext import commands

import economy
from config import ADMIN_CHANNEL_ID

logger = logging.getLogger(__name__)

_NS = "cmdstats"
_TS = "cmdstats_ts"
_TOP_N = 15


class UsageStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Usage stats module has been loaded")

    # ---- collection --------------------------------------------------------

    def _bump(self, guild_id: int, user_id: int, key: str):
        economy.kv_incr(guild_id, 0, _NS, key, 1)          # guild total per command
        economy.kv_incr(guild_id, user_id, _NS, key, 1)    # this user, this command
        economy.kv_incr(guild_id, user_id, _NS, "__total__", 1)  # this user, everything
        now = time.time()
        economy.kv_set(guild_id, 0, _TS, key, now)
        if not economy.kv_get(guild_id, 0, _TS, "__since__", None):
            economy.kv_set(guild_id, 0, _TS, "__since__", now)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        if ctx.guild and ctx.command:
            self._bump(ctx.guild.id, ctx.author.id, "!" + ctx.command.qualified_name)

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command):
        if interaction.guild_id and isinstance(command, discord.app_commands.Command):
            self._bump(interaction.guild_id, interaction.user.id, "/" + command.qualified_name)

    # ---- reporting ---------------------------------------------------------

    def _command_inventory(self) -> dict[str, set[str]]:
        """{cog_name: {tracked keys}} for every loaded cog, both styles."""
        inv: dict[str, set[str]] = {}
        for cog_name, cog in self.bot.cogs.items():
            keys: set[str] = set()
            for c in cog.walk_commands():
                keys.add("!" + c.qualified_name)
            for c in cog.walk_app_commands():
                if isinstance(c, discord.app_commands.Command):
                    keys.add("/" + c.qualified_name)
            if keys:
                inv[cog_name] = keys
        return inv

    @commands.command(name="usage")
    @commands.guild_only()
    async def usage_prefix(self, ctx, *, command: str = ""):
        """Admin: usage report. Bare = overview; `!usage /slots` = that command's top users."""
        if ctx.channel.id != ADMIN_CHANNEL_ID:
            return
        if command:
            await ctx.send(embed=self._command_report(ctx.guild.id, command.strip()))
            return
        counts = {k: int(v) for k, v in economy.kv_get_all(ctx.guild.id, 0, _NS).items()}
        stamps = economy.kv_get_all(ctx.guild.id, 0, _TS)
        since = stamps.get("__since__")

        inv = self._command_inventory()
        cog_totals = {cog: sum(counts.get(k, 0) for k in keys) for cog, keys in inv.items()}

        embed = discord.Embed(title="📊 Command Usage", color=discord.Color.blurple())
        if since:
            embed.description = f"Tracking since <t:{int(float(since))}:D>."
        else:
            embed.description = "No usage recorded yet — tracking starts with the first command."

        top = sorted(counts.items(), key=lambda kv: -kv[1])[:_TOP_N]
        if top:
            lines = []
            for key, n in top:
                ts = stamps.get(key)
                last = f" · last <t:{int(float(ts))}:R>" if ts else ""
                lines.append(f"`{key}` — **{n:,}**{last}")
            embed.add_field(name=f"Most used (top {len(top)})",
                            value="\n".join(lines)[:1024], inline=False)

        busiest = sorted(cog_totals.items(), key=lambda kv: -kv[1])[:10]
        if busiest and busiest[0][1] > 0:
            embed.add_field(
                name="Busiest cogs",
                value="\n".join(f"**{cog}** — {n:,}" for cog, n in busiest if n > 0)[:1024],
                inline=False,
            )

        heaviest = economy.kv_top(ctx.guild.id, _NS, "__total__", limit=10)
        if heaviest:
            embed.add_field(
                name="🎖️ Top users",
                value="\n".join(f"<@{uid}> — **{n:,}** commands" for uid, n in heaviest)[:1024],
                inline=False,
            )

        dead = sorted(cog for cog, total in cog_totals.items() if total == 0)
        if dead:
            embed.add_field(
                name=f"🪦 Untouched cogs ({len(dead)}) — archive candidates",
                value=(", ".join(dead))[:1024],
                inline=False,
            )
        embed.set_footer(text="Counts successful runs only; prefix (!) and slash (/) tracked separately. "
                              "Drill down with !usage <command>.")
        await ctx.send(embed=embed)

    def _command_report(self, guild_id: int, raw: str) -> discord.Embed:
        """Top users for one command. Accepts `/slots`, `!slots`, or bare
        `slots` (bare merges both invocation styles)."""
        if raw.startswith(("!", "/")):
            keys = [raw]
        else:
            keys = ["/" + raw, "!" + raw]
        per_user: dict[int, int] = {}
        total = 0
        for key in keys:
            total += int(economy.kv_get(guild_id, 0, _NS, key, 0) or 0)
            for uid, n in economy.kv_top(guild_id, _NS, key, limit=25):
                per_user[uid] = per_user.get(uid, 0) + n
        embed = discord.Embed(
            title=f"📊 Usage — {' + '.join(f'`{k}`' for k in keys)}",
            color=discord.Color.blurple(),
        )
        if not per_user:
            embed.description = "No recorded uses. Either nobody's run it since tracking began, or that's not a command."
            return embed
        top = sorted(per_user.items(), key=lambda kv: -kv[1])[:10]
        embed.description = f"**{total:,}** total uses since tracking began."
        embed.add_field(
            name="Top users",
            value="\n".join(f"<@{uid}> — **{n:,}**" for uid, n in top)[:1024],
            inline=False,
        )
        return embed


async def setup(bot):
    await bot.add_cog(UsageStats(bot))
