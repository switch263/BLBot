import discord
from discord.ext import commands
from discord import app_commands
import logging
import economy
import re

from config import ADMIN_CHANNEL_ID

logger = logging.getLogger(__name__)


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Admin module has been loaded")

    @commands.command(name="coins", aliases=["grantcoins", "addcoins", "cheatchk"])
    async def grant_coins(self, ctx, user: discord.Member, amount: int):
        """Admin command to grant coins to a user. Only works in the admin channel."""
        # Check if command is in the admin channel
        if ctx.channel.id != ADMIN_CHANNEL_ID:
            return  # Silently ignore if not in admin channel

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
    async def remove_coins(self, ctx, user: discord.Member, amount: int):
        """Deduct coins from a user. Allowed in the admin channel, OR anywhere for
        a member with the `Admin` role. Clamps at 0 — never produces a negative balance."""
        in_admin_channel = ctx.channel.id == ADMIN_CHANNEL_ID
        has_admin_role = isinstance(ctx.author, discord.Member) and any(
            r.name == "Admin" for r in ctx.author.roles
        )
        if not (in_admin_channel or has_admin_role):
            return  # Silently ignore — same gate behavior as unjail.

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
            f"• every item-card inventory and the Loaded Dice wager\n"
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


async def setup(bot):
    await bot.add_cog(Admin(bot))
