import discord
from discord.ext import commands
from discord import app_commands
import logging
import economy
import re

from config import ADMIN_CHANNEL_ID
from amount import parse_amount, amount_error

logger = logging.getLogger(__name__)


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Admin module has been loaded")

    @commands.command(name="coins", aliases=["grantcoins", "addcoins", "cheatchk"])
    async def grant_coins(self, ctx, user: discord.Member, amount: str):
        """Admin command to grant coins to a user. Only works in the admin channel."""
        # Check if command is in the admin channel
        if ctx.channel.id != ADMIN_CHANNEL_ID:
            return  # Silently ignore if not in admin channel

        # Parse amount
        amt = parse_amount(amount)
        if amt is None:
            await ctx.send(amount_error(amount))
            return
        amount = amt

        # Validate amount
        if amount <= 0:
            await ctx.send("Amount must be positive!")
            return

        # Grant the coins
        guild_id = ctx.guild.id
        economy.award_coins(guild_id, user.id, amount)

        # Confirm
        embed = discord.Embed(
            title="💰 Coins Granted",
            description=f"{ctx.author.mention} granted **{amount:,}** coins to {user.mention}",
            color=discord.Color.gold()
        )
        embed.add_field(name="New Balance", value=f"{economy.get_coins(guild_id, user.id):,} coins")
        embed.set_footer(text=f"Admin: {ctx.author.display_name}")
        await ctx.send(embed=embed)

        logger.info(f"Admin {ctx.author} granted {amount} coins to {user} in guild {guild_id}")

    @commands.command(name="unjail", aliases=["pardon"])
    async def unjail(self, ctx, user: discord.Member):
        """Release a user from casino jail. Allowed in the admin channel, OR anywhere
        for a member with the `Admin` role."""
        in_admin_channel = ctx.channel.id == ADMIN_CHANNEL_ID
        has_admin_role = isinstance(ctx.author, discord.Member) and any(
            r.name == "Admin" for r in ctx.author.roles
        )
        if not (in_admin_channel or has_admin_role):
            return  # Silently ignore — same gate behavior as the other admin commands.

        guild_id = ctx.guild.id
        was_jailed = economy.unjail_user(guild_id, user.id)

        if was_jailed:
            embed = discord.Embed(
                title="🔓 Released from Jail",
                description=f"{ctx.author.mention} pardoned {user.mention}. Back in the casino.",
                color=discord.Color.green(),
            )
            embed.set_footer(text=f"Admin: {ctx.author.display_name}")
            await ctx.send(embed=embed)
            logger.info(f"Admin {ctx.author} unjailed {user} in guild {guild_id}")
        else:
            await ctx.send(f"{user.display_name} wasn't in jail.")

    @commands.command(name="removecoins", aliases=["takecoins", "deductcoins", "subcoins"])
    async def remove_coins(self, ctx, user: discord.Member, amount: str):
        """Deduct coins from a user. Allowed in the admin channel, OR anywhere for
        a member with the `Admin` role. Clamps at 0 — never produces a negative balance."""
        in_admin_channel = ctx.channel.id == ADMIN_CHANNEL_ID
        has_admin_role = isinstance(ctx.author, discord.Member) and any(
            r.name == "Admin" for r in ctx.author.roles
        )
        if not (in_admin_channel or has_admin_role):
            return  # Silently ignore — same gate behavior as unjail.

        # Parse amount
        amt = parse_amount(amount)
        if amt is None:
            await ctx.send(amount_error(amount))
            return
        amount = amt

        if amount <= 0:
            await ctx.send("Amount must be positive!")
            return

        guild_id = ctx.guild.id
        before = economy.get_coins(guild_id, user.id)
        economy.fine_user(guild_id, user.id, amount)
        after = economy.get_coins(guild_id, user.id)
        actually_removed = before - after

        embed = discord.Embed(
            title="💸 Coins Removed",
            description=f"{ctx.author.mention} removed **{actually_removed:,}** coins from {user.mention}.",
            color=discord.Color.dark_red(),
        )
        if actually_removed < amount:
            embed.add_field(
                name="Note",
                value=f"Requested {amount:,}, but balance was only {before:,} — clamped at 0.",
                inline=False,
            )
        embed.add_field(name="New Balance", value=f"{after:,} coins")
        embed.set_footer(text=f"Admin: {ctx.author.display_name}")
        await ctx.send(embed=embed)

        logger.info(f"Admin {ctx.author} removed {actually_removed} coins from {user} in guild {guild_id}")

    # ----------------------------------------------------------------------
    # !clear_economy — PR-style approval flow for a full economy wipe.
    # ----------------------------------------------------------------------
    @commands.command(name="clear_economy")
    @commands.guild_only()
    async def clear_economy(self, ctx):
        """Wipe the entire economy for this server. Requires two approvals from
        OTHER admin-channel members before it runs. Admin channel only."""
        if ctx.channel.id != ADMIN_CHANNEL_ID:
            return  # Silently ignore — admin channel only.
        view = ClearEconomyView(
            initiator=ctx.author,
            guild=ctx.guild,
            channel=ctx.channel,
            required_approvals=2,
        )
        msg = await ctx.send(view.status_text(), view=view)
        view.message = msg
        logger.info(
            f"clear_economy requested by {ctx.author} in guild {ctx.guild.id} "
            f"(awaiting {view.required_approvals} approvals)"
        )

    # ----------------------------------------------------------------------
    # !deletewallet — approval-gated wipe of a single player's wallet.
    # ----------------------------------------------------------------------
    @commands.command(name="deletewallet", aliases=["resetwallet", "wipewallet"])
    @commands.guild_only()
    async def delete_wallet_cmd(self, ctx, *, member: discord.Member):
        """Wipe ONE player's wallet + economy footprint (game stats preserved).
        Requires one approval from another admin-channel member. Admin channel only."""
        if ctx.channel.id != ADMIN_CHANNEL_ID:
            return  # Silently ignore — admin channel only.
        if member.bot:
            await ctx.send("🚫 Can't delete a bot's wallet — that's the house pot.")
            return
        if economy.is_memorial(member.id):
            await ctx.send("🚫 That's the memorial player (kev2tall). His wallet is protected.")
            return
        view = DeleteWalletView(
            initiator=ctx.author,
            guild=ctx.guild,
            channel=ctx.channel,
            target=member,
            required_approvals=1,
        )
        msg = await ctx.send(view.status_text(), view=view)
        view.message = msg
        logger.info(
            f"deletewallet requested by {ctx.author} for {member} in guild "
            f"{ctx.guild.id} (awaiting {view.required_approvals} approval)"
        )


