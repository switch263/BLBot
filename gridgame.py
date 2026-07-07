"""Shared machinery for the grid push-your-luck games (mines, raccoon den,
bigfoot). One player, a grid of hidden tile buttons, one action button
(cash out / climb out / head back), a timeout that resolves the game instead
of eating the stake.

The base owns the plumbing that was copy-pasted three times: building the
button grid, gating clicks to the owner, ignoring clicks after the game ends,
flipping the board face-up, disabling everything, and routing the timeout.
Game logic — what a tile IS, what it pays, what the board looks like — stays
in the cog. Subclasses implement:

    async def on_tile(self, interaction, idx)   # a live tile was clicked
    async def on_action(self, interaction)      # the action button was clicked
    def tile_face(self, idx)                    # end-state face for tile idx:
                                                #   (label, style) or None to
                                                #   leave the button as-is
    async def on_abandon(self)                  # timed out unresolved

and call self.finish() when the game ends (reveals the board, disables all
buttons, stops the view).
"""
import discord


class GridView(discord.ui.View):
    HIDDEN_LABEL = "⬛"

    def __init__(self, user_id: int, *, rows: int, cols: int, timeout: float,
                 not_yours: str = "Not your game."):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.not_yours = not_yours
        self.resolved = False
        self.message: discord.Message | None = None

        self.tile_btns: list[discord.ui.Button] = []
        for i in range(rows * cols):
            btn = discord.ui.Button(
                label=self.HIDDEN_LABEL,
                style=discord.ButtonStyle.secondary,
                row=i // cols,
            )
            btn.callback = self._make_tile_cb(i)
            self.tile_btns.append(btn)
            self.add_item(btn)

        self.action_btn = discord.ui.Button(style=discord.ButtonStyle.primary, row=rows)
        self.action_btn.callback = self._action_cb
        self.add_item(self.action_btn)

    # ---- gating ----------------------------------------------------------
    async def _gate(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(self.not_yours, ephemeral=True)
            return False
        if self.resolved:
            await interaction.response.defer()
            return False
        return True

    def _make_tile_cb(self, idx: int):
        async def cb(interaction: discord.Interaction):
            if await self._gate(interaction):
                await self.on_tile(interaction, idx)
        return cb

    async def _action_cb(self, interaction: discord.Interaction):
        if await self._gate(interaction):
            await self.on_action(interaction)

    # ---- endgame ---------------------------------------------------------
    def finish(self):
        """Mark resolved, flip the board face-up, freeze every button."""
        self.resolved = True
        self.reveal_board()
        for child in self.children:
            child.disabled = True
        self.stop()

    def reveal_board(self):
        for i, btn in enumerate(self.tile_btns):
            face = self.tile_face(i)
            if face is not None:
                btn.label, btn.style = face

    async def on_timeout(self):
        if self.resolved:
            return
        self.resolved = True
        await self.on_abandon()

    # ---- subclass hooks ----------------------------------------------------
    async def on_tile(self, interaction: discord.Interaction, idx: int):
        raise NotImplementedError

    async def on_action(self, interaction: discord.Interaction):
        raise NotImplementedError

    def tile_face(self, idx: int):
        return None

    async def on_abandon(self):
        pass
