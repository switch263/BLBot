# Testing

_Last mapped: 2026-04-24_

## Critical Finding: No Automated Tests

**The codebase has zero automated test coverage.**

- No `tests/` directory (README references one at `BLBot/tests/` but no such directory exists on disk).
- No `test_*.py` or `*_test.py` files anywhere in the repo.
- No test framework in `requirements.txt`: no `pytest`, no `unittest`-specific extras, no `hypothesis`, no `coverage`.
- No `pyproject.toml` test config, no `pytest.ini`, no `tox.ini`, no `conftest.py`.
- No CI test step — the only GitHub Actions workflow (`.github/workflows/build_and_push.yaml`) only builds and pushes Docker images. It does not run any test command.

All verification today is **manual**: run the bot, play a command in Discord, eyeball the embed.

## What Would Be Testable Today

The codebase has good structural candidates for unit testing despite the zero coverage:

**Pure functions (easy wins, no mocks needed):**
- `cogs/blackjack.py::card_value`, `hand_total`, `is_blackjack`, `format_card`, `format_hand`, `new_deck`
- `cogs/slots.py::_spin` (random, but outcomes can be asserted with seed), `_calculate_payout`
- `cogs/coinflip.py::CoinFlip._flip` (needs economy stubbing)
- Various generator string templates in `cogs/insult.py`, `cogs/excuse.py`, `cogs/floridaman.py` (once data file paths are parameterized)

**Database service (needs in-memory SQLite):**
- `economy.py` — all 20+ functions are good pytest candidates. SQLite supports `:memory:` or a per-test temp file. The existing design (fresh `sqlite3.connect(DB_FILE)` per call) actually makes testing easier than a shared-connection pattern would.
- Coverage-worthy: `transfer_coins` atomicity, `jail_remaining` boundary conditions, `set_house_id` legacy migration, `get_leaderboard` house-exclusion logic.

**Multi-player game state (needs Discord mocks):**
- `cogs/blackjack.py::PlayerState`, split/double logic, dealer reveal
- `cogs/roulette.py` lobby state machine
- `cogs/pigderby.py` odds / payouts

## What's Hard to Test As-Is

- **Discord-coupled UX code**: view callbacks, button interactions, embed layout. Testing requires mocking `discord.Interaction`, `discord.ui.Button`, etc. `dpytest` exists but is not set up.
- **`economy.py`'s hard-coded `DB_FILE = os.path.join(DATA_DIR, "economy.db")`** — no way to inject a test path without monkeypatching the module global. A `set_db_file()` hook or `DB_FILE = os.environ.get("ECONOMY_DB", ...)` would unlock everything.
- **`cogs/admin.py`'s hardcoded `ADMIN_CHANNEL_ID = 401391297211924480`** — same problem. No way to override without editing source.
- **`cogs/slots.py:177`'s hardcoded privileged user ID `255560298705059841`** — a test would need to monkeypatch this constant.

## High-Priority Coverage Gaps

Ordered by business impact:

1. **`economy.transfer_coins`** — not atomic under the current SQLite config (each `conn.execute` auto-commits). A crash between the debit and credit lines leaves coins lost. A test that kills the process mid-transfer would prove this.
2. **`economy.update_wallet`** — the positive/negative branch logic with `is_jackpot` is easy to get wrong. Needs explicit assertions on `total_won`/`total_lost`/`spins`/`jackpots` increments.
3. **Blackjack ace handling** — `hand_total` soft/hard ace adjustment. Multiple aces in one hand + splits + doubles is a bug farm.
4. **Slots payout math** — `PAYOUTS` table * `bet` with 8 symbols and weighted distribution. Off-by-one or weight-sum drift would go unnoticed.
5. **Multi-player lobby state machines** — `blackjack`, `roulette`, `pigderby`, `cockroach`. State transitions under timeouts and player dropouts are untested and likely have edge cases.
6. **Jail gate** — every gambling cog calls `economy.jail_message`. One missing call is an exploit. A test that enumerates all `cogs/*.py` and asserts the call exists would catch regressions.
7. **`economy._init_db` migrations** — the `ALTER TABLE ... ADD COLUMN` blocks should be tested on a pre-migration schema snapshot.

## If You Add Tests

Recommended stack:
- `pytest` + `pytest-asyncio` (for async command handlers).
- `dpytest` for integration-style cog tests (Discord mocks are its whole job).
- In-memory SQLite: `sqlite3.connect(":memory:")` for unit tests of `economy.py`. Requires parameterizing `DB_FILE` first.
- `pytest-cov` for coverage reporting.
- Wire into CI: add a `test` job to `.github/workflows/build_and_push.yaml` that runs before the build.

Minimum viable first test file would be `tests/test_economy.py` covering wallet CRUD and jail lifecycle — no Discord mocks needed if `DB_FILE` is parameterizable.
