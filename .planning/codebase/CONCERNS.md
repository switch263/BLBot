# Concerns

_Last mapped: 2026-04-24_

A survey of technical debt, bugs, security smells, and fragile areas — roughly ordered by severity.

## CRITICAL

### 1. Sync SQLite calls block the asyncio event loop
**Files:** `economy.py` (every function), every cog that imports `economy`.
**What:** Every DB operation uses stdlib `sqlite3` synchronously inside `async def` handlers. Each call opens a fresh connection, reads/writes, commits, and closes — all on the event loop thread.
**Why it matters:** under load (multiple players mid-game), the gateway heartbeat can stall, leading to disconnects or delayed message handling. SQLite's lock contention amplifies this.
**Fix direction:** swap to `aiosqlite`, or wrap DB calls with `asyncio.to_thread(...)`. Either way, the module-level helper shape can stay the same if `economy.py` is updated once.

### 2. Non-atomic `transfer_coins`
**File:** `economy.py:226-245`.
**What:** The function runs two separate `UPDATE` statements in the same connection but with two separate `conn.execute()` calls. SQLite's default isolation + the `with` context manager means a crash between debit and credit (process kill, OS OOM, container restart) loses coins. There's no `BEGIN` / `COMMIT` wrapping both updates as a single transaction.
**Fix direction:** wrap in an explicit transaction block (`conn.execute("BEGIN")` / `conn.commit()`), or check that `with sqlite3.connect(...)` actually groups the statements into one transaction (it does, but only if no intermediate `.commit()` is called — verify this).

### 3. Hardcoded privileged user ID in slots
**File:** `cogs/slots.py:177`
**What:** `if user_id == 255560298705059841: amount = 20000` — a specific Discord user gets a guaranteed 20,000-coin daily reward instead of the weighted random roll. No comment explaining who or why.
**Why it matters:** opaque backdoor, undiscoverable without reading the code. If this is the bot author, it's at minimum worth documenting; if it's not, it's a bug. Either way it makes the "daily bonus" unfair and untestable.
**Fix direction:** lift to a config constant with a comment, or remove.

### 4. Hardcoded admin channel ID
**File:** `cogs/admin.py:10`
**What:** `ADMIN_CHANNEL_ID = 401391297211924480` — single Discord channel gates `!coins` (grant arbitrary coins) and `!unjail`. This is environment-specific (tied to one server), so admin commands are silently inoperative on any other server the bot is in.
**Fix direction:** move to `$ADMIN_CHANNEL_ID` env var, or per-guild config, or check Discord role/permissions instead of channel id.

## HIGH

### 5. No test coverage anywhere
See `TESTING.md`. Zero automated tests across ~13.5k lines of Python. Game math (payouts, ace handling, heist rates), economy invariants (transfer atomicity, jail boundaries), and multi-player state machines are all manually verified only.

### 6. In-memory multiplayer state is not durable
**Files:** `cogs/blackjack.py`, `cogs/roulette.py`, `cogs/pigderby.py`, `cogs/clownauction.py`, `cogs/cockroach.py`, and any other `self.active_games = {}` cog.
**What:** Lobbies, turn order, player hands, etc. live only in the cog instance. A bot restart during a game:
- Loses the lobby completely.
- Players who already had coins deducted for buy-in are **not refunded** unless the specific cog has explicit refund logic. Spot-check `blackjack.py` for whether buy-ins are held in escrow or deducted immediately.
**Fix direction:** either persist the minimal state to SQLite (overkill for most games), or ensure every cog implements a consistent "refund on shutdown" pattern — e.g. on `cog_unload`, refund any pending buy-ins.

### 7. f-string SQL (not exploitable today, but a footgun)
**File:** `economy.py:115` — `conn.execute(f"ALTER TABLE wallets ADD COLUMN {col} {decl}")`.
**What:** `col` and `decl` come from a hardcoded literal list inside the function, so it's **not currently a SQL injection**. But the pattern is here, and if someone later parameterizes this from a config file or API input, it becomes one instantly.
**Fix direction:** keep the literal list; add an explicit comment "never pass user input to this f-string," or move to an allowlist approach with identifier quoting.

### 8. Schema migrations are ad-hoc
**File:** `economy.py:102-117`.
**What:** Schema evolution happens via a try/except loop over `ALTER TABLE ... ADD COLUMN`. Works for column-add, but rename, drop, and constraint changes are unsupported. No version tracking — you can't tell what schema version a given DB file is on.
**Fix direction:** introduce a tiny version table (`PRAGMA user_version`) and a list of stepwise migration functions. `alembic` is overkill for SQLite; `yoyo-migrations` is lightweight.

### 9. Default log level is DEBUG in code, INFO in README
**File:** `bot.py:16` — `log_level_str = os.environ.get('LOG_LEVEL', "DEBUG")`. README says default is INFO.
**Why it matters:** misleading, noisy in production, and may leak more info than intended to the log sink (stdout → Docker logs → wherever).
**Fix direction:** align docs and code. Either update README to `DEBUG`, or flip the default to `INFO`.

