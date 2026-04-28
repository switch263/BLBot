import discord
from discord.ext import commands
from discord import app_commands
import random
import string
import sys
import os
import logging
import asyncio
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from economy import get_coins, add_coins, deduct_coins, jail_message

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data_files")

LOBBY_SECONDS = 45
TICK_SECONDS = 2.3
MAX_TICKS = 40
MIN_PLAYERS = 2
MAX_PLAYERS = 8
HP_BAR_WIDTH = 10
EVENT_LOG_DISPLAY = 5
EVENT_LOG_CAP = 40

PERSONALITIES = {
    "aggressor": {
        "emoji": "⚔️",
        "label": "Aggressor",
        "hp": 80,
        "atk_min": 20,
        "atk_max": 45,
        "dmg_taken_mult": 1.20,
        "target_weight": 1.5,
    },
    "turtle": {
        "emoji": "🐢",
        "label": "Turtle",
        "hp": 140,
        "atk_min": 8,
        "atk_max": 22,
        "dmg_taken_mult": 0.65,
        "target_weight": 0.7,
    },
    "wildcard": {
        "emoji": "🎲",
        "label": "Wildcard",
        "hp": 100,
        "atk_min": 5,
        "atk_max": 50,
        "dmg_taken_mult": 1.0,
        "target_weight": 1.0,
        "crit_chance": 0.18,
    },
}

CAR_EMOJIS = ["🚗", "🚙", "🚐", "🛻", "🚕", "🚘", "🏎️", "🚓"]


