import discord
from discord.ext import commands
from discord import app_commands
import random
import string
import sys
import os
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from economy import get_coins, add_coins, deduct_coins, jail_message

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data_files")

MIN_BET = 100
NUM_MODIFIERS = 3
INSPECTION_COST_PCT = 0.06
PART_OUT_PCT = 0.30
TRUE_VALUE_FLOOR = 0.15
TRUE_VALUE_CEILING = 4.5
UNCERTAINTY_PER_MODIFIER = 0.30


def _load_lines(filename: str) -> list[str]:
    """Load non-empty stripped lines from data_files/<filename>."""
    path = os.path.join(DATA_DIR, filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            # Preserve leading spaces in suffix pool etc. Only strip trailing newline.
            # Blank lines are kept (they're intentional weight-blanks for prefixes/suffixes).
            return [line.rstrip("\n") for line in f]
    except FileNotFoundError:
        logger.error(f"Lemon data file missing: {path}")
        return []


def _load_modifiers(filename: str) -> list[tuple[str, float]]:
    """Load (text, pct) tuples from a `PCT|TEXT` formatted file."""
    result: list[tuple[str, float]] = []
    for line in _load_lines(filename):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pct_str, _, text = line.partition("|")
        try:
            pct = float(pct_str.strip())
        except ValueError:
            logger.warning(f"Bad lemon modifier line (no pct): {line!r}")
            continue
        text = text.strip()
        if not text:
            continue
        result.append((text, pct))
    return result


def _compose(template: str, pools: dict[str, list[str]], **overrides) -> str:
    """Fill {token} placeholders in `template` using POOLS + overrides.

    - Values in `overrides` take precedence over pool lookups.
    - Unknown tokens are left as literal `{token}` so nothing crashes.
    """
    fields: dict[str, str] = {}
    for _, field, _, _ in string.Formatter().parse(template):
        if not field or field in fields:
            continue
        if field in overrides:
            fields[field] = overrides[field]
        elif field in pools and pools[field]:
            fields[field] = random.choice(pools[field])
        else:
            fields[field] = "{" + field + "}"
    try:
        return template.format(**fields)
    except (IndexError, KeyError) as e:
        logger.error(f"Template format failed for {template!r}: {e}")
        return template


class Modifier:
    def __init__(self, flavor: str, pct: float, is_feature: bool):
        self.flavor = flavor
        self.pct = pct
        self.is_feature = is_feature
        self.revealed = False


class LemonData:
    """Loads and holds all the flavor pools. Exactly one instance per cog."""
    def __init__(self):
        self.car_makes = [s for s in _load_lines("lemon_car_makes.txt") if s.strip()]
        # Prefixes/suffixes keep their blank lines — blanks act as weight for "no prefix".
        self.car_prefixes = _load_lines("lemon_car_prefixes.txt")
        self.car_suffixes = _load_lines("lemon_car_suffixes.txt")
        self.seller_quips = [s for s in _load_lines("lemon_seller_quips.txt") if s.strip()]
        self.mechanics = [s for s in _load_lines("lemon_mechanics.txt") if s.strip()]
        self.smell_sources = [s for s in _load_lines("lemon_smell_sources.txt") if s.strip()]
        self.stain_objects = [s for s in _load_lines("lemon_stain_objects.txt") if s.strip()]
        self.random_objects = [s for s in _load_lines("lemon_random_objects.txt") if s.strip()]
        self.issues = _load_modifiers("lemon_issues.txt")
        self.features = _load_modifiers("lemon_features.txt")
        self.inspect_narrations = [s for s in _load_lines("lemon_inspect_narrations.txt") if s.strip()]
        self.partout_flavor = [s for s in _load_lines("lemon_partout_flavor.txt") if s.strip()]
        self.flip_jackpot = [s for s in _load_lines("lemon_flip_jackpot.txt") if s.strip()]
        self.flip_win = [s for s in _load_lines("lemon_flip_win.txt") if s.strip()]
        self.flip_breakeven = [s for s in _load_lines("lemon_flip_breakeven.txt") if s.strip()]
        self.flip_loss = [s for s in _load_lines("lemon_flip_loss.txt") if s.strip()]
        self.flip_catastrophe = [s for s in _load_lines("lemon_flip_catastrophe.txt") if s.strip()]

        # Pools dict for template composition — keys match {token} names.
        self.pools = {
            "mechanic": self.mechanics,
            "smell_source": self.smell_sources,
            "stain_object": self.stain_objects,
            "random_object": self.random_objects,
        }

        missing = [name for name, pool in [
            ("car_makes", self.car_makes),
            ("seller_quips", self.seller_quips),
            ("mechanics", self.mechanics),
            ("issues", self.issues),
            ("features", self.features),
            ("inspect_narrations", self.inspect_narrations),
            ("partout_flavor", self.partout_flavor),
            ("flip_jackpot", self.flip_jackpot),
            ("flip_win", self.flip_win),
            ("flip_breakeven", self.flip_breakeven),
            ("flip_loss", self.flip_loss),
            ("flip_catastrophe", self.flip_catastrophe),
        ] if not pool]
        if missing:
            logger.error(f"Lemon data pools empty: {missing}")

    def roll_name(self, current_make: str | None = None) -> str:
        """Build a car name from prefix + make + suffix, capitalize first letter.

        Prefix/suffix pool lines are stripped — blank lines still serve as
        weighted 'no prefix / no suffix' choices. We handle the spacing here so
        data files don't depend on invisible trailing whitespace.
        """
        make = current_make or random.choice(self.car_makes or ["1994 Buick Century"])
        prefix = (random.choice(self.car_prefixes).strip() if self.car_prefixes else "")
        suffix = (random.choice(self.car_suffixes).strip() if self.car_suffixes else "")
        name = f"{prefix} {make}" if prefix else make
        if suffix:
            name = f"{name} {suffix}"
        return (name[:1].upper() + name[1:]) if name else make

    def roll_modifier(self) -> Modifier:
        """Pick a modifier — 50/50 issue vs feature, resolve any tokens in the flavor."""
        if random.random() < 0.50 and self.features:
            flavor, pct = random.choice(self.features)
            is_feature = True
        elif self.issues:
            flavor, pct = random.choice(self.issues)
            is_feature = False
        elif self.features:  # fallback if issues list is empty
            flavor, pct = random.choice(self.features)
            is_feature = True
        else:
            return Modifier("Runs. Probably.", 0.0, True)
        # Resolve tokens NOW so the same wording is locked in for the car's life.
        resolved = _compose(flavor, self.pools)
        return Modifier(resolved, pct, is_feature)


class LemonCar:
    def __init__(self, data: LemonData, bet: int):
        self.bet = bet
        self.make = random.choice(data.car_makes) if data.car_makes else "1994 Buick Century"
        self.name = data.roll_name(self.make)
        self.modifiers: list[Modifier] = []
        seen: set[str] = set()
        tries = 0
        while len(self.modifiers) < NUM_MODIFIERS and tries < 40:
            m = data.roll_modifier()
            tries += 1
            if m.flavor in seen:
                continue
            seen.add(m.flavor)
            self.modifiers.append(m)

    @property
    def true_mult(self) -> float:
        mult = 1.0 + sum(m.pct for m in self.modifiers)
        return max(TRUE_VALUE_FLOOR, min(TRUE_VALUE_CEILING, mult))

    @property
    def true_value(self) -> int:
        return int(self.bet * self.true_mult)

    @property
    def known_delta(self) -> float:
        return sum(m.pct for m in self.modifiers if m.revealed)

    @property
    def unrevealed(self) -> list[Modifier]:
        return [m for m in self.modifiers if not m.revealed]

    def reveal_one(self) -> Modifier:
        m = random.choice(self.unrevealed)
        m.revealed = True
        return m

    def estimate_range(self) -> tuple[int, int]:
        known = 1.0 + self.known_delta
        unknowns = len(self.unrevealed)
        unc = UNCERTAINTY_PER_MODIFIER * unknowns
        low = max(TRUE_VALUE_FLOOR, known - unc)
        high = min(TRUE_VALUE_CEILING, known + unc)
        return int(self.bet * low), int(self.bet * high)


class LemonGame:
    def __init__(self, data: LemonData, guild_id: int, user_id: int, user_name: str, bet: int):
        self.data = data
        self.guild_id = guild_id
        self.user_id = user_id
        self.user_name = user_name
        self.bet = bet
        self.car = LemonCar(data, bet)
        self.inspections_paid = 0
        self.inspect_count = 0
        self.ended = False
        self.seller_quip = (
            random.choice(data.seller_quips) if data.seller_quips else "'Runs great.'"
        )


class InspectButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="🔍 Inspect", row=0)

    async def callback(self, interaction: discord.Interaction):
        view: "LemonView" = self.view  # type: ignore
        g = view.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message("Not your car.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return
        cost = int(g.bet * INSPECTION_COST_PCT)
        if not g.car.unrevealed:
            await interaction.response.send_message("Nothing left to inspect.", ephemeral=True)
            return
        if get_coins(g.guild_id, g.user_id) < cost:
            await interaction.response.send_message(
                f"Too broke for another inspection (**{cost}c**). Flip it or part it out.",
                ephemeral=True,
            )
            return

        deduct_coins(g.guild_id, g.user_id, cost)
        g.inspections_paid += cost
        g.inspect_count += 1
        mod = g.car.reveal_one()

        narration_tpl = random.choice(g.data.inspect_narrations) if g.data.inspect_narrations else "{mechanic} says:"
        narration = _compose(narration_tpl, g.data.pools)
        sign = "✅" if mod.is_feature else "❌"
        pct_str = f"{'+' if mod.pct >= 0 else ''}{int(mod.pct * 100)}%"
        finding = f'{sign} *"{mod.flavor}"* (**{pct_str}**)'

        view._refresh()
        await interaction.response.edit_message(
            content=view.cog._render(g, last_event=f"{narration}\n{finding}"),
            view=view,
        )


class FlipButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.success, label="🏁 Flip It", row=0)

    async def callback(self, interaction: discord.Interaction):
        view: "LemonView" = self.view  # type: ignore
        g = view.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message("Not your car.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return
        g.ended = True
        sale = g.car.true_value
        add_coins(g.guild_id, g.user_id, sale)
        net = sale - g.bet - g.inspections_paid

        ratio = g.car.true_mult
        if ratio >= 2.5:
            tier = g.data.flip_jackpot
        elif ratio >= 1.2:
            tier = g.data.flip_win
        elif ratio >= 0.8:
            tier = g.data.flip_breakeven
        elif ratio >= 0.5:
            tier = g.data.flip_loss
        else:
            tier = g.data.flip_catastrophe
        flavor_tpl = random.choice(tier) if tier else "🏁 Sold."
        # Allow flavor templates to reference {mechanic}, {random_object}, or the car's own make.
        flavor = _compose(flavor_tpl, g.data.pools, make=g.car.make)

        for c in view.children:
            c.disabled = True
        await interaction.response.edit_message(
            content=view.cog._render_final(g, sale, net, flavor),
            view=view,
        )


class PartOutButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.danger, label="🪛 Part It Out", row=0)

    async def callback(self, interaction: discord.Interaction):
        view: "LemonView" = self.view  # type: ignore
        g = view.game
        if interaction.user.id != g.user_id:
            await interaction.response.send_message("Not your car.", ephemeral=True)
            return
        if g.ended:
            await interaction.response.defer()
            return
        g.ended = True
        sale = int(g.bet * PART_OUT_PCT)
        add_coins(g.guild_id, g.user_id, sale)
        net = sale - g.bet - g.inspections_paid
        flavor_tpl = random.choice(g.data.partout_flavor) if g.data.partout_flavor else "🪛 Parted out."
        flavor = _compose(flavor_tpl, g.data.pools)

        for c in view.children:
            c.disabled = True
        await interaction.response.edit_message(
            content=view.cog._render_final(g, sale, net, flavor),
            view=view,
        )


