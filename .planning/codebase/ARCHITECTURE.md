# Architecture

_Last mapped: 2026-04-24_

## System Overview

BLBot is a Python Discord bot built on `discord.py 2.4+` using the **cog plugin pattern**. The bot runs as a single long-lived process that discovers, loads, and dispatches commands across ~80 plugin modules ("cogs"). Each cog is a self-contained subsystem (a game, a generator, an admin tool). A single shared `economy.py` module acts as the database/service layer for all coin-based games.

**Runtime model:** single-process asyncio event loop. No background workers, no message queue, no external scheduler.

**Persistence model:** SQLite files on a mounted volume (`data/`). No migrations framework — DDL is in-code idempotent `CREATE TABLE IF NOT EXISTS` + opportunistic `ALTER TABLE` in `economy.py::_init_db()`.

**Deployment:** Docker Compose on a VPS. Single container, volume mounts for `data/` (rw) and `data_files/` (ro). GitHub Actions builds and pushes the image to `ghcr.io` on push to `main`/`master` and on version tags.

## Architectural Pattern

**Plugin architecture (cogs) over shared service layer.**

```
┌─────────────────────────────────────────────────────┐
│                     bot.py                          │
│  • asyncio entrypoint                               │
│  • discord.ext.commands.Bot (prefix '!' + slash)    │
│  • cog discovery via os.listdir('cogs/')            │
│  • on_ready: set_house_id, bot.tree.sync            │
│  • on_command_error: cowboy fallback                │
└────────────┬────────────────────────────────────────┘
             │ load_extension('cogs.<name>')
             ▼
┌─────────────────────────────────────────────────────┐
│                   cogs/<name>.py                    │
│  class <Name>Cog(commands.Cog):                     │
│    @commands.command    (! prefix)                  │
│    @app_commands.command (/ slash, dual-registered) │
│                                                     │
│  Plugin categories:                                 │
│    • Casino games         (slots, blackjack, ...)   │
│    • Push-your-luck       (raccoonden, bigfoot, ...)│
│    • Multiplayer/PvP      (roulette, heist, ...)    │
│    • Generators           (insult, floridaman, ...) │
│    • Utility              (weather, xkcd, urban)    │
│    • Passive/background   (chaos, gaslight, dadbot) │
│    • Admin                (admin.py)                │
└────────────┬────────────────────────────────────────┘
             │ import economy
             ▼
┌─────────────────────────────────────────────────────┐
│                   economy.py                        │
│  Coin wallet service                                │
│    get_wallet / get_coins / add / deduct / transfer │
│  Pot (bot = house) — set_house_id, get_pot          │
│  Stats — record_roulette, record_rr, record_heist   │
│  Jail — jail_user / unjail / jail_message           │
│  Leaderboard — get_leaderboard, get_server_stats    │
└────────────┬────────────────────────────────────────┘
             │ sqlite3.connect(DB_FILE)
             ▼
┌─────────────────────────────────────────────────────┐
│         data/economy.db   (wallets, jail, loot)     │
│         data/quotes.db    (quotes cog)              │
└─────────────────────────────────────────────────────┘
```

## Layers

There are three implicit layers, though no enforcement boundary:

1. **Bootstrap / dispatch layer** — `bot.py`, `config.py`. Loads environment, configures logging, discovers cogs, routes Discord events.
2. **Feature layer** — `cogs/*.py`. One file per feature. Each cog owns its UX (embeds, buttons, message flow) and game logic. In-memory state (active lobbies, turn order) is kept on the cog instance (`self.active_games = {}` keyed by `channel_id`).
3. **Shared service layer** — `economy.py` for coins/jail/stats. `data_files/*.txt` as a flat "content store" read by generator cogs.

No ORM. No DI container. No explicit interface/abstraction between cogs and `economy` — cogs just `import economy` and call module-level functions.

## Data Flow

**Command flow (typical game):**

```
User types "!coinflip 50 heads" in Discord
  → discord.py gateway → bot.on_message
  → prefix router → cogs.coinflip.CoinFlip.coinflip(ctx, bet, call)
  → economy.jail_message(guild_id, user_id)          # gate
  → economy.get_coins(guild_id, user_id)             # balance check
  → random.choice(...)                                # game outcome
  → economy.update_wallet(guild_id, user_id, ±bet)   # settle
  → ctx.send(embed=...)                              # render result
```

