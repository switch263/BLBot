"""The Splurge catalog — the economy's deliberate coin sink.

Winning is easy in here; getting rid of money is not. This cog is the outlet:
a wealth-gated catalog (splurges.py) of increasingly deranged purchases that
destroy coins outright. Nothing goes to the house, nothing is minted, nothing
comes back — economy.burn_purchase sends them to the void and records the
trophy in the same transaction.

Two escalators, both in splurges.py:
  * Tiers unlock on total wealth (wallet + bank), so the catalog grows as the
    fortune does — a broke player sees energy drinks, a player near the
    MAX_COINS ceiling sees the option to buy the casino itself.
  * Repeat purchases of the same splurge cost ESCALATION× more each time.

Splurges are purely cosmetic by design — trophies in /flex and nothing else. A
sink that pays out isn't a sink.

Commands: /splurge catalog | buy | flex | bonfire (plus !splurge, !flex,
!bonfire). State: cog_kv namespace "splurge" — `owned:<key>` per item and
`total_burned` lifetime, both written only by economy.burn_purchase.
"""
import discord
from discord.ext import commands
from discord import app_commands
import logging

import economy
import splurges

logger = logging.getLogger(__name__)

_NS = "splurge"
_TOTAL_KEY = "total_burned"
_OWNED_PREFIX = "owned:"

# Discord caps an autocomplete response at 25 entries.
_AC_LIMIT = 25


def _owned_key(key: str) -> str:
    return f"{_OWNED_PREFIX}{key}"


