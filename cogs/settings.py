"""
settings.py — one generic /set, /get, /unset for every per-user preference.

Instead of each cog spending a slash command on its own `/foo-save`, cogs
register their settings with `user_settings.register(...)` and players manage
them all through this single cog. Keeps us well under Discord's 100-command cap.

    /set setting:<name> value:<...>   save a preference
    /get [setting:<name>]             show one or all of your saved preferences
    /unset setting:<name>             forget a preference

The `setting` field autocompletes from the live registry, so newly-registered
settings appear automatically with no change here.
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging

import user_settings

logger = logging.getLogger(__name__)


class SettingsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Settings cog loaded (%d registered settings).",
                    len(user_settings.all_settings()))

    # --- shared logic --------------------------------------------------------

    def _do_set(self, user_id: int, key: str, value: str) -> str:
        setting = user_settings.get_setting(key)
        if not setting:
            return self._unknown(key)
        try:
            normalized = user_settings.normalize(setting, value)
        except ValueError as e:
            return f"❌ {e}"
        user_settings.set_value(user_id, setting.key, normalized)
        return f"✅ Saved **{setting.label}** → `{normalized}`"

    def _do_unset(self, user_id: int, key: str) -> str:
        setting = user_settings.get_setting(key)
        if not setting:
            return self._unknown(key)
        if user_settings.get_value(user_id, setting.key) is None:
            return f"You had no **{setting.label}** saved."
        user_settings.clear_value(user_id, setting.key)
        return f"🗑️ Forgot your **{setting.label}**."

    def _do_get(self, user_id: int, key: str | None) -> str:
        if key:
            setting = user_settings.get_setting(key)
            if not setting:
                return self._unknown(key)
            val = user_settings.get_value(user_id, setting.key)
            if val is None:
                return f"No **{setting.label}** saved. Set it with `/set {setting.key} <value>`."
            return f"**{setting.label}**: `{val}`"

        # No key → list everything the user has saved.
        saved = user_settings.all_for_user(user_id)
        if not saved:
            return ("You haven't saved any settings yet. Available:\n" +
                    self._available())
        lines = []
        for s in user_settings.all_settings():
            if s.key in saved:
                lines.append(f"• **{s.label}** (`{s.key}`): `{saved[s.key]}`")
        return "Your saved settings:\n" + "\n".join(lines)

    def _unknown(self, key: str) -> str:
        return (f"❌ `{key}` isn't a known setting.\n" + self._available())

    def _available(self) -> str:
        settings = user_settings.all_settings()
        if not settings:
            return "_(no settings are registered)_"
        return "\n".join(f"• `{s.key}` — {s.description}" for s in settings)

    # --- slash ---------------------------------------------------------------

    async def _setting_autocomplete(self, interaction: discord.Interaction, current: str):
        current = current.lower()
        return [
            app_commands.Choice(name=s.label, value=s.key)
            for s in user_settings.all_settings()
            if current in s.key.lower() or current in s.label.lower()
        ][:25]

    @app_commands.command(name="set", description="Save a personal preference (e.g. your weather location)")
    @app_commands.describe(setting="Which preference to set", value="The value to save")
    @app_commands.autocomplete(setting=_setting_autocomplete)
    async def set_slash(self, interaction: discord.Interaction, setting: str, value: str):
        await interaction.response.send_message(
            self._do_set(interaction.user.id, setting, value), ephemeral=True)

    @app_commands.command(name="get", description="Show your saved preferences")
    @app_commands.describe(setting="Optional — a single preference to show")
    @app_commands.autocomplete(setting=_setting_autocomplete)
    async def get_slash(self, interaction: discord.Interaction, setting: str | None = None):
        await interaction.response.send_message(
            self._do_get(interaction.user.id, setting), ephemeral=True)

    @app_commands.command(name="unset", description="Forget a saved preference")
    @app_commands.describe(setting="Which preference to clear")
    @app_commands.autocomplete(setting=_setting_autocomplete)
    async def unset_slash(self, interaction: discord.Interaction, setting: str):
        await interaction.response.send_message(
            self._do_unset(interaction.user.id, setting), ephemeral=True)

    # --- prefix --------------------------------------------------------------

    @commands.command(name="set")
    async def set_prefix(self, ctx, setting: str, *, value: str):
        await ctx.send(self._do_set(ctx.author.id, setting, value))

    @commands.command(name="get")
    async def get_prefix(self, ctx, setting: str = None):
        await ctx.send(self._do_get(ctx.author.id, setting))

    @commands.command(name="unset")
    async def unset_prefix(self, ctx, setting: str):
        await ctx.send(self._do_unset(ctx.author.id, setting))


async def setup(bot):
    await bot.add_cog(SettingsCog(bot))