# --------------------------------------------------------------------------
# ClearEconomyView — PR-style approval gate for the irreversible wipe.
# --------------------------------------------------------------------------

class ClearEconomyView(discord.ui.View):
    """Posts in the admin channel. Two distinct admin-channel members (not the
    initiator) must click Approve before the wipe runs. The initiator — or any
    admin-channel member — can cancel. 5-minute timeout."""

    def __init__(self, initiator: discord.Member, guild: discord.Guild,
                 channel: discord.TextChannel, required_approvals: int = 2):
        super().__init__(timeout=300)
        self.initiator = initiator
        self.guild = guild
        self.channel = channel
        self.required_approvals = required_approvals
        self.approvers: set[int] = set()
        self.message: discord.Message | None = None
        self.resolved = False

    # ---- eligibility & rendering --------------------------------------
    def _is_admin_channel_member(self, user_id: int) -> bool:
        return any(m.id == user_id and not m.bot for m in self.channel.members)

    def _approver_names(self) -> str:
        if not self.approvers:
            return "—"
        names = []
        for uid in self.approvers:
            m = self.guild.get_member(uid)
            names.append(m.display_name if m else f"<{uid}>")
        return ", ".join(names)

    def status_text(self) -> str:
        return (
            f"🚨 **ECONOMY CLEAR REQUESTED**\n"
            f"{self.initiator.mention} wants to **wipe the economy** for this server. "
            f"There is no undo.\n\n"
            f"**This will reset:**\n"
            f"• every player wallet (back to fresh)\n"
            f"• the house pot — on-hand AND safe-harbor reserve\n"
            f"• all active jail sentences\n"
            f"• every item-card inventory\n"
            f"• loot-drop cooldowns (AM/PM)\n"
            f"• jail-bounty rate-limit history\n\n"
            f"**Preserved:** game stats (play counts, win counts) — leaderboards survive.\n\n"
            f"**{self.required_approvals} approvals required** from other admin-channel "
            f"members. The initiator's request does not count.\n"
            f"**Approvals: {len(self.approvers)}/{self.required_approvals}**  ({self._approver_names()})"
        )

    async def _refresh(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content=self.status_text(), view=self)

    def _disable_all(self):
        for child in self.children:
            child.disabled = True

    # ---- buttons -------------------------------------------------------
    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="✅")
    async def approve_button(self, interaction: discord.Interaction,
                              button: discord.ui.Button):
        if self.resolved:
            await interaction.response.send_message(
                "This request is already resolved.", ephemeral=True)
            return
        user = interaction.user
        if user.id == self.initiator.id:
            await interaction.response.send_message(
                "🚫 You started this request — someone else has to approve.",
                ephemeral=True)
            return
        if not self._is_admin_channel_member(user.id):
            await interaction.response.send_message(
                "🚫 Only admin-channel members can approve.", ephemeral=True)
            return
        if user.id in self.approvers:
            await interaction.response.send_message(
                "You already approved.", ephemeral=True)
            return
        self.approvers.add(user.id)

        if len(self.approvers) >= self.required_approvals:
            await self._execute(interaction)
        else:
            await self._refresh(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="✖️")
    async def cancel_button(self, interaction: discord.Interaction,
                             button: discord.ui.Button):
        if self.resolved:
            await interaction.response.send_message(
                "This request is already resolved.", ephemeral=True)
            return
        # Initiator OR any admin-channel member can cancel.
        if (interaction.user.id != self.initiator.id
                and not self._is_admin_channel_member(interaction.user.id)):
            await interaction.response.send_message(
                "🚫 Only admin-channel members can cancel.", ephemeral=True)
            return
        self.resolved = True
        self._disable_all()
        self.stop()
        await interaction.response.edit_message(
            content=(
                f"❌ **Economy clear cancelled** by {interaction.user.mention}.\n"
                f"Initiator was {self.initiator.mention}; "
                f"approvals at cancel: {len(self.approvers)}/{self.required_approvals}."
            ),
            view=self,
        )

    # ---- execution & timeout ------------------------------------------
    async def _execute(self, interaction: discord.Interaction):
        self.resolved = True
        self._disable_all()
        self.stop()
        result = economy.clear_economy(self.guild.id)
        rows_summary = "\n".join(
            f"• `{tbl}`: **{n}** rows" for tbl, n in result.items()
        ) or "_(no rows reported)_"
        await interaction.response.edit_message(
            content=(
                f"💥 **ECONOMY CLEARED** — fresh slate.\n"
                f"Initiator: {self.initiator.mention}\n"
                f"Approved by: {self._approver_names()}\n\n"
                f"**Deleted:**\n{rows_summary}\n\n"
                f"Game stats preserved. Everyone starts over."
            ),
            view=self,
        )
        logger.warning(
            f"ECONOMY CLEARED in guild {self.guild.id} by {self.initiator} "
            f"with approvals from {self.approvers}; rows deleted: {result}"
        )

    async def on_timeout(self):
        if self.resolved or self.message is None:
            return
        self.resolved = True
        self._disable_all()
        try:
            await self.message.edit(
                content=(
                    f"⏰ **Economy clear expired** without enough approvals "
                    f"({len(self.approvers)}/{self.required_approvals} after 5 min). "
                    f"Request: {self.initiator.mention}."
                ),
                view=self,
            )
        except Exception as e:
            logger.error(f"Failed to edit on clear_economy timeout: {e}")