class Splurge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Splurge catalog loaded.")

    # --- shared plumbing ----------------------------------------------------

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

    def _state(self, guild_id: int, user_id: int) -> tuple[dict, int]:
        """(owned counts by splurge key, lifetime burned) for one player."""
        raw = economy.kv_get_all(guild_id, user_id, _NS) or {}
        owned = {
            k[len(_OWNED_PREFIX):]: int(v or 0)
            for k, v in raw.items()
            if k.startswith(_OWNED_PREFIX) and int(v or 0) > 0
        }
        return owned, int(raw.get(_TOTAL_KEY, 0) or 0)

    # --- catalog ------------------------------------------------------------

    async def _catalog(self, ctx_or_interaction, tier: int | None = None):
        guild, user, reply = self._ctx_bits(ctx_or_interaction)
        if guild is None:
            await reply("Server only.", ephemeral=True)
            return
        wealth = economy.get_wealth(guild.id, user.id)
        owned, burned = self._state(guild.id, user.id)
        unlocked = splurges.unlocked_tiers(wealth)

        # Default view: the richest tier they've unlocked — the stuff they came
        # for — rather than a wall of energy drinks they outgrew long ago.
        show = tier if tier in splurges.TIERS else (unlocked[-1] if unlocked else 1)
        rank, rank_emoji = splurges.burn_rank(burned)

        embed = discord.Embed(
            title=f"💸 The Splurge Catalog — Tier {show}: {splurges.tier_name(show)}",
            description=(
                f"Your wealth: **{wealth:,}** • Burned so far: **{burned:,}** "
                f"({rank_emoji} {rank})\n"
                f"Tiers unlocked: **{len(unlocked)}/{len(splurges.TIERS)}**"
            ),
            color=discord.Color.dark_gold(),
        )

        if show not in unlocked:
            need = splurges.tier_requirement(show)
            embed.add_field(
                name="🔒 LOCKED",
                value=(f"{splurges.tier_locked_hint(show)}\n"
                       f"Needs **{need:,}** wealth — you're **{need - wealth:,}** short."),
                inline=False,
            )
        else:
            outstanding = economy.total_house_shares(guild.id)
            for key, entry in splurges.by_tier(show):
                have = owned.get(key, 0)
                cost = splurges.price_for(key, have)
                if key == splurges.SHARES_KEY:
                    value = f"**{cost:,}** coins per share"
                    if outstanding:
                        value += (f" • **{outstanding}** share(s) outstanding"
                                  + (f", **{have}** yours" if have else ""))
                elif splurges.is_unique(key) and have:
                    value = f"~~{entry['price']:,}~~ — **OWNED** (one per customer)"
                else:
                    value = f"**{cost:,}** coins"
                    if have:
                        value += f" • owned ×{have} (price climbs each time)"
                    if splurges.is_unique(key):
                        value += " • one per customer"
                value += f"\n{entry['blurb']}\n*{entry['flavor']}*"
                embed.add_field(name=f"{entry['emoji']} {entry['name']}",
                                value=value, inline=False)

        nxt = splurges.next_tier(wealth)
        footer = "/splurge buy <thing> — coins are destroyed, not spent. "
        if nxt:
            footer += (f"Tier {nxt} ({splurges.tier_name(nxt)}) unlocks at "
                       f"{splurges.tier_requirement(nxt):,} wealth.")
        else:
            footer += "You have unlocked everything. Seek help."
        embed.set_footer(text=footer)
        await reply(embed=embed)

    # --- buying -------------------------------------------------------------

    async def _buy(self, ctx_or_interaction, item_text: str, qty: int = 1):
        guild, user, reply = self._ctx_bits(ctx_or_interaction)
        if guild is None:
            await reply("Server only.", ephemeral=True)
            return
        key = splurges.resolve(item_text or "")
        if key is None:
            await reply(
                f"❓ No such splurge: **{item_text}**. Browse with `/splurge catalog`.",
                ephemeral=True)
            return
        qty = max(1, min(int(qty or 1), 25))
        entry = splurges.SPLURGES[key]

        wealth = economy.get_wealth(guild.id, user.id)
        tier = entry["tier"]
        if tier not in splurges.unlocked_tiers(wealth):
            need = splurges.tier_requirement(tier)
            await reply(
                f"🔒 **{entry['name']}** is Tier {tier} ({splurges.tier_name(tier)}).\n"
                f"{splurges.tier_locked_hint(tier)}\n"
                f"Needs **{need:,}** wealth — you have **{wealth:,}**.",
                ephemeral=True)
            return

        owned, _ = self._state(guild.id, user.id)
        have = owned.get(key, 0)
        if splurges.is_unique(key):
            if have:
                await reply(f"🏆 You already own **{entry['name']}**. "
                            f"One per customer — even for you.", ephemeral=True)
                return
            qty = 1

        # A house share is the one purchase with a mechanical effect: it also
        # credits economy's SHARES_KEY, which is what makes the buyer a
        # shareholder (dividends + the gambling ban).
        buying_shares = key == splurges.SHARES_KEY

        # Price each copy at its own escalated rate, so buying 3 at once costs
        # exactly what buying them one at a time would.
        total = sum(splurges.price_for(key, have + i) for i in range(qty))

        # No special-casing needed for shares: economy.SHARES_KEY IS the
        # `owned:` row this already credits, so buying the item is buying in.
        res = economy.burn_purchase(
            guild.id, user.id, total, _NS,
            [(_owned_key(key), qty), (_TOTAL_KEY, total)])
        if not res.get("ok"):
            if res.get("error") == "broke":
                short = total - res.get("have", 0)
                await reply(
                    f"💸 **{entry['name']}** ×{qty} costs **{total:,}**. "
                    f"You have **{res.get('have', 0):,}** — **{short:,}** short.\n"
                    f"Go win it. That's the whole point.",
                    ephemeral=True)
                return
            await reply("⚠️ The transaction failed. Your coins are safe. Unfortunately.",
                        ephemeral=True)
            return

        burned = res["counters"].get(_TOTAL_KEY, total)
        now_owned = res["counters"].get(_owned_key(key), qty)
        rank, rank_emoji = splurges.burn_rank(burned)

        embed = discord.Embed(
            title=f"{entry['emoji']} {entry['name']}"
                  + (f" ×{qty}" if qty > 1 else ""),
            description=f"{entry['blurb']}\n*{entry['flavor']}*",
            color=discord.Color.dark_gold(),
        )
        embed.add_field(name="Burned", value=f"🔥 **{total:,}** coins", inline=True)
        embed.add_field(name="Balance", value=f"**{res['balance']:,}**", inline=True)
        embed.add_field(name="You now own", value=f"×{now_owned}", inline=True)
        embed.add_field(
            name="Lifetime burned",
            value=f"**{burned:,}** — {rank_emoji} *{rank}*",
            inline=False,
        )
        if buying_shares:
            mine = economy.house_shares(guild.id, user.id)
            outstanding = economy.total_house_shares(guild.id)
            stake = (mine / outstanding * economy.HOUSE_PROFIT_SHARE_PCT * 100
                     if outstanding else 0)
            embed.color = discord.Color.gold()
            embed.add_field(
                name="🏛️ YOU ARE A SHAREHOLDER",
                value=(
                    f"You hold **{mine}** of **{outstanding}** share(s) — "
                    f"**{stake:.1f}%** of house profit, paid out as the house earns it.\n"
                    f"Shareholders split "
                    f"**{int(economy.HOUSE_PROFIT_SHARE_PCT * 100)}%** of profit; "
                    f"the more people buy in, the thinner everyone's slice.\n"
                    f"You are also **permanently barred from gambling here**. "
                    f"You're on the house's side of the table now."
                ),
                inline=False,
            )
        nxt = splurges.next_rank(burned)
        if nxt:
            embed.set_footer(text=f"{nxt[0] - burned:,} more burned to reach {nxt[1]}.")
        else:
            embed.set_footer(text="Top rank. There is nothing left to prove and you proved it anyway.")
        await reply(embed=embed)
        if buying_shares:
            # Landmark event — announce it in the channel, not just to the buyer.
            await reply(f"🏛️ **<@{user.id}> HAS BOUGHT INTO THE HOUSE.** "
                        f"They draw a dividend on house profit now, and they'll "
                        f"never place another bet.")

    # --- trophy case --------------------------------------------------------

    async def _flex(self, ctx_or_interaction, target: discord.Member | None = None):
        guild, user, reply = self._ctx_bits(ctx_or_interaction)
        if guild is None:
            await reply("Server only.", ephemeral=True)
            return
        who = target or user
        owned, burned = self._state(guild.id, who.id)
        rank, rank_emoji = splurges.burn_rank(burned)

        if not owned:
            await reply(
                f"🪙 **{who.display_name}** has never burned a single coin on "
                f"anything fun. A vault with legs. Try `/splurge catalog`.")
            return

        embed = discord.Embed(
            title=f"{rank_emoji} {who.display_name}'s Trophy Case",
            description=f"Lifetime burned: **{burned:,}** coins — *{rank}*",
            color=discord.Color.dark_gold(),
        )
        for tier in sorted(splurges.TIERS):
            lines = [
                f"{splurges.SPLURGES[k]['emoji']} {splurges.SPLURGES[k]['name']}"
                + (f" ×{owned[k]}" if owned[k] > 1 else "")
                for k, _ in splurges.by_tier(tier) if k in owned
            ]
            if lines:
                embed.add_field(name=f"Tier {tier}: {splurges.tier_name(tier)}",
                                value="\n".join(lines), inline=False)
        embed.set_footer(
            text=f"{sum(owned.values())} purchase(s) across "
                 f"{len(owned)} distinct splurge(s). All of it worthless. That's the point.")
        await reply(embed=embed)

    # --- guild leaderboard --------------------------------------------------

    async def _bonfire(self, ctx_or_interaction):
        guild, user, reply = self._ctx_bits(ctx_or_interaction)
        if guild is None:
            await reply("Server only.", ephemeral=True)
            return
        top = economy.kv_top(guild.id, _NS, _TOTAL_KEY, limit=10)
        if not top:
            await reply("🔥 Nobody in this server has burned a coin on purpose. "
                        "A room full of misers. `/splurge catalog`.")
            return
        lines = []
        for i, (uid, total) in enumerate(top, 1):
            member = guild.get_member(uid)
            name = member.display_name if member else f"<@{uid}>"
            rank, rank_emoji = splurges.burn_rank(int(total))
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"**{i}.**")
            lines.append(f"{medal} {name} — **{int(total):,}** {rank_emoji} *{rank}*")
        embed = discord.Embed(
            title="🔥 The Bonfire — Coins Destroyed On Purpose",
            description="\n".join(lines),
            color=discord.Color.dark_gold(),
        )
        embed.set_footer(text="Money that left the economy and is never coming back.")
        await reply(embed=embed)

    # --- prefix commands ----------------------------------------------------

    @commands.command(name="splurge")
    @commands.guild_only()
    async def splurge_prefix(self, ctx, *, args: str = ""):
        """!splurge [tier N | <thing> [qty]] — browse or buy."""
        args = (args or "").strip()
        if not args:
            await self._catalog(ctx)
            return
        parts = args.split()
        if parts[0].lower() == "tier" and len(parts) > 1 and parts[1].isdigit():
            await self._catalog(ctx, int(parts[1]))
            return
        # Trailing integer is a quantity, not part of the name.
        qty = 1
        if len(parts) > 1 and parts[-1].isdigit():
            qty = int(parts[-1])
            parts = parts[:-1]
        await self._buy(ctx, " ".join(parts), qty)

    @commands.command(name="flex")
    @commands.guild_only()
    async def flex_prefix(self, ctx, member: discord.Member = None):
        await self._flex(ctx, member)

    @commands.command(name="bonfire")
    @commands.guild_only()
    async def bonfire_prefix(self, ctx):
        await self._bonfire(ctx)

    # --- slash commands -----------------------------------------------------
    # One /splurge group — subcommands are free against Discord's command cap.

    splurge_group = app_commands.Group(
        name="splurge", description="Burn coins on things you do not need",
        guild_only=True)

    async def _item_autocomplete(self, interaction: discord.Interaction,
                                 current: str) -> list[app_commands.Choice[str]]:
        """Suggest splurges, unlocked ones first — the catalog is far past the
        25-entry cap that static choices allow."""
        try:
            wealth = economy.get_wealth(interaction.guild_id, interaction.user.id)
        except Exception:
            wealth = 0
        unlocked = set(splurges.unlocked_tiers(wealth))
        needle = (current or "").lower()
        matches = [
            (k, v) for k, v in splurges.SPLURGES.items()
            if needle in k.lower() or needle in v["name"].lower()
        ]
        matches.sort(key=lambda kv: (kv[1]["tier"] not in unlocked,
                                     kv[1]["tier"], kv[1]["price"]))
        out = []
        for key, entry in matches[:_AC_LIMIT]:
            lock = "" if entry["tier"] in unlocked else "🔒 "
            label = f"{lock}{entry['name']} — {entry['price']:,}"
            out.append(app_commands.Choice(name=label[:100], value=key))
        return out

    @splurge_group.command(name="catalog", description="Browse things to waste money on")
    @app_commands.describe(tier="Which tier to show (default: the best you've unlocked)")
    async def catalog_slash(self, interaction: discord.Interaction, tier: int = None):
        await self._catalog(interaction, tier)

    @splurge_group.command(name="buy", description="Destroy coins on something useless")
    @app_commands.describe(item="What to waste money on", qty="How many (default 1)")
    @app_commands.autocomplete(item=_item_autocomplete)
    async def buy_slash(self, interaction: discord.Interaction, item: str, qty: int = 1):
        await self._buy(interaction, item, qty)

    @splurge_group.command(name="flex", description="Show off everything you've wasted money on")
    @app_commands.describe(member="Whose trophy case to show (default: yours)")
    async def flex_slash(self, interaction: discord.Interaction,
                         member: discord.Member = None):
        await self._flex(interaction, member)

    @splurge_group.command(name="bonfire", description="Who has destroyed the most coins")
    async def bonfire_slash(self, interaction: discord.Interaction):
        await self._bonfire(interaction)


async def setup(bot):
    await bot.add_cog(Splurge(bot))
