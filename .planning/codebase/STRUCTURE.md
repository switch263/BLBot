# Structure

_Last mapped: 2026-04-24_

## Directory Tree (top 3 levels)

```
BLBot/
├── bot.py                        # Entry point: cog loader, slash sync, error handler
├── economy.py                    # Shared coin/wallet/jail/stats service (all games use this)
├── config.py                     # dbtype, DATA_DIR, dbfile (quotes.db path)
├── requirements.txt              # Python deps (pinned with >=)
├── Dockerfile                    # python:3.12-slim base
├── docker-compose.yml            # Single service + volume mounts
├── .dockerignore
├── .env.example                  # DISCORD_TOKEN, LOG_LEVEL, DISCORD_GUILD_ID
├── .gitignore                    # Ignores data/, .env, config.py*, *.db, __pycache__
├── README.md                     # User-facing feature list and setup
├── .github/workflows/
│   └── build_and_push.yaml       # GHCR Docker build on push/tag to main/master
├── cogs/                         # ~80 plugin modules, one feature per file
│   ├── admin.py                  # Admin-channel-gated commands
│   ├── basiccommands.py          # /ping, /roll, /choose, /joined, /lenny
│   ├── help.py                   # Paginated help embed (8 pages)
│   ├── info.py
│   ├── economy games/            #  (not a folder — flat in cogs/, listed by role)
│   │   slots, coinflip, blackjack, highlow, vault, casinoroulette,
│   │   roulette, heist, pigderby, cockroach, clownauction,
│   │   raccoonden, bigfoot, hotdog, pawnshop, wheelofmisfortune,
│   │   vendingmachine, sushi, methgator, sunnyvale, mayorelection,
│   │   duisim, trollbridge, lemon, pickup, demoderby
│   ├── earning/                  #  lootdrop, gift, richest, vault
│   ├── generators/               #  insult, roast, floridaman, conspiracy,
│   │                             #  therapy, thought, advice, excuse,
│   │                             #  headline, chucknorris, fortune, bdsm
│   ├── text/                     #  mock, clap, vaporwave, zalgo, emojify,
│   │                             #  soup, zalgo
│   ├── social/                   #  fight, slap, donger, rekt, villain,
│   │                             #  lifestats, randomquote, quotes
│   ├── utility/                  #  weather, xkcd, urban, tarkov_time,
│   │                             #  temperature, serverstats
│   ├── passive (disabled)/       #  chaos, gaslight, dadbot, faketyping,
│   │                             #  lurkercallout, selectivememory, unhinged,
│   │                             #  typopolice, phantomping
│   └── meme images/              #  lasaga, pineapple, ohio, hf, lenny
├── data_files/                   # ~40 plain-text content files (read-only at runtime)
│   ├── insults.txt, savage_insults.txt
│   ├── thoughts.txt, therapy_responses.txt, unhinged_replies.txt
│   ├── floridaman_actions.txt, floridaman_footers.txt
│   ├── bad_advice.txt, fake_quotes.txt
│   ├── excuse_{starters,actions,subjects,extras}.txt
│   ├── fakequote_{starters,actions,endings}.txt
│   ├── bdsm_{templates,actions,toys,traps}.txt
│   ├── derby_{car_makes,car_parts,collision_templates,...}.txt
│   ├── lemon_{car_makes,features,issues,...}.txt
│   └── (all plain-text, one entry per line or templated tokens)
└── data/                         # gitignored — runtime SQLite databases
    ├── economy.db                # wallets, jail, loot_cooldowns
    └── quotes.db                 # (path from config.py)
```

## Key Locations

