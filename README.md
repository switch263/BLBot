# BLBot

A chaotic Discord bot for the Bored Lunatics gaming server. Built on [discord.py](https://github.com/Rapptz/discord.py) 2.4+ with both `!prefix` and `/slash` command support.

## Features

### Economy System
Shared coin wallet across all games. Start with 100 coins.

| Command | Description |
|---------|-------------|
| `!slots [bet]` | Slot machine with 8 weighted symbols (bet 1-1000) |
| `!coinflip <bet> <heads/tails>` | Double or nothing |
| `!heist @victim [@accomplice]` | Rob someone's coins (solo 35% / duo 55% success) |
| `!loot` | Daily loot drop with 5 rarity tiers |
| `!slots daily` | Daily coin bonus (random: 50/100/200/5000) |
| `!gift @user <amount>` | Send coins to another user |
| `!roulette` | Multiplayer Russian Roulette, winner takes the pot |
| `!richest` | Leaderboard and server economy stats |

### Humor & Generators
| Command | Description |
|---------|-------------|
| `!roast @user` | Template-based creative roasts |
| `!insult @user` | 700+ insults with 15 templates, 25% chance of savage mode |
| `!fortune` | Sarcastic fortune cookie with lucky numbers |
| `!headline` | Absurd fake news headlines |
| `!floridaman` | Florida Man headlines (100 in data file) |
| `!conspiracy` | Unhinged conspiracy theory generator |
| `!therapy` | Increasingly unhinged therapist advice (100 responses) |
| `!thought` | Shower thoughts (100 in data file) |
| `!advice` | Terrible life advice (100 in data file) |
| `!excuse` | Absurd excuse generator (40x40x40x40 combinations) |

### Text Manipulation
| Command | Description |
|---------|-------------|
| `!mock <text>` | SpOnGeBoB mOcKiNg tExT |
| `!clap <text>` | Put 👏 between 👏 every 👏 word |
| `!vaporwave <text>` | Ｆｕｌｌｗｉｄｔｈ ａｅｓｔｈｅｔｉｃ |
| `!zalgo <text>` | C̸o̷r̶r̵u̸p̵t̷ text (intensity 1-3) |
| `!emojify <text>` | Turn words into emoji |
| `!soup` | Scramble the last message into alphabet soup |

### Social & Interactive
| Command | Description |
|---------|-------------|
| `!fight @user` | Random fight narrator |
| `!slap @user` | 1.8M+ slap combinations, bot retaliates after 5/day |
| `!donger @user` | Raise your donger (30% chance of measurement) |
| `!bdsm @user` | BDSM scenario generator (720k+ combinations) |
| `!rekt @user` | Get Riggity Rekt (10% combo chance) |
| `!pickup @user` | Terrible pickup lines |
| `!villain @user` | Dramatic villain monologue |
| `!lifestats @user` | Deterministic RPG character sheet |
| `!random @user` | Random out-of-context message from history (or fake) |

### Utility & Info
| Command | Description |
|---------|-------------|
| `!weather <location>` | Weather with rich embeds |
| `!xkcd [number]` | XKCD comics (latest, random, or specific) |
| `!urban <word>` | Urban Dictionary lookup |
| `!chucknorris` | Random Chuck Norris fact |
| `!tarkov_time` | Escape from Tarkov in-game times |
| `!quote [add/get]` | Quote database |
| `!ctf` / `!ftc` | Temperature conversion |
| `!roll NdN` | Dice roller |
| `!serverstats` | Server statistics embed |
| `/whoami` | Your user info (ephemeral, slash only) |
| `/channelinfo` | Channel info (ephemeral, slash only) |
| `/help` | Paginated help with buttons (ephemeral, slash only) |

### Meme Images
`!lasaga` `!pineapple` `!ohio` `!hf` `!lenny` `!gaslight`

### Passive Chaos (no commands, just happens)
| Feature | What it does |
|---------|-------------|
| **Gaslight** | Sends a message then sneakily edits it. Fake misquotes. Suspicious reacts. |
| **Dad Bot** | 5% chance to reply "Hi X, I'm Dad!" when someone says "I'm X" |
| **Typo Police** | 2% chance to "correct" spelling incorrectly |
| **Fake Typing** | Shows typing for 30 seconds then sends "nvm" (every 4-48 hours) |
| **Lurker Callout** | Pings someone who hasn't spoken in 7 days (every 5-14 days) |
| **Sleep Police** | Tells people to go to bed if they post between 2-5am UTC |
| **Selective Memory** | "Remembers" events that never happened about random users (every 2-7 days) |
| **Phantom Ping** | "who pinged me?" when nobody did, with paranoid followups (every 1-4 days) |
| **Unhinged** | Replies to random old messages with unhinged commentary (every 3-60 days) |
| **Chaos Engine** | Wrong channel messages, existential crises, fake maintenance alerts, vague threats, relationship drama, abandonment issues, context crimes, passive aggressive reaction chains |

## Setup

### Requirements
- Python 3.12+
- Discord bot token ([Developer Portal](https://discord.com/developers/applications))

### Quick Start (Docker Compose)

```bash
git clone https://github.com/switch263/BLBot.git
cd BLBot
cp .env.example .env
# Edit .env with your DISCORD_TOKEN
docker compose up -d
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_TOKEN` | Yes | Discord bot token |
| `LOG_LEVEL` | No | DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO) |
| `DISCORD_GUILD_ID` | No | Guild ID for instant slash command sync during development |

### Manual Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your DISCORD_TOKEN
python3 bot.py
```

## Architecture

```
BLBot/
├── bot.py              # Main entry point, cog loader, slash command sync
├── config.py           # Database config, DATA_DIR
├── docker-compose.yml  # Docker Compose setup
├── Dockerfile          # Python 3.12-slim container
├── requirements.txt    # Python dependencies
├── cogs/               # All bot plugins (auto-loaded)
├── data/               # SQLite databases (auto-created, gitignored)
├── data_files/         # Text data files for generators
└── tests/              # Unit tests
```

### Adding Content
Most generators read from plain text files in `data_files/`. To add content, just append lines:
- `data_files/insults.txt` — one insult noun per line
- `data_files/savage_insults.txt` — full savage insult sentences
- `data_files/thoughts.txt` — shower thoughts
- `data_files/therapy_responses.txt` — therapist responses
- `data_files/floridaman_actions.txt` — Florida Man actions
- `data_files/bad_advice.txt` — terrible life advice
- `data_files/fake_quotes.txt` — static fake quotes
- `data_files/fakequote_starters.txt` / `fakequote_actions.txt` / `fakequote_endings.txt` — templated fake quotes
- `data_files/unhinged_replies.txt` — unhinged reply messages
- `data_files/bdsm_templates.txt` / `bdsm_actions.txt` / `bdsm_toys.txt` / `bdsm_traps.txt` — BDSM generator

Use `!reload` (bot owner only) to pick up changes without restarting.

### Adding Cogs
Drop a `.py` file in `cogs/` following the pattern:

```python
import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger(__name__)

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def mycommand(self, ctx):
        await ctx.send("Hello!")

    @app_commands.command(name="mycommand", description="Does a thing")
    async def mycommand_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message("Hello!")

async def setup(bot):
    await bot.add_cog(MyCog(bot))
```

## CI/CD

GitHub Actions builds and pushes Docker images to `ghcr.io` on push to main/master and version tags.