def _load_lines(filename: str) -> list[str]:
    """Load lines from data_files/<filename>. Blank lines preserved (for weight)."""
    path = os.path.join(DATA_DIR, filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [line.rstrip("\n") for line in f]
    except FileNotFoundError:
        logger.error(f"Derby data file missing: {path}")
        return []


def _compose(template: str, pools: dict[str, list[str]], **overrides) -> str:
    """Fill {token} placeholders — overrides first, then pool lookups, else literal."""
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
        logger.error(f"Derby template format failed for {template!r}: {e}")
        return template


class DerbyData:
    """Holds all demolition derby flavor pools loaded from data_files/."""
    def __init__(self):
        self.car_makes = [s for s in _load_lines("derby_car_makes.txt") if s.strip()]
        # Prefixes/suffixes keep blank lines as weighted "no prefix" / "no suffix".
        self.car_prefixes = _load_lines("derby_car_prefixes.txt")
        self.car_suffixes = _load_lines("derby_car_suffixes.txt")
        self.car_parts = [s for s in _load_lines("derby_car_parts.txt") if s.strip()]
        self.crowd_reactions = [s for s in _load_lines("derby_crowd_reactions.txt") if s.strip()]
        self.driver_quirks = [s for s in _load_lines("derby_driver_quirks.txt") if s.strip()]
        self.collision_templates = [s for s in _load_lines("derby_collision_templates.txt") if s.strip()]
        self.self_events = [s for s in _load_lines("derby_self_events.txt") if s.strip()]
        self.crowd_events = [s for s in _load_lines("derby_crowd_events.txt") if s.strip()]
        self.pileup_templates = [s for s in _load_lines("derby_pileup_templates.txt") if s.strip()]
        self.death_flavor = [s for s in _load_lines("derby_death_flavor.txt") if s.strip()]
        self.win_flavor = [s for s in _load_lines("derby_win_flavor.txt") if s.strip()]
        self.start_quips = [s for s in _load_lines("derby_start_quips.txt") if s.strip()]

        # Shared pools for {token} resolution in any template.
        self.pools = {
            "part": self.car_parts,
            "crowd_reaction": self.crowd_reactions,
            "driver_quirk": self.driver_quirks,
        }

        missing = [name for name, pool in [
            ("car_makes", self.car_makes),
            ("collision_templates", self.collision_templates),
            ("self_events", self.self_events),
            ("crowd_events", self.crowd_events),
            ("pileup_templates", self.pileup_templates),
            ("death_flavor", self.death_flavor),
            ("win_flavor", self.win_flavor),
            ("start_quips", self.start_quips),
        ] if not pool]
        if missing:
            logger.error(f"Derby data pools empty: {missing}")

    def roll_car_name(self, existing: set[str] | None = None) -> str:
        """Roll a unique (within `existing`) random car name from the pools."""
        existing = existing or set()
        for _ in range(25):
            make = random.choice(self.car_makes) if self.car_makes else "Unknown"
            prefix = random.choice(self.car_prefixes).strip() if self.car_prefixes else ""
            suffix = random.choice(self.car_suffixes).strip() if self.car_suffixes else ""
            name = f"{prefix} {make}" if prefix else make
            if suffix:
                name = f"{name} {suffix}"
            name = (name[:1].upper() + name[1:]) if name else make
            if name not in existing:
                return name
        return name  # settle for a dup if we can't find a unique one


def hp_bar(hp: int, max_hp: int) -> str:
    if max_hp <= 0 or hp <= 0:
        return "░" * HP_BAR_WIDTH
    pct = max(0.0, min(1.0, hp / max_hp))
    filled = int(round(pct * HP_BAR_WIDTH))
    return "█" * filled + "░" * (HP_BAR_WIDTH - filled)


class Car:
    def __init__(self, player: discord.Member, personality_key: str, emoji: str, name: str):
        self.player = player
        self.personality = personality_key
        self.emoji = emoji
        self.name = name
        p = PERSONALITIES[personality_key]
        self.max_hp = p["hp"]
        self.hp = p["hp"]
        self.alive = True
        self.death_tick: int | None = None

    def personality_emoji(self) -> str:
        return PERSONALITIES[self.personality]["emoji"]

    def personality_label(self) -> str:
        return PERSONALITIES[self.personality]["label"]

    def roll_attack(self) -> tuple[int, bool]:
        p = PERSONALITIES[self.personality]
        dmg = random.randint(p["atk_min"], p["atk_max"])
        crit = False
        if self.personality == "wildcard" and random.random() < p.get("crit_chance", 0):
            dmg *= 2
            crit = True
        return dmg, crit

    def take(self, raw_dmg: int, tick: int) -> tuple[int, bool]:
        """Apply damage. Returns (dealt, newly_dead)."""
        if not self.alive:
            return 0, False
        p = PERSONALITIES[self.personality]
        dmg = max(1, int(raw_dmg * p["dmg_taken_mult"]))
        self.hp = max(0, self.hp - dmg)
        if self.hp <= 0 and self.alive:
            self.alive = False
            self.death_tick = tick
            return dmg, True
        return dmg, False


class Derby:
    LOBBY = "lobby"
    RACING = "racing"
    DONE = "done"

    def __init__(self, guild_id: int, channel_id: int, host_id: int, buy_in: int):
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.host_id = host_id
        self.buy_in = buy_in
        self.cars: list[Car] = []
        self.players: set[int] = set()
        self.phase = Derby.LOBBY
        self.lobby_deadline = 0.0
        self.message: discord.Message | None = None
        self.timer_task: asyncio.Task | None = None
        self.event_log: list[str] = []

    def alive_cars(self) -> list[Car]:
        return [c for c in self.cars if c.alive]


class JoinPersonalityButton(discord.ui.Button):
    def __init__(self, key: str):
        p = PERSONALITIES[key]
        super().__init__(
            style=discord.ButtonStyle.primary,
            label=f"Join as {p['label']} ({p['hp']}hp, {p['atk_min']}-{p['atk_max']}dmg)",
            emoji=p["emoji"],
            row=0,
        )
        self.key = key

    async def callback(self, interaction: discord.Interaction):
        view: "LobbyView" = self.view  # type: ignore
        d = view.derby
        if d.phase != Derby.LOBBY:
            await interaction.response.send_message("Already started.", ephemeral=True)
            return
        if interaction.user.id in d.players:
            await interaction.response.send_message("You're already in.", ephemeral=True)
            return
        if len(d.cars) >= MAX_PLAYERS:
            await interaction.response.send_message("Arena is full.", ephemeral=True)
            return
        jmsg = jail_message(d.guild_id, interaction.user.id)
        if jmsg:
            await interaction.response.send_message(jmsg, ephemeral=True)
            return
        if get_coins(d.guild_id, interaction.user.id) < d.buy_in:
            await interaction.response.send_message(
                f"Too broke for the **{d.buy_in}c** entry.", ephemeral=True,
            )
            return
        deduct_coins(d.guild_id, interaction.user.id, d.buy_in)
        emoji = CAR_EMOJIS[len(d.cars) % len(CAR_EMOJIS)]
        existing_names = {c.name for c in d.cars}
        name = view.cog.data.roll_car_name(existing_names)
        car = Car(interaction.user, self.key, emoji, name)
        d.cars.append(car)
        d.players.add(interaction.user.id)
        await interaction.response.edit_message(content=view.cog._render_lobby(d), view=view)


class StartButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.success, label="Start", emoji="🏁", row=1)

    async def callback(self, interaction: discord.Interaction):
        view: "LobbyView" = self.view  # type: ignore
        d = view.derby
        if interaction.user.id != d.host_id:
            await interaction.response.send_message("Only the host can start.", ephemeral=True)
            return
        if d.phase != Derby.LOBBY:
            await interaction.response.send_message("Already started.", ephemeral=True)
            return
        if len(d.cars) < MIN_PLAYERS:
            await interaction.response.send_message(
                f"Need at least **{MIN_PLAYERS}** cars on the track.", ephemeral=True,
            )
            return
        await interaction.response.defer()
        if d.timer_task:
            d.timer_task.cancel()
        await view.cog._run_derby(d)


class CancelButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.danger, label="Cancel", emoji="❌", row=1)

    async def callback(self, interaction: discord.Interaction):
        view: "LobbyView" = self.view  # type: ignore
        d = view.derby
        if interaction.user.id != d.host_id:
            await interaction.response.send_message("Only the host can cancel.", ephemeral=True)
            return
        if d.phase != Derby.LOBBY:
            await interaction.response.send_message("Already started.", ephemeral=True)
            return
        for c in d.cars:
            add_coins(d.guild_id, c.player.id, d.buy_in)
        d.phase = Derby.DONE
        if d.timer_task:
            d.timer_task.cancel()
        view.cog.derbies.pop(d.channel_id, None)
        for child in view.children:
            child.disabled = True
        await interaction.response.edit_message(
            content="🛑 Demolition Derby cancelled. Buy-ins refunded.",
            view=view,
        )


class LobbyView(discord.ui.View):
    def __init__(self, cog, derby: Derby):
        super().__init__(timeout=LOBBY_SECONDS + 15)
        self.cog = cog
        self.derby = derby
        self.add_item(JoinPersonalityButton("aggressor"))
        self.add_item(JoinPersonalityButton("turtle"))
        self.add_item(JoinPersonalityButton("wildcard"))
        self.add_item(StartButton())
        self.add_item(CancelButton())


