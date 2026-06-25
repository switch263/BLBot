"""Weekly winnings tax — the economy's primary coin sink.

An income tax on NET winnings. Once a week the bot assesses WINNINGS_TAX_PCT of
each player's net gambling profit since the previous levy (their net_won now
minus the snapshot taken last week) and posts a single notice to #game-spam.
net_won is payouts minus stakes, so a break-even or losing week nets <= 0 and
owes nothing — only coins you actually came out ahead on are taxed. (This
replaced an older GROSS basis that counted returned stakes too, which let
churn inflate a bill past the player's wallet.) Players have 24h to `/paytax`;
the coins flow to the house on-hand (a closed loop, not burned). Miss the
deadline and you're a tax evader: jailed and your wallet is forfeited.

All state lives in economy's cog_kv store (namespace "tax"), so the levy/
collect/enforce cycle survives restarts:
  guild-scoped (user_id=0):  last_levy_ts, due_ts  (due_ts == 0 -> idle)
                             schema_v  (migration guard; see _migrate_once)
  per-user:                  net_base  (net_won snapshot at the last levy)
                             owed  (the locked bill; deleted once paid)

All tuning knobs (rate, period, grace, jail length, channel) live in economy.py.
"""
import time
import logging

import discord
from discord.ext import commands, tasks
from discord import app_commands

import economy
from config import ADMIN_CHANNEL_ID

logger = logging.getLogger(__name__)

_NS = "tax"
_MAX_LIST = 30  # cap how many bills/evaders we spell out in one message
# Bump to force _migrate_once to clear stale bill state on next loop. v2 = the
# gross→net winnings basis change.
_SCHEMA_VERSION = 2


