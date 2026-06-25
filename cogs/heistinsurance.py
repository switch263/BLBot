"""Heist Insurance — buy a policy, reclaim a cut of a robbery from the house.

Distinct from the 🛡️ Heist Shield (which *prevents* one heist): a policy does
nothing to stop the robbery, but afterward you can file a claim and the house
("the bank") reimburses a percentage of what was stolen.

Flow:
  /insure   — buy a policy. Premium is a % of your wallet, paid to the house
              (so the house funds the claims it later pays). Lasts a week.
  /reclaim  — after you've been robbed while insured, file a claim. The house
              pays COVERAGE_PCT of the stolen amount and the policy is spent.
  /policy   — check your policy + any pending claim.

State lives in the cog_kv store (namespace "heistins"). heist.py stamps each
victim's most recent loss as "amount:unix_ts" under the key "last_loss"; a claim
only honors a loss that happened *after* the policy was bought (loss_ts >=
since_ts), so you can't insure a robbery that already occurred. The atomic
kv_claim on f"claimed_{since_ts}" makes a policy single-use even under a
double-clicked /reclaim.

Commands are named /insure, /reclaim, /policy because the fraud-game cog
(cogs/insurance.py) already owns /insurance and the alias /claim.
"""

import discord
from discord.ext import commands
from discord import app_commands
import time
import logging

import economy
from economy import jail_message

logger = logging.getLogger(__name__)

INSURANCE_NS = "heistins"
INSURANCE_PREMIUM_PCT = 0.04          # premium = 4% of your wallet at purchase…
INSURANCE_PREMIUM_MIN = 1_000          # …but at least this much.
INSURANCE_COVERAGE_PCT = 0.60          # reimburse 60% of what was stolen.
INSURANCE_DURATION = 7 * 24 * 60 * 60  # a policy lasts one week.


def _parse_loss(raw) -> tuple[int, int]:
    """Parse the 'amount:unix_ts' loss marker into (amount, ts); (0, 0) if unset
    or malformed."""
    if not raw:
        return 0, 0
    try:
        amount_s, ts_s = str(raw).split(":", 1)
        return int(amount_s), int(ts_s)
    except (ValueError, AttributeError):
        return 0, 0


