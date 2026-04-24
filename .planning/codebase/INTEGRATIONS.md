# External Integrations

**Analysis Date:** 2026-04-24

## APIs & External Services

**Fun/Info APIs:**
- Chuck Norris Jokes - Random joke facts
  - SDK/Client: aiohttp
  - Endpoint: `https://api.chucknorris.io/jokes/random`
  - Usage: `cogs/chucknorris.py`
  - No auth required

- Urban Dictionary - Word definitions
  - SDK/Client: aiohttp
  - Endpoint: `https://api.urbandictionary.com/v0/define`
  - Usage: `cogs/urban.py`
  - No auth required

- Escape from Tarkov Time - In-game time tracking
  - SDK/Client: aiohttp
  - Endpoint: `https://tarkov-time.adam.id.au/api`
  - Usage: `cogs/tarkov_time.py`
  - No auth required

**Weather API:**
- Discord Weather Service - Weather information
  - SDK/Client: aiohttp with connection pooling and semaphore
  - Endpoint: `https://discord.flvrtown.com`
  - Usage: `cogs/weather.py`
  - Features: 10-second timeout, 10 concurrent request limit, DNS caching
  - No auth required

**Utility Libraries:**
- Lenny Package - Lenny face generation
  - Package: lenny 0.1.3
  - Usage: `cogs/basiccommands.py`
  - No external API calls

## Data Storage

**Databases:**
- SQLite 3
  - Connection: Local file-based (`data/economy.db`, `data/quotes.db`)
  - Client: sqlite3 (Python built-in)
  - No external server required

**File Storage:**
- Local filesystem only
  - Data directory: `data/` (mounted as Docker volume `/app/data`)
  - Data files: `data_files/` (read-only, mounted as `/app/data_files`)
  - Flat text files for game content: derby car parts, BDSM actions, excuses, etc.

**Caching:**
- None - In-memory only, no persistent cache backend

## Authentication & Identity

**Auth Provider:**
- Discord OAuth/Token-based
  - Implementation: discord.py handles Discord authentication
  - Token source: `DISCORD_TOKEN` environment variable
  - Scope: Full bot intents via `discord.Intents.all()`

## Monitoring & Observability

**Error Tracking:**
- None detected

**Logs:**
- Python standard logging to stdout
  - Format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
  - Level: Configurable via `LOG_LEVEL` environment variable (default: INFO)
  - Docker logging: JSON-file driver with rotation (10m max, 3 file limit)

## CI/CD & Deployment

**Hosting:**
- Docker container (Docker Compose)
- Self-hosted or any Docker-compatible platform

**CI Pipeline:**
- GitHub Actions workflow present: `.github/workflows/build_and_push.yaml`
- Build and push container images to registry (likely Docker Hub)

## Environment Configuration

**Required env vars:**
- `DISCORD_TOKEN` - Discord bot token from Discord Developer Portal

**Optional env vars:**
- `DISCORD_GUILD_ID` - Guild ID for instant slash command sync
- `LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `BOT_DATA_DIR` - Custom path for bot data (defaults to `./data`)

**Secrets location:**
- `.env` file (NOT committed to git per `.gitignore`)
- Template: `.env.example`

## Webhooks & Callbacks

**Incoming:**
- Discord message events and slash commands (handled by discord.py)
- HTTP responses from external APIs (non-blocking, async)

**Outgoing:**
- None detected

## External Dependencies at Startup

1. Discord API - Must be reachable to connect bot
2. External API services (chuck norris, urban dictionary, tarkov time, weather) - Called on-demand by commands, graceful error handling if unavailable
3. SQLite database - Local file access required

---

*Integration audit: 2026-04-24*
