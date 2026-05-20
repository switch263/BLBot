"""Shop cog — spend coins on item cards.

Buying destroys the coins (a real money sink); the item lands in the player's
inventory. Items are used via `/use` (Get Out of Jail Free, Loaded Dice),
`/freespin` in the slots cog (Bonus Spin), or passively (Heist Shield, in the
heist cog). The catalog lives in items.py; economy.py stores the inventory.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import economy
from items import (
    ITEMS, ALL_ITEMS, JAIL_CARD, BONUS_SPIN, HEIST_SHIELD, LOADED_DICE,
    item_meta, display, resolve,
)

logger = logging.getLogger(__name__)

# A buy is capped so a fat-fingered qty can't overflow or drain a wallet by
# accident. Plenty for any real purchase.
MAX_BUY_QTY = 100

# Slash-command dropdown of the catalog — keeps players from typo-guessing keys.
_ITEM_CHOICES = [
    app_commands.Choice(name=f"{m['emoji']} {m['name']}", value=key)
    for key, m in ITEMS.items()
]


def _split_item_qty(args: str) -> tuple[str, int]:
    """Parse a prefix-command tail like 'loaded dice 3' into ('loaded dice', 3).
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
        total = m["price"] * qty
        if not economy.try_deduct(guild.id, user.id, total):
            have = economy.get_coins(guild.id, user.id)
            await reply(
                f"Too broke. {m['emoji']} **{m['name']}** ×{qty} costs **{total:,}** "
                f"coins — you have **{have:,}**."
            )
            return
        economy.grant_item(guild.id, user.id, key, qty)
        await reply(
            f"🛒 {user.display_name} bought {m['emoji']} **{m['name']}** ×{qty} for "
            f"**{total:,}** coins. Burned to the void. Use it with "
            f"{'`/freespin`' if key == BONUS_SPIN else '`/use`'} "
            f"{'(auto-triggers when heisted)' if key == HEIST_SHIELD else ''}".strip()
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
        if key == HEIST_SHIELD:
            await reply(
                f"{m['emoji']} A Heist Shield can't be used on demand — it triggers "
                f"automatically the next time someone heists you."
            )
            return

        if key == JAIL_CARD:
            if not economy.consume_item(guild.id, user.id, JAIL_CARD):
                await reply(f"You don't own a {m['emoji']} **{m['name']}**.")
                return
            if not economy.release_from_jail(guild.id, user.id):
                economy.grant_item(guild.id, user.id, JAIL_CARD)  # wasn't needed
                await reply("You're not in jail. Card kept — no sense wasting it.")
                return
            await reply(
                f"🃏 **{user.display_name}** plays a **Get Out of Jail Free** card "
                f"and strolls out of casino jail. The warden is furious."
            )
            return

        if key == LOADED_DICE:
            if not economy.consume_item(guild.id, user.id, LOADED_DICE):
                await reply(f"You don't own a {m['emoji']} **{m['name']}**.")
                return
            result = economy.refund_last_loss(guild.id, user.id)
            if not result.get("ok"):
                economy.grant_item(guild.id, user.id, LOADED_DICE)  # give it back
                err = result.get("error")
                if err == "house_broke":
                    await reply("The house can't cover a refund right now. Loaded Dice kept.")
                else:
                    await reply(
                        "No bet lost in the last 10 minutes to undo. Loaded Dice kept — "
                        "play it right after a loss."
                    )
                return
            await reply(
                f"🎲 **{user.display_name}** rolls the **Loaded Dice** — the last losing "
                f"bet of **{result['refunded']:,}** coins is refunded by the house."
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
            await ctx.send("Usage: `!buy <item> [qty]` — e.g. `!buy loaded dice 2`.")
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
            await ctx.send("Usage: `!use <item>` — e.g. `!use jail` or `!use dice`.")
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
