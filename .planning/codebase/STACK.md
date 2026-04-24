# Technology Stack

**Analysis Date:** 2026-04-24

## Languages

**Primary:**
- Python 3.12 - Entire bot application

## Runtime

**Environment:**
- Python 3.12 (as specified in `Dockerfile`)

**Package Manager:**
- pip3
- Lockfile: requirements.txt (present)

## Frameworks

**Core:**
- discord.py 2.4.0 - Discord bot framework with async support

**Testing:**
- Not detected

**Build/Dev:**
- Docker - Containerization for deployment
- Docker Compose 3.8 - Multi-service orchestration

## Key Dependencies

**Critical:**
- discord.py 2.4.0 - Discord bot client and command framework
- aiohttp 3.11.11 - Async HTTP client for external API requests
- lenny 0.1.3 - Utility package for lenny face generation

**Infrastructure:**
- websockets 14.1 - WebSocket support for Discord connections
- aiosignal 1.3.1 - Signal support for async operations
- async-timeout 5.0.1 - Timeout management for async operations
- asyncio (stdlib) - Async/await runtime

**Networking & Encoding:**
- urllib3 2.3.0 - HTTP client pooling and utilities
- certifi 2024.12.14 - CA bundle for SSL/TLS validation
- chardet 5.2.0 - Character encoding detection
- charset-normalizer 3.4.1 - Character set normalization
- idna 3.10 - Internationalized domain names support

**Data Structures:**
- frozenlist 1.5.0 - Immutable list implementation
- multidict 6.1.0 - Multi-value dictionary
- yarl 1.18.3 - URL handling library
- attrs 24.3.0 - Class definition utilities
- typing_extensions 4.12.2 - Extended type hints

## Configuration

**Environment:**
- Environment variables (`.env` file, `.env.example` as template)
- Key configuration: `DISCORD_TOKEN` (required), `DISCORD_GUILD_ID` (optional), `LOG_LEVEL` (optional)
- Optional: `BOT_DATA_DIR` for custom data directory location

**Build:**
- `Dockerfile` - Python 3.12 slim base image
- `docker-compose.yml` - Service orchestration with volume mounts

## Data Storage

**Database:**
- SQLite 3 (built-in with Python)
- Database files stored in `data/` directory
- Primary: `economy.db` - Economy/wallet system
- Optional: `quotes.db` - Quotes storage

## Platform Requirements

**Development:**
- Python 3.12
- pip3 package manager
- Docker and Docker Compose (for containerized deployment)

**Production:**
- Docker container runtime
- Discord bot token from Discord Developer Portal
- Persistent volume for SQLite database files (`/app/data`)
- Persistent volume for data files (`/app/data_files`)

---

*Stack analysis: 2026-04-24*