| What | Where | Notes |
|------|-------|-------|
| Entry point | `bot.py` | `asyncio.run(main())` |
| Cog discovery | `bot.py::load_extensions` | `os.listdir('cogs/')`, filters `_` prefix and `DISABLED_COGS` |
| Disabled-by-default cogs | `bot.py:71` (`DISABLED_COGS` list) | `faketyping`, `lurkercallout`, `villain`, `unhinged`, `typopolice`, `selectivememory`, `dadbot` |
| Coin/wallet service | `economy.py` | Single shared module; all gambling cogs `import economy` |
| House wallet | `economy.py::_house_id` | Bot's own Discord user_id after `set_house_id` runs in `on_ready` |
| Admin channel ID | `cogs/admin.py:10` | Hardcoded `401391297211924480` |
| DB path | `config.py::DATA_DIR` | `$BOT_DATA_DIR` env var, else `./data/` |
| Content data files | `data_files/*.txt` | Read by generator cogs; append-only, `!reload` picks up |
| Logging config | `bot.py:16-27` | Log level from `$LOG_LEVEL`, defaults to `DEBUG` |
| Slash command sync | `bot.py::on_ready` | Global + per-guild if `$DISCORD_GUILD_ID` set |
| CI | `.github/workflows/build_and_push.yaml` | Docker build → `ghcr.io/<repo>`, triggered on push to main/master and version tags |

## Naming Conventions

**Files:**
- `cogs/<feature>.py` — one feature per file, lowercase, no underscores in names (`coinflip.py`, `raccoonden.py`, not `coin_flip.py`).
- `data_files/<feature>_<slot>.txt` — underscore-separated, e.g. `fakequote_starters.txt`, `lemon_car_makes.txt`.
- Test files: none exist.

**Classes:**
- PascalCase matching the cog's conceptual name. Not always matching the filename:
  - `cogs/coinflip.py` → `class CoinFlip`
  - `cogs/roulette.py` → `class RussianRoulette`
  - `cogs/admin.py` → `class Admin`
  - `cogs/blackjack.py` → `class Blackjack` + `class PlayerState` + view classes

**Functions / methods:**
- `snake_case` throughout.
- Private helpers prefixed with `_`: `_init_db`, `_spin`, `_flip`, `_calculate_payout`.
- Dual-register pattern: `coinflip` (prefix) + `coinflip_slash` (slash) both call a shared `_flip` helper.

**Constants:**
- `UPPER_SNAKE_CASE` at module top: `STARTING_COINS`, `MIN_BET`, `MAX_PLAYERS`, `LOBBY_SECONDS`, `CHAMBER_SIZE`.
- Flavor-text lists are module-level constants too: `WIN_MESSAGES`, `LOSE_MESSAGES`, `CLICK_MESSAGES`.

**Setup function:**
- Every cog ends with `async def setup(bot): await bot.add_cog(<ClassName>(bot))`.

## Adding New Code

**New cog:** drop `cogs/<name>.py` matching the template in `README.md:191-214`. Auto-loads on next restart. Must export `async def setup(bot)`.

**New game that uses coins:** `import economy`. Always call `economy.jail_message(...)` first to gate play. Call `economy.update_wallet(guild_id, user_id, delta)` to settle (delta is signed — positive = won, negative = lost).

**New content for an existing generator:** append lines to the matching `data_files/*.txt`. No code change needed. Run `!reload` if the generator caches on load (most don't).

**New passive/background cog:** write it like a normal cog but use `@tasks.loop(...)` (or an `asyncio.create_task` in `cog_load`). Consider adding the name to `DISABLED_COGS` in `bot.py` so it doesn't auto-load in fresh deployments.

**New admin command:** add to `cogs/admin.py`, gated on `ctx.channel.id != ADMIN_CHANNEL_ID` at the top of the handler.

## What's Conspicuously Missing

- `tests/` directory does not exist (README mentions it but repo has none).
- No `pyproject.toml`, `setup.py`, `pyproject.cfg`, `ruff.toml`, `.pre-commit-config.yaml`, or other Python tooling configs.
- No type-checker config (no `mypy.ini`, `pyrightconfig.json`).
- No logging config file — all logging is configured inline in `bot.py`.
- No `CONTRIBUTING.md`, `CHANGELOG.md`, or `LICENSE` at the repo root.
- No database migration framework (Alembic, yoyo) — schema evolution is ad-hoc in `economy.py::_init_db`.