class Taxes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tax_loop.start()

    def cog_unload(self):
        self.tax_loop.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Taxes module has been loaded")

    # --- state helpers ----------------------------------------------------

    def _guild_state(self, guild_id: int) -> tuple[float, float]:
        last = economy.kv_get(guild_id, 0, _NS, "last_levy_ts", 0) or 0
        due = economy.kv_get(guild_id, 0, _NS, "due_ts", 0) or 0
        return float(last), float(due)

    def _owed(self, guild_id: int, user_id: int) -> int:
        return int(economy.kv_get(guild_id, user_id, _NS, "owed", 0) or 0)

    def _find_channel(self, guild: discord.Guild):
        """Resolve the announcement channel: #game-spam by name, then the
        configured admin channel, then the guild system channel."""
        ch = discord.utils.get(guild.text_channels, name=economy.TAX_CHANNEL_NAME)
        if ch:
            return ch
        ch = guild.get_channel(ADMIN_CHANNEL_ID)
        if isinstance(ch, discord.TextChannel):
            return ch
        return guild.system_channel

    # --- the weekly cycle -------------------------------------------------

    @tasks.loop(minutes=30)
    async def tax_loop(self):
        now = time.time()
        for guild in list(self.bot.guilds):
            try:
                self._migrate_once(guild)
                last, due = self._guild_state(guild.id)
                if due > 0:
                    # A collection window is open — enforce once it lapses.
                    if now >= due:
                        await self._enforce(guild, now)
                elif last <= 0:
                    # First sighting of this guild: anchor the clock and seed
                    # everyone's baseline so the first levy lands a full period
                    # out and taxes only growth from here on.
                    self._seed_baselines(guild)
                    economy.kv_set(guild.id, 0, _NS, "last_levy_ts", now)
                elif now - last >= economy.TAX_PERIOD_SECONDS:
                    await self._levy(guild, now)
            except Exception as e:
                logger.error(f"tax_loop failed for guild {guild.id}: {e}")

    @tax_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    def _migrate_once(self, guild: discord.Guild):
        """One-time cleanup when the tax basis changed from gross winnings
        (total_won) to net winnings (net_won). The old basis over-charged players
        — churned coins inflated the bill past their wallet. Clear the transient
        bill state (every open `owed` plus the due window) so nobody is enforced
        on a stale, inflated bill. Offense/streak history is preserved.
        Baselines re-seed lazily: _levy now reads the new `net_base` key, so the
        first levy after this taxes nothing and starts the clock fresh."""
        ver = int(economy.kv_get(guild.id, 0, _NS, "schema_v", 0) or 0)
        if ver >= _SCHEMA_VERSION:
            return
        economy.kv_set(guild.id, 0, _NS, "due_ts", 0)  # close any open window
        house_id = economy.get_house_id()
        for uid, _coins in economy.get_all_wallets(guild.id):
            if uid == house_id:
                continue
            economy.kv_delete(guild.id, uid, _NS, "owed")
        economy.kv_set(guild.id, 0, _NS, "schema_v", _SCHEMA_VERSION)
        logger.info("taxes: migrated guild %s to net-winnings basis; "
                    "cleared stale bills.", guild.id)

    def _seed_baselines(self, guild: discord.Guild):
        """Record everyone's current net-winnings counter as their starting
        baseline, so the first levy taxes only what they net after this point."""
        house_id = economy.get_house_id()
        for uid, net in economy.get_all_net_winnings(guild.id):
            if uid == house_id or economy.is_memorial(uid):
                continue
            economy.kv_set(guild.id, uid, _NS, "net_base", net)

    async def _levy(self, guild: discord.Guild, now: float):
        """Assess each player's NET winnings since their baseline, lock the
        bills, roll baselines forward, open the 24h window, and announce. A
        break-even or losing week nets <= 0, so nothing is owed."""
        house_id = economy.get_house_id()
        bills: list[tuple[int, int]] = []
        for uid, net in economy.get_all_net_winnings(guild.id):
            if uid == house_id or economy.is_memorial(uid):
                continue
            base = economy.kv_get(guild.id, uid, _NS, "net_base", None)
            # New player with no baseline yet: start the clock, tax nothing.
            base = net if base is None else int(base)
            economy.kv_set(guild.id, uid, _NS, "net_base", net)  # roll forward
            winnings = net - base
            owed = int(winnings * economy.WINNINGS_TAX_PCT) if winnings > 0 else 0
            if owed <= 0:
                economy.kv_delete(guild.id, uid, _NS, "owed")
                continue
            economy.kv_set(guild.id, uid, _NS, "owed", owed)
            bills.append((uid, owed))

        economy.kv_set(guild.id, 0, _NS, "last_levy_ts", now)

        # Nobody had taxable winnings — no collection window, no notice.
        if not bills:
            return

        due = now + economy.TAX_GRACE_SECONDS
        economy.kv_set(guild.id, 0, _NS, "due_ts", due)
        bills.sort(key=lambda b: b[1], reverse=True)
        await self._announce_levy(guild, bills, int(due))

    async def _announce_levy(self, guild, bills, due_ts):
        pct = int(economy.WINNINGS_TAX_PCT * 100)
        lines = [f"<@{uid}> owes **{owed:,}**" for uid, owed in bills[:_MAX_LIST]]
        if len(bills) > _MAX_LIST:
            lines.append(f"…and **{len(bills) - _MAX_LIST}** more.")
        embed = discord.Embed(
            title="🧾 TAX DAY",
            description=(
                f"The house is collecting its **{pct}%** weekly tax on every "
                f"coin you **won** this week — locked in as of right now. Doesn't "
                f"matter if you lost it all back; if you won it, it's taxed. Won "
                f"nothing? You owe nothing.\n\n"
                f"Pay with **`/paytax`** before <t:{due_ts}:R> (deadline "
                f"<t:{due_ts}:f>).\n"
                f"**Miss it and the house seizes your bill plus a cut of your "
                f"wallet, and you go to jail.** Repeat offenders lose more — and "
                f"no Get Out of Jail Free card springs them. This is your only "
                f"reminder.\n\n"
                + "\n".join(lines)
            ),
            color=discord.Color.dark_gold(),
        )
        ch = self._find_channel(guild)
        if ch is None:
            logger.warning(f"No tax channel for guild {guild.id}; levy unposted.")
            return
        # Ping the debtors in content so the notice actually reaches them.
        mentions = " ".join(f"<@{uid}>" for uid, _ in bills[:_MAX_LIST])
        try:
            await ch.send(content=f"🧾 **Tax day!** {mentions}".strip(), embed=embed)
        except discord.HTTPException as e:
            logger.error(f"Failed to post tax levy in guild {guild.id}: {e}")

    async def _enforce(self, guild: discord.Guild, now: float):
        """Round up everyone who still owes. Graduated penalty: the unpaid bill
        plus a wallet cut (25% first offense, 50% repeat), capped at wallet,
        plus jail (48h first / 72h repeat, repeat sentences card-proof)."""
        house_id = economy.get_house_id()
        ch = self._find_channel(guild)
        channel_id = ch.id if ch else 0
        evaders: list[tuple[int, int, int]] = []  # (uid, seized, offense_level)
        for uid, _coins in economy.get_all_wallets(guild.id):
            if uid == house_id or economy.is_memorial(uid):
                continue
            owed = self._owed(guild.id, uid)
            if owed <= 0:
                continue

            # Escalate the offense level; missing resets any decay progress.
            offense = int(economy.kv_get(guild.id, uid, _NS, "offenses", 0) or 0) + 1
            economy.kv_set(guild.id, uid, _NS, "offenses", offense)
            economy.kv_set(guild.id, uid, _NS, "streak", 0)
            repeat = offense >= 2
            penalty_pct = economy.TAX_PENALTY_PCT_2 if repeat else economy.TAX_PENALTY_PCT_1

            coins = economy.get_coins(guild.id, uid)
            target = owed + int(coins * penalty_pct)   # bill + wallet penalty
            seized = self._seize(guild.id, uid, target)  # capped at wallet

            economy.jail_user(
                guild.id, uid,
                int(economy.TAX_JAIL_REPEAT_SECONDS if repeat else economy.TAX_JAIL_SECONDS),
                reason="Tax evasion", channel_id=channel_id, no_release=repeat,
            )
            economy.kv_delete(guild.id, uid, _NS, "owed")
            # No baseline roll here: `net_base` was snapshotted to this levy's
            # net_won in _levy, and seizure (is_bet=False) doesn't touch net_won.
            # Leaving it means any winnings during the grace window are taxed next
            # period — same as players who paid on time.
            evaders.append((uid, seized, offense))

        # Close the window — back to idle until next week's levy.
        economy.kv_set(guild.id, 0, _NS, "due_ts", 0)
        await self._announce_enforcement(guild, ch, evaders)

    def _seize(self, guild_id: int, user_id: int, amount: int) -> int:
        """Move up to `amount` coins from a player to the house (closed loop),
        capped at what they actually hold. Returns coins seized."""
        coins = economy.get_coins(guild_id, user_id)
        take = min(amount, coins)
        if take <= 0:
            return 0
        return take if economy.transfer_to_house(guild_id, user_id, take, is_bet=False).get("ok") else 0

    async def _announce_enforcement(self, guild, ch, evaders):
        if ch is None:
            return
        if not evaders:
            embed = discord.Embed(
                title="✅ Taxes Settled",
                description="Everyone paid up this week. The house is pleased.",
                color=discord.Color.green(),
            )
        else:
            h1 = int(economy.TAX_JAIL_SECONDS // 3600)
            h2 = int(economy.TAX_JAIL_REPEAT_SECONDS // 3600)
            lines = []
            for uid, seized, offense in evaders[:_MAX_LIST]:
                if offense >= 2:
                    tag = f"repeat offender — **{h2}h**, no card out"
                else:
                    tag = f"first offense — **{h1}h**"
                lines.append(f"<@{uid}> — **{seized:,}** seized, {tag}")
            if len(evaders) > _MAX_LIST:
                lines.append(f"…and **{len(evaders) - _MAX_LIST}** more.")
            embed = discord.Embed(
                title="🚔 TAX EVASION CRACKDOWN",
                description=(
                    f"The deadline passed. **{len(evaders)}** deadbeat(s) hauled "
                    f"off to jail, bill plus a cut of the wallet seized for the "
                    f"house:\n\n" + "\n".join(lines)
                ),
                color=discord.Color.dark_red(),
            )
        try:
            await ch.send(embed=embed)
        except discord.HTTPException as e:
            logger.error(f"Failed to post tax enforcement in guild {guild.id}: {e}")

    # --- player commands --------------------------------------------------

    def _pay(self, guild_id: int, user: discord.abc.User) -> discord.Embed:
        owed = self._owed(guild_id, user.id)
        if owed <= 0:
            return discord.Embed(
                description="You don't owe any taxes right now. Breathe easy.",
                color=discord.Color.green(),
            )
        res = economy.transfer_to_house(guild_id, user.id, owed, is_bet=False)
        if not res.get("ok"):
            if res.get("error") == "broke":
                have = res.get("have", 0)
                return discord.Embed(
                    title="💸 Can't Cover It",
                    description=(
                        f"Your tax bill is **{owed:,}** but you only have "
                        f"**{have:,}**. Win it back before the deadline or it's "
                        f"jail and a forfeited wallet."
                    ),
                    color=discord.Color.red(),
                )
            return discord.Embed(description="Payment failed. Try again.",
                                 color=discord.Color.red())
        economy.kv_delete(guild_id, user.id, _NS, "owed")
        decayed = self._credit_on_time(guild_id, user.id)
        bal = economy.get_coins(guild_id, user.id)
        desc = (
            f"{user.mention} settled a **{owed:,}** coin tax bill with the "
            f"house.\nBalance: **{bal:,}** coins."
        )
        if decayed:
            desc += (
                "\n\n✅ Clean streak paid off — your evasion record dropped a "
                "tier. Keep it up."
            )
        return discord.Embed(title="🧾 Taxes Paid", description=desc,
                             color=discord.Color.gold())

    def _credit_on_time(self, guild_id: int, user_id: int) -> bool:
        """Record an on-time payment toward decay. Returns True if it dropped
        the player's offense level a tier this time."""
        offense = int(economy.kv_get(guild_id, user_id, _NS, "offenses", 0) or 0)
        if offense <= 0:
            return False  # nothing to decay; don't bother tracking a streak
        streak = int(economy.kv_get(guild_id, user_id, _NS, "streak", 0) or 0) + 1
        if streak >= economy.TAX_DECAY_WEEKS:
            economy.kv_set(guild_id, user_id, _NS, "offenses", offense - 1)
            economy.kv_set(guild_id, user_id, _NS, "streak", 0)
            return True
        economy.kv_set(guild_id, user_id, _NS, "streak", streak)
        return False

    def _bill(self, guild_id: int, user: discord.abc.User) -> discord.Embed:
        owed = self._owed(guild_id, user.id)
        _last, due = self._guild_state(guild_id)
        if owed <= 0 or due <= 0:
            return discord.Embed(
                title="🧾 Tax Bill",
                description="No taxes due right now. The next levy comes when it comes.",
                color=discord.Color.green(),
            )
        return discord.Embed(
            title="🧾 Tax Bill",
            description=(
                f"You owe **{owed:,}** coins on this week's winnings.\n"
                f"Pay with `/paytax` before <t:{int(due)}:R> (<t:{int(due)}:f>) "
                f"or face jail and a forfeited wallet."
            ),
            color=discord.Color.dark_gold(),
        )

    @commands.command(name="paytax", aliases=["paytaxes"])
    @commands.guild_only()
    async def paytax_prefix(self, ctx):
        """Pay your weekly tax bill."""
        await ctx.send(embed=self._pay(ctx.guild.id, ctx.author))

    @app_commands.command(name="paytax", description="Pay your weekly winnings-tax bill to the house.")
    async def paytax_slash(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=self._pay(interaction.guild_id, interaction.user)
        )

    @commands.command(name="taxbill", aliases=["taxes", "mytax"])
    @commands.guild_only()
    async def taxbill_prefix(self, ctx):
        """Check what you owe and when it's due."""
        await ctx.send(embed=self._bill(ctx.guild.id, ctx.author))

    @app_commands.command(name="taxbill", description="Check your current tax bill and deadline.")
    async def taxbill_slash(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=self._bill(interaction.guild_id, interaction.user), ephemeral=True
        )

    # --- admin: force a levy now (testing / manual collection) ------------

    @commands.command(name="taxrun")
    @commands.guild_only()
    async def taxrun_prefix(self, ctx):
        """Admin: trigger a tax levy immediately (admin channel only)."""
        if ctx.channel.id != ADMIN_CHANNEL_ID:
            return
        _last, due = self._guild_state(ctx.guild.id)
        if due > 0:
            await ctx.send("A collection window is already open. Wait for it to close.")
            return
        await self._levy(ctx.guild, time.time())
        await ctx.send("Levy triggered.")


async def setup(bot):
    await bot.add_cog(Taxes(bot))
