# Conventions

_Last mapped: 2026-04-24_

## Language & Style

- **Python 3.12+** (see `Dockerfile` base image and `README.md` setup section).
- **4-space indentation** throughout. No tabs.
- **No linter/formatter config files present** — no `ruff.toml`, `pyproject.toml`, `setup.cfg`, `.flake8`, `.pre-commit-config.yaml`. Style is organic but broadly PEP 8-compliant.
- **No type-checker config** — `mypy`, `pyright`, `pyre` are not configured.

## Type Hints

Type hints are used **selectively but consistently where used**. Public economy functions are fully hinted:

```python
def get_coins(guild_id: int, user_id: int) -> int:
def transfer_coins(guild_id: int, from_id: int, to_id: int, amount: int) -> tuple[int, int]:
def jail_message(guild_id: int, user_id: int) -> str | None:
```

Cogs use hints selectively — command handlers are often untyped because the `commands.Cog` + decorator pattern doesn't require them, but helper methods are usually hinted:

```python
async def _flip(self, guild_id: int, user_id: int, bet: int, call: str) -> discord.Embed:
```

Modern `X | None` union syntax is used (Python 3.10+), not `Optional[X]`.

## Naming

| Kind | Convention | Examples |
|------|-----------|----------|
| Module files | lowercase, no underscores | `coinflip.py`, `raccoonden.py` |
| Classes | `PascalCase` | `CoinFlip`, `RussianRoulette`, `PlayerState` |
| Functions/methods | `snake_case` | `get_coins`, `update_wallet`, `format_hand` |
| Private helpers | `_snake_case` | `_init_db`, `_spin`, `_flip`, `_calculate_payout` |
| Constants | `UPPER_SNAKE_CASE` | `STARTING_COINS`, `MIN_BET`, `LOBBY_SECONDS` |
| Flavor-text lists | `UPPER_SNAKE_CASE` module-level lists | `WIN_MESSAGES`, `LOSE_MESSAGES`, `CLICK_MESSAGES` |

## Module Layout (cog template)

Every cog follows this structure:

```python
import discord
from discord.ext import commands
from discord import app_commands
# stdlib imports
import random, logging, asyncio
# shared service
import economy

logger = logging.getLogger(__name__)

# module-level constants
MIN_BET = 1
STARTING_COINS = 100
WIN_MESSAGES = [...]

class Feature(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}  # in-memory state, if any

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Feature module has been loaded")

    async def _helper(self, guild_id, user_id, bet) -> discord.Embed:
        # guard: jail check
        jmsg = economy.jail_message(guild_id, user_id)
        if jmsg: return discord.Embed(...)
        # guard: bet/balance validation
        # game logic
        # economy.update_wallet(...)
        # return embed

    @commands.command(aliases=[...])
    async def feature(self, ctx, bet: int = None, ...):
        embed = await self._helper(ctx.guild.id, ctx.author.id, bet)
        await ctx.send(embed=embed)

    @app_commands.command(name="feature", description="...")
    async def feature_slash(self, interaction: discord.Interaction, bet: int, ...):
        embed = await self._helper(interaction.guild_id, interaction.user.id, bet)
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Feature(bot))
```

## Dual Command Pattern

Every playable command is registered **twice**: once as `@commands.command` (prefix `!`) and once as `@app_commands.command` (slash `/`). Both delegate to a shared private helper that returns an `Embed`. This is the single most consistent pattern in the codebase.

## Error Handling

**Database operations** are wrapped in `try/except sqlite3.Error` with specific catches:

```python
try:
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(...)
        conn.commit()
except sqlite3.Error as e:
    logger.error(f"Database error <operation>: {e}")
    return dict(_EMPTY_WALLET)  # or 0, False, etc.
```

- Errors are **logged but not propagated** — callers get a sentinel (empty wallet, 0, False, empty list).
- Pattern is repeated ~20 times in `economy.py` — every public function has its own `try/except` block.

**Command-level errors** are handled by `bot.py::on_command_error` with a generic cowboy fallback only for `CommandNotFound`. Other exceptions fall through to the default `discord.py` error logger.

**Validation errors in games** are returned as `discord.Embed(color=Color.red())` to the user, not raised:

```python
if bet < MIN_BET:
    return discord.Embed(description=f"Bet must be at least **{MIN_BET}** coin.", color=discord.Color.red())
```

**No exceptions bubble up to the Discord gateway.** Every command handler swallows its own errors.

## Logging

- `logging` stdlib module only — no `loguru`, `structlog`, or JSON log formatting.
- Per-module logger: `logger = logging.getLogger(__name__)` at every cog's top.
- Global config in `bot.py`: `logging.basicConfig(stream=sys.stdout, level=log_level, format=log_format)`.
- Log level from `$LOG_LEVEL` env var; default is `DEBUG` (in code) despite README claiming `INFO`.
- Format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`.
- Heavy use of `logger.info(f"...")` on cog load and `logger.error(f"...")` in DB except blocks.

## Async Patterns

- All Discord command handlers are `async def`. Correct — `discord.py 2.x` requires this.
- `asyncio.sleep(...)` is used for game timers (buy-in windows, reveal delays).
- `discord.ui.View` + `discord.ui.Button` callbacks for interactive UIs.
- **`sqlite3` calls inside async handlers are synchronous and blocking** — no `aiosqlite`, no thread executor. This is a latent performance bug, not a convention.

## State Management

- **In-memory, per-cog-instance** state: `self.active_games = {}` keyed by `channel_id`. Standard across all multiplayer cogs (`roulette`, `blackjack`, `pigderby`, `clownauction`, `cockroach`).
- **Never persisted** — lost on restart.
- No `threading.Lock` / `asyncio.Lock` around dict access. Protected only by single-threaded asyncio + the fact that commands are handled serially in a single event loop.

## File I/O Conventions

- Plain-text content files (`data_files/*.txt`) are read with `open(..., 'r', encoding='utf-8')` and split by line.
- Paths are built with `os.path.join(os.path.dirname(__file__), ...)` or `Path(__file__).parents[0]`.
- Many cogs re-read data files on every invocation (no caching), which is fine for small files but adds up at scale.

## What the codebase does NOT use

- No dependency injection (cogs hard-import `economy`).
- No data classes / Pydantic models for domain objects — flat `dict`s and tuples throughout.
- No ORM (raw `sqlite3` with f-strings for table names, `?`-placeholders for values).
- No context manager for DB sessions at the cog level — every call opens a new connection.
- No `__all__` exports, no `__init__.py` files in `cogs/` (though `discord.py` loads them fine as a package because there's no import collision).
- No docstrings in most functions — a few key economy functions have one-liners, cogs are mostly uncommented.