class HeistInsurance(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Heist Insurance loaded.")

    # ---- helpers --------------------------------------------------------
    def _active_policy(self, guild_id: int, user_id: int) -> dict | None:
        """Return {'since_ts', 'expires_ts'} for a live, unexpired policy, or
        None. Lazily clears an expired one."""
        active = economy.kv_get(guild_id, user_id, INSURANCE_NS, "active", "0")
        if str(active) != "1":
            return None
        since_ts = int(float(economy.kv_get(guild_id, user_id, INSURANCE_NS, "since_ts", 0) or 0))
        expires_ts = int(float(economy.kv_get(guild_id, user_id, INSURANCE_NS, "expires_ts", 0) or 0))
        if time.time() > expires_ts:
            economy.kv_set(guild_id, user_id, INSURANCE_NS, "active", "0")
            return None
        return {"since_ts": since_ts, "expires_ts": expires_ts}

    # ---- /insure --------------------------------------------------------
    async def _buy(self, ctx_or_interaction):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild
        user = ctx_or_interaction.user if is_slash else ctx_or_interaction.author

        async def reply(content, **kwargs):
            if is_slash:
                await ctx_or_interaction.response.send_message(content, **kwargs)
                return await ctx_or_interaction.original_response()
            return await ctx_or_interaction.send(content, **kwargs)

        if not guild:
            await reply("Server only.")
            return

        existing = self._active_policy(guild.id, user.id)
        if existing:
            await reply(
                f"🧾 You already hold an active heist-insurance policy — it expires "
                f"<t:{existing['expires_ts']}:R>. Use `/reclaim` if you've been robbed."
            )
            return

        wallet = economy.get_coins(guild.id, user.id)
        premium = max(INSURANCE_PREMIUM_MIN, int(wallet * INSURANCE_PREMIUM_PCT))
        bet_result = economy.transfer_to_house(guild.id, user.id, premium, is_bet=False)
        if not bet_result.get("ok"):
            if bet_result.get("error") == "broke":
                await reply(
                    f"🧾 The premium is **{premium:,}** ({int(INSURANCE_PREMIUM_PCT * 100)}% of your "
                    f"wallet). You can't cover it — balance: **{bet_result.get('have', 0):,}**."
                )
            else:
                await reply("Couldn't write the policy. Try again.")
            return

        now = int(time.time())
        expires = now + INSURANCE_DURATION
        economy.kv_set(guild.id, user.id, INSURANCE_NS, "active", "1")
        economy.kv_set(guild.id, user.id, INSURANCE_NS, "since_ts", now)
        economy.kv_set(guild.id, user.id, INSURANCE_NS, "expires_ts", expires)
        await reply(
            f"🧾 **Heist insurance written.** Premium of **{premium:,}** paid to the house.\n"
            f"If you're robbed in the next week, `/reclaim` recovers "
            f"**{int(INSURANCE_COVERAGE_PCT * 100)}%** of the loss from the bank. "
            f"Policy expires <t:{expires}:R>."
        )

    # ---- /reclaim -------------------------------------------------------
    async def _claim(self, ctx_or_interaction):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild
        user = ctx_or_interaction.user if is_slash else ctx_or_interaction.author

        async def reply(content, **kwargs):
            if is_slash:
                await ctx_or_interaction.response.send_message(content, **kwargs)
                return await ctx_or_interaction.original_response()
            return await ctx_or_interaction.send(content, **kwargs)

        if not guild:
            await reply("Server only.")
            return

        policy = self._active_policy(guild.id, user.id)
        if not policy:
            await reply("🧾 You have no active heist-insurance policy. Buy one with `/insure`.")
            return

        amount, loss_ts = _parse_loss(
            economy.kv_get(guild.id, user.id, INSURANCE_NS, "last_loss", "")
        )
        if amount <= 0 or loss_ts < policy["since_ts"]:
            await reply(
                "🧾 Nothing to claim — your policy only covers robberies that happen "
                "*after* you bought it, and you haven't been hit since."
            )
            return

        # Single-use gate: only the first /reclaim against this policy pays out,
        # even if double-clicked. since_ts uniquely identifies this policy.
        if not economy.kv_claim(guild.id, user.id, INSURANCE_NS, f"claimed_{policy['since_ts']}", "1"):
            await reply("🧾 You've already claimed on this policy. One payout per policy.")
            return

        payout = max(1, int(amount * INSURANCE_COVERAGE_PCT))
        paid = economy.casino_payout(guild.id, user.id, payout)
        minted = 0
        if paid < payout:  # the bank always honors a valid claim — mint the rest
            minted = payout - paid
            economy.add_coins(guild.id, user.id, minted)

        # Spend the policy and clear the loss so it can't be re-used.
        economy.kv_set(guild.id, user.id, INSURANCE_NS, "active", "0")
        economy.kv_delete(guild.id, user.id, INSURANCE_NS, "last_loss")

        mint_note = "" if minted <= 0 else "\n*(the bank fired up the printer to honor it 🖨️)*"
        await reply(
            f"🧾💰 **Claim approved.** You were robbed of **{amount:,}**; the bank reimburses "
            f"**{payout:,}** ({int(INSURANCE_COVERAGE_PCT * 100)}%). Policy is now spent.{mint_note}"
        )

    # ---- /policy --------------------------------------------------------
    async def _status(self, ctx_or_interaction):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild
        user = ctx_or_interaction.user if is_slash else ctx_or_interaction.author

        async def reply(content, **kwargs):
            if is_slash:
                await ctx_or_interaction.response.send_message(content, **kwargs)
                return await ctx_or_interaction.original_response()
            return await ctx_or_interaction.send(content, **kwargs)

        if not guild:
            await reply("Server only.")
            return

        policy = self._active_policy(guild.id, user.id)
        if not policy:
            await reply(
                f"🧾 No active policy. `/insure` buys one for "
                f"{int(INSURANCE_PREMIUM_PCT * 100)}% of your wallet — covers "
                f"{int(INSURANCE_COVERAGE_PCT * 100)}% of a robbery for a week."
            )
            return

        amount, loss_ts = _parse_loss(
            economy.kv_get(guild.id, user.id, INSURANCE_NS, "last_loss", "")
        )
        lines = [
            f"🧾 **Heist insurance — active.** Expires <t:{policy['expires_ts']}:R>.",
            f"Coverage: **{int(INSURANCE_COVERAGE_PCT * 100)}%** of a robbery.",
        ]
        if amount > 0 and loss_ts >= policy["since_ts"]:
            lines.append(
                f"📌 Pending claim: robbed of **{amount:,}** — `/reclaim` to collect "
                f"**{int(amount * INSURANCE_COVERAGE_PCT):,}**."
            )
        else:
            lines.append("No claimable robbery yet. Stay frosty.")
        await reply("\n".join(lines))

    # ---- prefix commands ------------------------------------------------
    @commands.command(name="insure")
    @commands.guild_only()
    async def insure_prefix(self, ctx):
        await self._buy(ctx)

    @commands.command(name="reclaim")
    @commands.guild_only()
    async def reclaim_prefix(self, ctx):
        await self._claim(ctx)

    @commands.command(name="policy")
    @commands.guild_only()
    async def policy_prefix(self, ctx):
        await self._status(ctx)

    # ---- slash commands -------------------------------------------------
    # All three live under one /insure group (a single top-level slash command
    # with subcommands) to spend just one slot against Discord's 100-command cap.
    insure_group = app_commands.Group(name="insure", description="Heist insurance — hedge against being robbed.")

    @insure_group.command(name="buy", description="Buy heist insurance — reclaim part of a robbery from the bank.")
    async def insure_buy(self, interaction: discord.Interaction):
        await self._buy(interaction)

    @insure_group.command(name="claim", description="File a heist-insurance claim after you've been robbed.")
    async def insure_claim(self, interaction: discord.Interaction):
        await self._claim(interaction)

    @insure_group.command(name="status", description="Check your heist-insurance policy and any pending claim.")
    async def insure_status(self, interaction: discord.Interaction):
        await self._status(interaction)


async def setup(bot):
    await bot.add_cog(HeistInsurance(bot))