class DemoDerby(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = DerbyData()
        self.derbies: dict[int, Derby] = {}

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(
            f"Demolition Derby loaded — {len(self.data.collision_templates)} collisions, "
            f"{len(self.data.death_flavor)} deaths, {len(self.data.car_makes)} makes, "
            f"{len(self.data.crowd_reactions)} crowd reactions."
        )

    # ---------- Rendering ----------

    def _render_lobby(self, d: Derby) -> str:
        lines = [
            "💥 **DEMOLITION DERBY — LOBBY** 💥",
            f"Entry: **{d.buy_in}c**  |  Cars: **{len(d.cars)}/{MAX_PLAYERS}**  |  "
            f"Pot: **{d.buy_in * len(d.cars)}c**",
            f"Starts <t:{int(d.lobby_deadline)}:R> (host can start early).",
            "",
            "**Personalities:**",
            "⚔️ **Aggressor** — 80hp · 20-45dmg · glass cannon (+20% dmg taken)",
            "🐢 **Turtle** — 140hp · 8-22dmg · armor (−35% dmg taken)",
            "🎲 **Wildcard** — 100hp · 5-50dmg · 18% crit (2× dmg)",
            "",
        ]
        if d.cars:
            lines.append("**On the starting line:**")
            for c in d.cars:
                lines.append(
                    f"{c.emoji} **{c.name}** — {c.personality_emoji()} {c.personality_label()} "
                    f"({c.max_hp}hp) — {c.player.display_name}"
                )
        else:
            lines.append("_No cars yet. Click a personality button to join._")
        return "\n".join(lines)

    def _render_arena(self, d: Derby, header: str) -> str:
        lines = [header, ""]
        width = min(36, max((len(c.name) for c in d.cars), default=20))
        for c in d.cars:
            display_name = (c.name[:width - 1] + "…") if len(c.name) > width else c.name
            if c.alive:
                bar = hp_bar(c.hp, c.max_hp)
                hp_str = f"{c.hp:>3}/{c.max_hp}"
                status = f"{c.personality_emoji()} {c.personality_label()}"
            else:
                bar = hp_bar(0, c.max_hp)
                hp_str = f"  0/{c.max_hp}"
                status = "💥 WRECKED"
            lines.append(
                f"{c.emoji} `{display_name:<{width}}` `[{bar}]` `{hp_str}` {status} — {c.player.display_name}"
            )
        if d.event_log:
            lines.append("")
            lines.append("**Recent action:**")
            lines.extend(d.event_log[-EVENT_LOG_DISPLAY:])
        return "\n".join(lines)

    # ---------- Combat ----------

    def _pick_attacker(self, alive: list[Car]) -> Car:
        weights = [PERSONALITIES[c.personality]["target_weight"] for c in alive]
        return random.choices(alive, weights=weights, k=1)[0]

    def _format_car_ref(self, c: Car) -> str:
        return f"{c.emoji} {c.name}"

    def _compose_event(self, template: str, **overrides) -> str:
        return _compose(template, self.data.pools, **overrides)

    def _do_collision(self, d: Derby, tick: int) -> list[str]:
        alive = d.alive_cars()
        if len(alive) < 2:
            return []
        attacker = self._pick_attacker(alive)
        defender = random.choice([c for c in alive if c is not attacker])
        dmg, crit = attacker.roll_attack()
        tpl = random.choice(self.data.collision_templates) if self.data.collision_templates else "💥 {A} rams {B} for {dmg}."
        mutual = "each" in tpl or "Both take" in tpl
        dealt, newly_dead = defender.take(dmg, tick)
        line = self._compose_event(
            tpl,
            A=self._format_car_ref(attacker),
            B=self._format_car_ref(defender),
            dmg=str(dealt),
        )
        if crit:
            line += " 💢 CRIT!"
        events = [line]
        if mutual:
            back_dealt, back_dead = attacker.take(int(dmg * 0.6), tick)
            events.append(
                f"↩️ **{self._format_car_ref(attacker)}** takes **{back_dealt}** back from the impact."
            )
            if back_dead:
                events.append(self._compose_event(
                    random.choice(self.data.death_flavor),
                    name=self._format_car_ref(attacker),
                ))
        if newly_dead:
            events.append(self._compose_event(
                random.choice(self.data.death_flavor),
                name=self._format_car_ref(defender),
            ))
        return events

    def _do_self_event(self, d: Derby, tick: int) -> list[str]:
        alive = d.alive_cars()
        if not alive:
            return []
        car = random.choice(alive)
        raw = random.randint(10, 25)
        dealt, newly_dead = car.take(raw, tick)
        tpl = random.choice(self.data.self_events) if self.data.self_events else "🔥 {A} self-damages for {dmg}."
        events = [self._compose_event(tpl, A=self._format_car_ref(car), dmg=str(dealt))]
        if newly_dead:
            events.append(self._compose_event(
                random.choice(self.data.death_flavor),
                name=self._format_car_ref(car),
            ))
        return events

    def _do_crowd_event(self, d: Derby, tick: int) -> list[str]:
        alive = d.alive_cars()
        if not alive:
            return []
        car = random.choice(alive)
        raw = random.randint(8, 22)
        dealt, newly_dead = car.take(raw, tick)
        tpl = random.choice(self.data.crowd_events) if self.data.crowd_events else "🎪 {A} gets distracted for {dmg}."
        events = [self._compose_event(tpl, A=self._format_car_ref(car), dmg=str(dealt))]
        if newly_dead:
            events.append(self._compose_event(
                random.choice(self.data.death_flavor),
                name=self._format_car_ref(car),
            ))
        return events

    def _do_pileup(self, d: Derby, tick: int) -> list[str]:
        alive = d.alive_cars()
        if len(alive) < 3:
            return []
        n = min(len(alive), random.randint(3, 5))
        victims = random.sample(alive, n)
        raw = random.randint(15, 30)
        names = ", ".join(f"**{self._format_car_ref(v)}**" for v in victims)
        tpl = random.choice(self.data.pileup_templates) if self.data.pileup_templates else "💥 PILEUP: {names} take {dmg}."
        events = [self._compose_event(tpl, names=names, dmg=str(raw))]
        for v in victims:
            _, newly_dead = v.take(raw, tick)
            if newly_dead:
                events.append(self._compose_event(
                    random.choice(self.data.death_flavor),
                    name=self._format_car_ref(v),
                ))
        return events

    # ---------- Flow ----------

    async def _start_derby(self, ctx_or_interaction, bet: int):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild
        channel = ctx_or_interaction.channel
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
        if bet <= 0:
            await reply("Buy-in must be > 0.")
            return
        if channel.id in self.derbies:
            await reply("A derby is already running in this channel.")
            return
        if get_coins(guild.id, user.id) < bet:
            await reply(f"You're broke. Balance: **{get_coins(guild.id, user.id)}c**")
            return

        d = Derby(guild.id, channel.id, user.id, bet)
        d.lobby_deadline = time.time() + LOBBY_SECONDS
        self.derbies[channel.id] = d

        view = LobbyView(self, d)
        msg = await reply(self._render_lobby(d), view=view)
        d.message = msg
        d.timer_task = asyncio.create_task(self._lobby_timer(d))

    async def _lobby_timer(self, d: Derby):
        try:
            delay = d.lobby_deadline - time.time()
            if delay > 0:
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        if d.phase != Derby.LOBBY:
            return
        if len(d.cars) < MIN_PLAYERS:
            for c in d.cars:
                add_coins(d.guild_id, c.player.id, d.buy_in)
            d.phase = Derby.DONE
            self.derbies.pop(d.channel_id, None)
            if d.message:
                try:
                    await d.message.edit(
                        content=f"🛑 Derby cancelled — need at least **{MIN_PLAYERS}** cars. Buy-ins refunded.",
                        view=None,
                    )
                except discord.HTTPException:
                    pass
            return
        await self._run_derby(d)

    async def _run_derby(self, d: Derby):
        d.phase = Derby.RACING
        pot = d.buy_in * len(d.cars)
        start_quip = random.choice(self.data.start_quips) if self.data.start_quips else "The race begins."
        try:
            await d.message.edit(
                content=self._render_arena(
                    d, f"🏁 **THE DERBY BEGINS** — _{start_quip}_  |  Pot: **{pot}c**"
                ),
                view=None,
            )
        except discord.HTTPException:
            pass
        await asyncio.sleep(TICK_SECONDS)

        for tick in range(1, MAX_TICKS + 1):
            alive = d.alive_cars()
            if len(alive) <= 1:
                break
            num_events = 1 if len(alive) <= 2 else random.choice([1, 2, 2, 3])
            for _ in range(num_events):
                roll = random.random()
                if roll < 0.60:
                    events = self._do_collision(d, tick)
                elif roll < 0.80:
                    events = self._do_crowd_event(d, tick)
                elif roll < 0.94:
                    events = self._do_self_event(d, tick)
                else:
                    events = self._do_pileup(d, tick) or self._do_collision(d, tick)
                if events:
                    d.event_log.extend(events)
                    if len(d.event_log) > EVENT_LOG_CAP:
                        d.event_log = d.event_log[-EVENT_LOG_CAP:]
                if len(d.alive_cars()) <= 1:
                    break

            header = f"💥 **DEMOLITION DERBY** — Tick **{tick}**  |  Pot: **{pot}c**"
            try:
                await d.message.edit(content=self._render_arena(d, header))
            except discord.HTTPException:
                pass
            if len(d.alive_cars()) <= 1:
                break
            await asyncio.sleep(TICK_SECONDS)

        # Sudden death if time runs out with >1 alive: kill weakest until 1 remains.
        while len(d.alive_cars()) > 1:
            weakest = min(d.alive_cars(), key=lambda c: c.hp)
            weakest.hp = 0
            weakest.alive = False
            weakest.death_tick = MAX_TICKS + 1
            d.event_log.append(
                f"⏰ **Time called** — officials declare **{self._format_car_ref(weakest)}** wrecked."
            )
            d.event_log.append(self._compose_event(
                random.choice(self.data.death_flavor),
                name=self._format_car_ref(weakest),
            ))

        alive = d.alive_cars()
        if alive:
            winner = alive[0]
        else:
            # Everyone died in a single sweep — whoever died last (highest tick) takes it.
            winner = max(d.cars, key=lambda c: (c.death_tick or 0))

        add_coins(d.guild_id, winner.player.id, pot)
        d.phase = Derby.DONE
        self.derbies.pop(d.channel_id, None)

        win_line = self._compose_event(
            random.choice(self.data.win_flavor) if self.data.win_flavor else "🏆 {name} wins.",
            name=self._format_car_ref(winner),
        )
        final_header = (
            f"🏆 **{self._format_car_ref(winner)}** WINS THE DEMOLITION DERBY!\n"
            f"_{win_line}_\n"
            f"**{winner.player.display_name}** takes the **{pot}c** pot."
        )
        try:
            await d.message.edit(content=self._render_arena(d, final_header))
        except discord.HTTPException as e:
            logger.error(f"Failed to finalize derby: {e}")

    @commands.command(name="demoderby", aliases=["demo", "smash", "roadrage", "demolition"])
    @commands.guild_only()
    async def derby_prefix(self, ctx, bet: int):
        await self._start_derby(ctx, bet)

    @app_commands.command(name="demoderby", description="Multiplayer demolition derby. Last car running takes the pot.")
    @app_commands.describe(bet="Entry fee per player")
    async def derby_slash(self, interaction: discord.Interaction, bet: int):
        await self._start_derby(interaction, bet)


async def setup(bot):
    await bot.add_cog(DemoDerby(bot))
