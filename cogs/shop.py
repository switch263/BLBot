"""Shop cog — spend coins on item cards.

Buying destroys the coins (a real money sink); the item lands in the player's
inventory. Items are used via `/use` (Get Out of Jail Free), `/freespin` in
the slots cog (Bonus Spin), or passively (Heist Shield, in the heist cog).
The catalog lives in items.py; economy.py stores the inventory.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import economy
from items import (
    ITEMS, ALL_ITEMS, JAIL_CARD, BONUS_SPIN, HEIST_SHIELD,
    item_meta, display, resolve,
)

logger = logging.getLogger(__name__)

# A buy is capped so a fat-fingered qty can't overflow or drain a wallet by
# accident. Plenty for any real purchase.
MAX_BUY_QTY = 100

# Heist Shield activation state. Activating stamps today's date here; the shield
# blocks heists for the rest of that calendar day (see cogs/heist.py).
_SHIELD_NS = "heistshield"

# Slash-command dropdown of the catalog — keeps players from typo-guessing keys.
_ITEM_CHOICES = [
    app_commands.Choice(name=f"{m['emoji']} {m['name']}", value=key)
    for key, m in ITEMS.items()
]


def _split_item_qty(args: str) -> tuple[str, int]:
    """Parse a prefix-command tail like 'jail card 3' into ('jail card', 3).
    A trailing integer is the quantity; otherwise quantity defaults to 1."""
    parts = args.rsplit(None, 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0], int(parts[1])
    return args.strip(), 1


class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Shop module has been loaded.")

    # --- shared helpers ----------------------------------------------------
    @staticmethod
    def _ctx_bits(ctx_or_interaction):
        """Return (is_slash, guild, user, reply) for either invocation style."""
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild
        user = ctx_or_interaction.user if is_slash else ctx_or_interaction.author

        async def reply(content=None, **kwargs):
            if is_slash:
                await ctx_or_interaction.response.send_message(content, **kwargs)
                return await ctx_or_interaction.original_response()
            return await ctx_or_interaction.send(content, **kwargs)

        return is_slash, guild, user, reply

    # --- /shop -------------------------------------------------------------
    async def _shop(self, ctx_or_interaction):
        _is_slash, guild, _user, reply = self._ctx_bits(ctx_or_interaction)
        if not guild:
            await reply("Server only.")
            return
        embed = discord.Embed(
            title="🛒 The Shop",
            description="Spend coins on item cards. `/buy` to purchase, `/inventory` to check your stash.",
            color=discord.Color.gold(),
        )
        for key in ALL_ITEMS:
            m = ITEMS[key]
            embed.add_field(
                name=f"{m['emoji']} {m['name']} — {m['price']:,} coins",
                value=f"{m['blurb']}\n*{m['flavor']}*",
                inline=False,
            )
        embed.set_footer(text="Coins spent here are burned — gone for good.")
        await reply(embed=embed)

    # --- /buy --------------------------------------------------------------
    async def _buy(self, ctx_or_interaction, item_text: str, qty: int):
        _is_slash, guild, user, reply = self._ctx_bits(ctx_or_interaction)
        if not guild:
            await reply("Server only.")
            return
        key = resolve(item_text)
        if key is None:
            await reply(f"No such item: **{item_text}**. Try `/shop` to see the catalog.")
            return
        if qty < 1 or qty > MAX_BUY_QTY:
            await reply(f"Quantity must be between 1 and {MAX_BUY_QTY}.")
            return
        m = item_meta(key)

        # Per-item hold cap (e.g. only 3 jail cards / heist shields on hand).
        cap = m.get("max_owned")
        if cap is not None:
            have_now = economy.item_qty(guild.id, user.id, key)
            if have_now + qty > cap:
                room = max(0, cap - have_now)
                await reply(
                    f"🚫 You can only hold **{cap}** {m['emoji']} **{m['name']}** at a time. "
                    f"You have **{have_now}** — room for **{room}** more."
                )
                return

        total = m["price"] * qty
        if not economy.try_deduct(guild.id, user.id, total):
            have = economy.get_coins(guild.id, user.id)
            await reply(
                f"Too broke. {m['emoji']} **{m['name']}** ×{qty} costs **{total:,}** "
                f"coins — you have **{have:,}**."
            )
            return
        economy.grant_item(guild.id, user.id, key, qty)
        if key == BONUS_SPIN:
            how = "Use it with `/freespin`."
        elif key == HEIST_SHIELD:
            how = "Activate it with `/use` to block heists for the rest of the day."
        elif key == JAIL_CARD:
            how = "Have a lawyer play it with `/lawyer freecard` while jailed."
        else:
            how = "Use it with `/use`."
        await reply(
            f"🛒 {user.display_name} bought {m['emoji']} **{m['name']}** ×{qty} for "
            f"**{total:,}** coins. Burned to the void. {how}"
        )

    # --- /inventory --------------------------------------------------------
    async def _inventory(self, ctx_or_interaction):
        _is_slash, guild, user, reply = self._ctx_bits(ctx_or_interaction)
        if not guild:
            await reply("Server only.")
            return
        inv = economy.get_inventory(guild.id, user.id)
        owned = {k: inv.get(k, 0) for k in ALL_ITEMS if inv.get(k, 0) > 0}
        embed = discord.Embed(
            title=f"🎒 {user.display_name}'s Inventory",
            color=discord.Color.blurple(),
        )
        if not owned:
            embed.description = "Empty. Hit `/shop` or open a loot drop."
        else:
            for key, count in owned.items():
                m = ITEMS[key]
                embed.add_field(
                    name=f"{m['emoji']} {m['name']} ×{count}",
                    value=m["blurb"],
                    inline=False,
                )
        await reply(embed=embed)

    # --- /use --------------------------------------------------------------
    async def _use(self, ctx_or_interaction, item_text: str):
        _is_slash, guild, user, reply = self._ctx_bits(ctx_or_interaction)
        if not guild:
            await reply("Server only.")
            return
        key = resolve(item_text)
        if key is None:
            await reply(f"No such item: **{item_text}**.")
            return
        m = item_meta(key)

        if key == BONUS_SPIN:
            await reply(f"{m['emoji']} Use a Bonus Spin with `/freespin` (or `!freespin`).")
            return

        if key == JAIL_CARD:
            await reply(
                f"{m['emoji']} A **Get Out of Jail Free** card isn't played on demand — "
                f"you hand it to a lawyer to play at your hearing. While jailed, run "
                f"`/lawyer freecard` (pays a lawyer's fee, ~98% to walk). One per day."
            )
            return

        if key == HEIST_SHIELD:
            # Activated, not passive: consume one card to raise a shield that
            # blocks EVERY heist against you for the rest of the calendar day.
            today = economy.today_str()
            active = economy.kv_get(guild.id, user.id, _SHIELD_NS, "active_date", "")
            if active == today:
                await reply(
                    f"{m['emoji']} Your Heist Shield is already up for the rest of today — "
                    f"no need to burn another."
                )
                return
            if not economy.consume_item(guild.id, user.id, HEIST_SHIELD):
                await reply(f"You don't own a {m['emoji']} **{m['name']}**.")
                return
            economy.kv_set(guild.id, user.id, _SHIELD_NS, "active_date", today)
            await reply(
                f"🛡️ **{user.display_name}** raises a **Heist Shield**. Every heist "
                f"against you fizzles for the rest of the day. Thieves, despair."
            )
            return

    # --- prefix commands ---------------------------------------------------
    @commands.command(name="shop")
    @commands.guild_only()
    async def shop_prefix(self, ctx):
        await self._shop(ctx)

    @commands.command(name="buy")
    @commands.guild_only()
    async def buy_prefix(self, ctx, *, args: str = ""):
        if not args:
            await ctx.send("Usage: `!buy <item> [qty]` — e.g. `!buy jail card 2`.")
            return
        item_text, qty = _split_item_qty(args)
        await self._buy(ctx, item_text, qty)

    @commands.command(name="inventory", aliases=["inv"])
    @commands.guild_only()
    async def inventory_prefix(self, ctx):
        await self._inventory(ctx)

    @commands.command(name="use")
    @commands.guild_only()
    async def use_prefix(self, ctx, *, item: str = ""):
        if not item:
            await ctx.send("Usage: `!use <item>` — e.g. `!use jail card`.")
            return
        await self._use(ctx, item)

    # --- slash commands ----------------------------------------------------
    @app_commands.command(name="shop", description="Browse the item-card shop")
    async def shop_slash(self, interaction: discord.Interaction):
        await self._shop(interaction)

    @app_commands.command(name="buy", description="Buy an item card from the shop")
    @app_commands.describe(item="Which item to buy", qty="How many (default 1)")
    @app_commands.choices(item=_ITEM_CHOICES)
    async def buy_slash(self, interaction: discord.Interaction,
                        item: app_commands.Choice[str], qty: int = 1):
        await self._buy(interaction, item.value, qty)

    @app_commands.command(name="inventory", description="Show the item cards you own")
    async def inventory_slash(self, interaction: discord.Interaction):
        await self._inventory(interaction)

    @app_commands.command(name="use", description="Use an item card you own")
    @app_commands.describe(item="Which item to use")
    @app_commands.choices(item=_ITEM_CHOICES)
    async def use_slash(self, interaction: discord.Interaction,
                        item: app_commands.Choice[str]):
        await self._use(interaction, item.value)


async def setup(bot):
    await bot.add_cog(Shop(bot))