**Dual-command pattern:** nearly every cog registers the same command twice — once as `@commands.command` (prefix `!`) and once as `@app_commands.command` (slash `/`). Both usually delegate to a shared private helper (e.g. `CoinFlip._flip`) that returns a `discord.Embed`.

**Multiplayer / lobby flow:**

```
!blackjack 100   (first player)
  → cog stores lobby state in self.active_games[channel_id]
  → buy-in window (60s) via asyncio.sleep / discord.ui.View
  → other players react/click to join
  → state machine: deal → each player's turn (View) → dealer → settle
  → economy.add_coins / deduct_coins per player
  → clear self.active_games[channel_id]
```

In-memory state is **not durable**. A bot restart during an active multiplayer game loses the lobby; buy-ins that were already deducted stay deducted unless the cog has explicit refund logic.

## Abstractions

**Shared service: `economy.py`**
- Stateless-ish module (one module-global: `_house_id`).
- Every function opens a new `sqlite3.connect(DB_FILE)` with a `with` block (auto-commit on exit).
- Return shape is either a primitive (`int`, `bool`) or a flat `dict`. No domain objects.
- The "house" wallet is the bot's own Discord user_id — the bot literally is a player in its own economy.
- `_LEGACY_HOUSE_ID = 0` exists because the house was once a sentinel user_id 0. `set_house_id()` migrates balances from 0 to the real bot id on startup.

**Jail gate:** every gambling cog calls `economy.jail_message(guild_id, user_id)` at the top of its command handler. If the return is non-None, the cog renders that string and bails. This is the canonical "is the user allowed to gamble right now" check.

**Generator pattern:** cogs like `cogs/insult.py`, `cogs/floridaman.py`, `cogs/excuse.py` read one or more `data_files/*.txt` files and combine lines randomly. New content = append lines to the text file + `!reload` (no code change).

**View-based UIs:** interactive cogs (`blackjack`, `vault`, `highlow`, `pigderby`) use `discord.ui.View` subclasses with `discord.ui.Button` callbacks for player choices. Timeouts are set per-view.

## Entry Points

| Path | Role |
|------|------|
| `bot.py` | Main async entry. `if __name__ == '__main__': asyncio.run(main())` |
| `bot.py::load_extensions` | Scans `cogs/*.py`, skips `DISABLED_COGS`, loads via `bot.load_extension` |
| `bot.py::on_ready` | Sets house id, syncs slash commands globally + to `DISCORD_GUILD_ID` if set |
| `bot.py::on_command_error` | Generic fallback that responds "Not a thing I know how to do, partner!" on `CommandNotFound` |
| `cogs/*.py::setup(bot)` | Every cog exposes `async def setup(bot): await bot.add_cog(...)` |
| `cogs/admin.py` | Admin-channel-gated commands (`!coins`, `!unjail`) — hardcoded `ADMIN_CHANNEL_ID = 401391297211924480` |
| `economy.py::_init_db` | Runs at import time (imported by `bot.py`), creates tables and runs column-add migrations |

## Key Architectural Constraints

- **Single process, single guild optimization** — most schemas have `(guild_id, user_id)` composite keys, but in-memory state (`self.active_games`) is keyed by `channel_id` only. Cross-guild channel ID collisions are theoretically possible but unlikely.
- **No auth layer beyond Discord** — all permission checks are Discord-native (`ADMIN_CHANNEL_ID`, channel permissions, etc).
- **No rate limiting beyond Discord's own gateway limits** — individual cogs may implement per-user cooldowns (daily, loot) via DB timestamps.
- **Disabled-by-default passive chaos cogs** — `DISABLED_COGS` in `bot.py` excludes `faketyping`, `lurkercallout`, `villain`, `unhinged`, `typopolice`, `selectivememory`, `dadbot` from auto-load. Admin can load them manually if the admin cog allows it.
- **Slash command sync has two modes** — global (eventual consistency, ~1h) and guild-scoped (instant). Both happen on every `on_ready` if `DISCORD_GUILD_ID` is set.

## What's NOT in this architecture

- No tests / CI test step (CI only builds Docker images).
- No metrics, tracing, or health endpoint.
- No database migration framework — schema evolution is append-only via `ALTER TABLE ... IF NOT EXISTS`-style try/except blocks in `economy._init_db()`.
- No caching layer — SQLite is hit on every command.
- No background task scheduler other than `discord.ext.tasks` loops (used in a few passive cogs like `chaos.py`, `gaslight.py`).
- No web API. No admin UI. Admin is Discord commands gated by `ADMIN_CHANNEL_ID`.
