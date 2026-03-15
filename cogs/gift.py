import discord
from discord.ext import commands
from discord import app_commands
import logging
import economy

logger = logging.getLogger(__name__)


class Gift(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Gift module has been loaded")

    async def _do_gift(self, guild_id: int, sender: discord.Member, recipient: discord.Member, amount: int) -> discord.Embed:
        if sender.id == recipient.id:
            return discord.Embed(description="You can't gift coins to yourself!", color=discord.Color.red())
        if recipient.bot:
            return discord.Embed(description="You can't gift coins to a bot!", color=discord.Color.red())
        if amount < 1:
            return discord.Embed(description="You must gift at least **1** coin!", color=discord.Color.red())
        if amount > 1000000:
            return discord.Embed(description="That's too generous! Max gift is **1,000,000** coins.", color=discord.Color.red())

        balance = economy.get_coins(guild_id, sender.id)
        if balance < amount:
            return discord.Embed(description=f"You only have **{balance}** coins!", color=discord.Color.red())

        sender_bal, recv_bal = economy.transfer_coins(guild_id, sender.id, recipient.id, amount)

        embed = discord.Embed(
            title="Gift Sent!",
            description=f"{sender.mention} gifted **{amount}** coins to {recipient.mention}!",
            color=discord.Color.green()
        )
        embed.add_field(name=f"{sender.display_name}'s Balance", value=f"{sender_bal} coins", inline=True)
        embed.add_field(name=f"{recipient.display_name}'s Balance", value=f"{recv_bal} coins", inline=True)
        return embed

    @commands.command(aliases=['give', 'send'])
    async def gift(self, ctx, recipient: discord.Member = None, amount: int = None):
        """Gift coins to another user. Usage: !gift @user amount"""
        if recipient is None or amount is None:
            await ctx.send("Usage: `!gift @user amount`")
            return
        embed = await self._do_gift(ctx.guild.id, ctx.author, recipient, amount)
        await ctx.send(embed=embed)

    @app_commands.command(name="gift", description="Gift coins to another user")
    @app_commands.describe(recipient="Who to send coins to", amount="How many coins to give")
    async def gift_slash(self, interaction: discord.Interaction, recipient: discord.Member, amount: int):
        embed = await self._do_gift(interaction.guild_id, interaction.user, recipient, amount)
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Gift(bot))