### 10. No cleanup of abandoned game state
**What:** If a player starts a multiplayer game and everyone walks away, `self.active_games[channel_id]` stays populated forever (or until the next bot restart). A malicious or careless user can accumulate dozens of dead entries — unbounded memory growth over time.
**Fix direction:** each game should have a safety timeout that reliably clears its slot in the dict, even on exception paths.

## MEDIUM

### 11. Game logic and Discord UI mixed in one file
**Files:** `cogs/blackjack.py` (579 lines), `cogs/demoderby.py` (645), `cogs/sunnyvale.py` (544), `cogs/lemon.py` (487), `cogs/pigderby.py` (448), `cogs/chaos.py` (397), `cogs/heist.py` (349), `cogs/weather.py` (323).
**Why it matters:** pure game math lives next to `discord.Embed` rendering and `discord.ui.View` callbacks. Impossible to unit-test without Discord mocks. Refactor would lift pure functions (deck dealing, payout math, state transitions) into adjacent modules (`cogs/blackjack_logic.py`?) that are pure-python and test-friendly.

### 12. No connection pooling
**File:** `economy.py` — every helper does `with sqlite3.connect(DB_FILE) as conn:`. For a command-heavy workload this is a lot of open/close.
**Why it matters:** negligible at current scale, but once combined with the async-blocking issue (concern #1) it's two multiplicative overheads.
**Fix direction:** single long-lived connection (SQLite works fine with one), or move to `aiosqlite` which has its own pooling.

### 13. Slash command sync runs on every `on_ready`
**File:** `bot.py::on_ready`.
**What:** Every reconnection re-syncs slash commands globally and to the dev guild. Discord rate-limits slash command sync to 200/day globally. Frequent reconnects (network blip → discord.py reconnects automatically) could quietly burn the quota.
**Fix direction:** sync only on first `on_ready` per process, or gate on a `COMMANDS_SYNCED` flag.

### 14. `on_command_error` swallows non-CommandNotFound errors
**File:** `bot.py:62-67`.
**What:** Any other exception is just `logger.error(...)`-ed; the user sees nothing. They typed a command, nothing happened, they assume the bot is dead or their input was wrong.
**Fix direction:** at least reply "something broke, check logs" to the user for non-CommandNotFound paths.

### 15. Weather cog re-creates aiohttp session on every call if lost
**File:** `cogs/weather.py:82-84`.
**What:** If `self.session` goes None mid-lifecycle, a new session is created on-the-fly — but the original cog_load already created one with a different connector config. Two overlapping session configs is confusing and might leak connections.
**Fix direction:** pick one creation path; if cog_load fails, error loudly.

### 16. Economy house-id global state
**File:** `economy.py:16` — module-level `_house_id` mutable global.
**Why it matters:** module globals + async + multi-entry (`set_house_id` called from `on_ready` which can run multiple times) = state drift. Currently guarded by an early `if new_id == _house_id: return` check, but a multi-guild deployment where the bot is in two servers could theoretically call this twice with different ids (it won't — bot user id is global — but the guard against it is subtle, not obvious).

## LOW

### 17. README mentions a `tests/` directory that doesn't exist
**File:** `README.md:171` — `└── tests/              # Unit tests`. There is no such directory. Either add it or drop the reference.

### 18. `config.py` has `dbtype = 'sqlite'` that isn't used anywhere meaningful
**File:** `config.py:3`. It's exported and `bot.py` imports it (`from config import dbtype, dbfile`), but `dbtype` is never referenced anywhere. Dead export.

### 19. `bot.py` imports `json` and `random` but neither is used
**File:** `bot.py:5`, `bot.py:8`. Minor, but hints at copy-paste pattern.

### 20. `.gitignore` ignores `config.py*`
**File:** `.gitignore:3` — ignores anything starting with `config.py`. But `config.py` itself **is** committed (it's part of the repo). The pattern works only for `config.py.bak` etc. Worth a comment explaining or a cleanup.

### 21. No `LICENSE` file
Public-facing Discord bot, published Docker image, no license declared. Legal ambiguity for contributors.

### 22. `discord.Intents.all()` is overscoped
**File:** `bot.py:36`. Requests every intent including privileged ones (MessageContent, GuildMembers, Presences). The passive/chaos cogs probably need MessageContent; most others don't. Reducing to the minimum set tightens the attack surface and future-proofs against Discord's intent tightening.

## Not a concern, but worth knowing

- The "house is the bot" design is clever but surprising. Documented implicitly in `economy.py:13-16` — worth surfacing in `ARCHITECTURE.md` (done).
- The `DISABLED_COGS` list in `bot.py:71` is a feature, not debt — the passive chaos cogs are off by default because they're disruptive.
- `0.001%` heist success rate against the bot (`README.md`) is a design choice, not a bug. Still a good thing to have a unit test for in `cogs/heist.py` so the odds don't silently shift.