# --------------------------------------------------------------------------
# DeleteWalletView — approval gate for wiping a single player's wallet.
# --------------------------------------------------------------------------

class DeleteWalletView(discord.ui.View):
    """Posts in the admin channel. One admin-channel member who is NOT the
    initiator must click Approve before the target's wallet is wiped. The
    initiator — or any admin-channel member — can cancel. 5-minute timeout."""

    def __init__(self, initiator: discord.Member, guild: discord.Guild,
                 channel: discord.TextChannel, target: discord.Member,
                 required_approvals: int = 1):
        super().__init__(timeout=300)
        self.initiator = initiator
        self.guild = guild
        self.channel = channel
        self.target = target
        self.required_approvals = required_approvals
        self.approvers: set[int] = set()
        self.message: discord.Message | None = None
        self.resolved = False

    # ---- eligibility & rendering --------------------------------------
    def _is_admin_channel_member(self, user_id: int) -> bool:
        return any(m.id == user_id and not m.bot for m in self.channel.members)

    def _approver_names(self) -> str:
        if not self.approvers:
            return "—"
        names = []
        for uid in self.approvers:
            m = self.guild.get_member(uid)
            names.append(m.display_name if m else f"<{uid}>")
        return ", ".join(names)

    def status_text(self) -> str:
        bal = economy.get_coins(self.guild.id, self.target.id)
        return (
            f"🗑️ **WALLET DELETE REQUESTED**\n"
            f"{self.initiator.mention} wants to **wipe {self.target.mention}'s "
            f"wallet** (currently **{bal:,}** coins). There is no undo.\n\n"
            f"**This will reset, for this player only:**\n"
            f"• their wallet (coins + winnings, back to fresh)\n"
            f"• any active jail sentence\n"
            f"• their item-card inventory & cog state (incl. tax baseline)\n"
            f"• their loot-drop cooldowns and bounty history\n\n"
            f"**Preserved:** their game stats (play/win counts). The house pot "
            f"and everyone else are untouched.\n\n"
            f"**{self.required_approvals} approval required** from another "
            f"admin-channel member. The initiator's request does not count.\n"
            f"**Approvals: {len(self.approvers)}/{self.required_approvals}**  "
            f"({self._approver_names()})"
        )

    async def _refresh(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content=self.status_text(), view=self)

    def _disable_all(self):
        for child in self.children:
            child.disabled = True

    # ---- buttons -------------------------------------------------------
    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="✅")
    async def approve_button(self, interaction: discord.Interaction,
                              button: discord.ui.Button):
        if self.resolved:
            await interaction.response.send_message(
                "This request is already resolved.", ephemeral=True)
            return
        user = interaction.user
        if user.id == self.initiator.id:
            await interaction.response.send_message(
                "🚫 You started this request — someone else has to approve.",
                ephemeral=True)
            return
        if not self._is_admin_channel_member(user.id):
            await interaction.response.send_message(
                "🚫 Only admin-channel members can approve.", ephemeral=True)
            return
        if user.id in self.approvers:
            await interaction.response.send_message(
                "You already approved.", ephemeral=True)
            return
        self.approvers.add(user.id)

        if len(self.approvers) >= self.required_approvals:
            await self._execute(interaction)
        else:
            await self._refresh(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="✖️")
    async def cancel_button(self, interaction: discord.Interaction,
                             button: discord.ui.Button):
        if self.resolved:
            await interaction.response.send_message(
                "This request is already resolved.", ephemeral=True)
            return
        # Initiator OR any admin-channel member can cancel.
        if (interaction.user.id != self.initiator.id
                and not self._is_admin_channel_member(interaction.user.id)):
            await interaction.response.send_message(
                "🚫 Only admin-channel members can cancel.", ephemeral=True)
            return
        self.resolved = True
        self._disable_all()
        self.stop()
        await interaction.response.edit_message(
            content=(
                f"❌ **Wallet delete cancelled** by {interaction.user.mention}.\n"
                f"Target was {self.target.mention}; initiator {self.initiator.mention}."
            ),
            view=self,
        )

    # ---- execution & timeout ------------------------------------------
    async def _execute(self, interaction: discord.Interaction):
        self.resolved = True
        self._disable_all()
        self.stop()
        result = economy.delete_wallet(self.guild.id, self.target.id)
        rows_summary = "\n".join(
            f"• `{tbl}`: **{n}** rows" for tbl, n in result.items()
        ) or "_(no rows reported)_"
        await interaction.response.edit_message(
            content=(
                f"💥 **WALLET DELETED** — {self.target.mention} is back to a fresh slate.\n"
                f"Initiator: {self.initiator.mention}\n"
                f"Approved by: {self._approver_names()}\n\n"
                f"**Deleted:**\n{rows_summary}\n\n"
                f"Game stats preserved."
            ),
            view=self,
        )
        logger.warning(
            f"WALLET DELETED for {self.target} in guild {self.guild.id} by "
            f"{self.initiator} with approvals from {self.approvers}; rows: {result}"
        )

    async def on_timeout(self):
        if self.resolved or self.message is None:
            return
        self.resolved = True
        self._disable_all()
        try:
            await self.message.edit(
                content=(
                    f"⏰ **Wallet delete expired** without approval "
                    f"({len(self.approvers)}/{self.required_approvals} after 5 min). "
                    f"Target: {self.target.mention}; request: {self.initiator.mention}."
                ),
                view=self,
            )
        except Exception as e:
            logger.error(f"Failed to edit on deletewallet timeout: {e}")


async def setup(bot):
    await bot.add_cog(Admin(bot))