class LemonView(discord.ui.View):
    def __init__(self, cog, game: LemonGame):
        super().__init__(timeout=300)
        self.cog = cog
        self.game = game
        self.inspect_btn = InspectButton()
        self.flip_btn = FlipButton()
        self.part_btn = PartOutButton()
        self.add_item(self.inspect_btn)
        self.add_item(self.flip_btn)
        self.add_item(self.part_btn)
        self._refresh()

    def _refresh(self):
        g = self.game
        cost = int(g.bet * INSPECTION_COST_PCT)
        remaining = len(g.car.unrevealed)
        if remaining == 0:
            self.inspect_btn.disabled = True
            self.inspect_btn.label = "🔍 Nothing left to inspect"
        else:
            self.inspect_btn.label = f"🔍 Inspect ({remaining} left, {cost}c)"

    async def on_timeout(self):
        g = self.game
        if g.ended:
            return
        # Auto-part-out so the user doesn't lose everything to inactivity.
        sale = int(g.bet * PART_OUT_PCT)
        add_coins(g.guild_id, g.user_id, sale)
        g.ended = True


class LemonCarFlip(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = LemonData()

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(
            f"Lemon Car Flip loaded — {len(self.data.issues)} issues, "
            f"{len(self.data.features)} features, {len(self.data.car_makes)} makes."
        )

    def _render(self, g: LemonGame, last_event: str | None = None) -> str:
        low, high = g.car.estimate_range()
        revealed = [m for m in g.car.modifiers if m.revealed]
        part_out = int(g.bet * PART_OUT_PCT)

        lines = [
            f"🚗 **{g.user_name}'s Used Car Hustle**",
            f"💰 Paid **{g.bet}c** for **{g.car.name}**.",
            f"🗣️ Seller said: *{g.seller_quip}*",
            "",
            f"**Estimated flip value:** {low}–{high} coins",
            f"**Part-out value:** {part_out}c (guaranteed)",
            f"**Quirks known:** {len(revealed)}/{len(g.car.modifiers)}"
            + (f"  |  **Inspections paid:** {g.inspections_paid}c" if g.inspections_paid else ""),
        ]
        if revealed:
            lines.append("")
            lines.append("**Discovered so far:**")
            for m in revealed:
                sign = "✅" if m.is_feature else "❌"
                pct_str = f"{'+' if m.pct >= 0 else ''}{int(m.pct * 100)}%"
                lines.append(f"  {sign} *{m.flavor}* ({pct_str})")
        if last_event:
            lines.append("")
            lines.append(last_event)
        return "\n".join(lines)

    def _render_final(self, g: LemonGame, sale: int, net: int, flavor: str) -> str:
        revealed = [m for m in g.car.modifiers if m.revealed]
        hidden = [m for m in g.car.modifiers if not m.revealed]

        lines = [
            f"🚗 **{g.user_name}'s Used Car Hustle — SETTLED**",
            f"Car: **{g.car.name}**",
            "",
            flavor,
            "",
            f"💰 **Sale:** {sale}c",
            f"🧾 Paid for car: {g.bet}c",
            f"🔍 Inspection costs: {g.inspections_paid}c",
            f"**Net:** {'+' if net >= 0 else ''}{net}c",
        ]
        if hidden:
            lines.append("")
            lines.append("**Quirks you never found out about:**")
            for m in hidden:
                sign = "✅" if m.is_feature else "❌"
                pct_str = f"{'+' if m.pct >= 0 else ''}{int(m.pct * 100)}%"
                lines.append(f"  {sign} *{m.flavor}* ({pct_str})")
        elif revealed:
            lines.append("")
            lines.append("_(You knew everything there was to know.)_")
        lines.append("")
        lines.append(f"Balance: **{get_coins(g.guild_id, g.user_id)}c**")
        return "\n".join(lines)

    async def _start(self, ctx_or_interaction, bet: int):
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
        jmsg = jail_message(guild.id, user.id)
        if jmsg:
            await reply(jmsg)
            return
        if bet < MIN_BET:
            await reply(f"Down payment is at least **{MIN_BET}c**. Real cars cost real money.")
            return
        if get_coins(guild.id, user.id) < bet:
            await reply(f"You're broke. Balance: **{get_coins(guild.id, user.id)}c**")
            return

        deduct_coins(guild.id, user.id, bet)
        game = LemonGame(self.data, guild.id, user.id, user.display_name, bet)
        view = LemonView(self, game)
        await reply(self._render(game), view=view)

    @commands.command(name="lemon", aliases=["flip", "usedcar", "carflip"])
    @commands.guild_only()
    async def lemon_prefix(self, ctx, bet: int):
        await self._start(ctx, bet)

    @app_commands.command(name="lemon", description="Buy a sketchy used car sight-unseen. Inspect, flip, or part it out.")
    @app_commands.describe(bet="Coins spent on the down payment (min 100)")
    async def lemon_slash(self, interaction: discord.Interaction, bet: int):
        await self._start(interaction, bet)


async def setup(bot):
    await bot.add_cog(LemonCarFlip(bot))
