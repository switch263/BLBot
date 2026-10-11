# BLBot

A chaotic Discord bot for the Bored Lunatics gaming server. Built on [discord.py](https://github.com/Rapptz/discord.py) 2.4+ with both `!prefix` and `/slash` command support.

## Features

### Economy System
Shared coin wallet across all games. Start with 100 coins. The bot itself is the house — its wallet collects the roulette pot. `/heist @bot` is allowed but has a **1%** success rate; failure = **casino jail (1–36h, longer for repeat offenders)**, blocking every gambling command. Admins can `!unjail @user` (or `!bail` / `!pardon`) in the admin channel.

#### 🎲 Classic Casino
| Command | Description |
|---------|-------------|
| `!slots [bet]` | 8-symbol weighted slots (min bet 1, no cap) |
| `!coinflip <bet> <heads/tails>` | Double or nothing |
| `!blackjack <bet>` | Multi-player blackjack with 60s buy-in lobby |
| `!highlow <bet>` | Predict next card higher/lower; streak builds multiplier |
| `!vault <bet>` | Mastermind-style 4-digit safecrack, 6 attempts |
| `!bet <red/black/even/odd/N> <amount>` | Casino roulette (hit green = claim the pot) |
| `!pot` | Show the current house pot |

#### 🃏 Solo Chaos / Push-Your-Luck
| Command | Description |
|---------|-------------|
| `!gauntlet <bet>` | High-roller ladder — cash out or push your luck; bet scales with the house (no flat 100k cap) |
| `!mines <bet> [mines]` | 5×4 grid — reveal gems for a rising multiplier, hit a mine and bust; cash out anytime |
| `!dig <bet>` | Raccoon's Den — 4×4 grid of bins, 3 raccoons bite |
| `!bigfoot <bet>` | Hunt Bigfoot — 3 bears + 1 Bigfoot jackpot tile |
| `!dogs <bet>` | Hot Dog Eating Contest — each dog raises mult + hurl risk |
| `!wheel <bet>` | Wheel of Misfortune — chaotic weighted outcomes |
| `!vend <bet>` | The Vending Machine From Hell — 6 cursed sodas |
| `!methgator <bet>` | You are a gator on meth. Pick one of 8 rampages. |
| `!troll <bet>` | Troll Bridge — correct answer to a nonsense riddle = ×3 |
| `!insurance <bet>` | File a fraudulent insurance claim — pick a scheme, try not to get caught |
| `!microwave <bet>` | "Is it a good idea to microwave this?" |
| `!bongo <bet>` | Let the kitty play the bongos — multiplicative board, pays big once a day |
| `!scratch <bet>` | Buy an instant-win lottery ticket and scratch it (`!tickets` for odds) |
| `!juju` | Tempt the juju — a free loot grid, twice a day; one tile curses you |

#### 👥 Multiplayer & PvP
| Command | Description |
|---------|-------------|
| `!roulette` | Russian Roulette — ALL IN your entire wallet, winner takes all |
| `!pigderby <bet>` | 5-pig race with fixed-odds betting (2×–15× payouts) |
| `!roach @user <bet>` | Cockroach Fight Club — 1v1 duel, winner takes pot |
| `!heist @victim [@accomplice]` | Rob someone (or the bot, at long odds) |
| `!crewheist <target> [account] [approach]` | Recruit a paid crew to hit a player, the whole casino, or one bank box |
| `!insure` / `!reclaim` | Buy heist insurance; reclaim 60% of a robbery from the bank |
| `!bounty @user <bet>` | Pay to maybe-jail someone — odds scale with the bet; a miss jails you |
| `!bingle @user` | Get bingled, or bingle someone |

#### 💰 Earning & Economy
| Command | Description |
|---------|-------------|
| `!loot` | Daily loot drop with 5 rarity tiers (500–200000 coins) |
| `!wallet` | Balance + stats across all games |
| `!gift @user <amount>` | Send coins to another user |
| `!richest` | Leaderboard & server economy stats |
| `!jail [@user]` | Check casino jail status |
| `!bank` / `!deposit` / `!withdraw` | Private, heist-resistant, un-gamblable vault (earns interest) |
| `!shop` / `!buy` / `!inventory` / `!use` / `!sell` | Item shop — Get Out of Jail Free, Bonus Spin, Heist Shield |
| `!splurge` / `!flex` / `!bonfire` | Wealth-gated coin sink — buy cosmetic trophies, show them off |
| `!burn <amount>` | Burn coins to the house pot (or set vanish to destroy them) |
| `!prestige` / `!legacy` | Wipe your fortune for a permanent winnings multiplier; lifetime leaderboard |
| `!dividends` | House profit-sharing — who owns a piece of the house |
| `!loan borrow/repay/job/tab` | Big Sal's loan business — the vig is not negotiable |
| `!taxbill` / `!paytax` | Check and pay what you owe the casino |

#### 🚔 Crime & Jail
| Command | Description |
|---------|-------------|
| `!bailbonds @user` / `!bondboard` | Post bond on a jailed user (roll for vig — or for jail); see who's bondable |
| `!jailbreak` | Risk it for early release — or make your sentence worse |
| `!lawyer` | Hire a lawyer to fight your sentence for a cut of your wallet |
| `!trial` | Jury trial — argue your way out (`!jury` / `!objection`) |
| `!prison file/labor/dice/gym/shiv/guard/cards` | The prison economy — only works while you're locked up |

### Humor & Generators
| Command | Description |
|---------|-------------|
| `!roast @user` | Template-based creative roasts |
| `!yourmother @user` | Your-mother jokes (`!yomama` / `!urmom`) |
| `!fortune` | Sarcastic fortune cookie with lucky numbers |
| `!headline` | Absurd fake news headlines |
| `!conspiracy` | Unhinged conspiracy theory generator |
| `!therapy` | Increasingly unhinged therapist advice (99 responses) |
| `!thought` | Shower thoughts (100 in data file) |
| `!advice` | Terrible life advice (100 in data file) |
| `!excuse` | Absurd excuse generator (40x40x40x40 combinations) |
| `!8ball <question>` | Ask the magic 8-ball |

### Text Manipulation
| Command | Description |
|---------|-------------|
| `!mock <text>` | SpOnGeBoB mOcKiNg tExT |
| `!clap <text>` | Put 👏 between 👏 every 👏 word |
| `!emojify <text>` | Turn words into emoji |

### Social & Interactive
| Command | Description |
|---------|-------------|
| `!fight @user` | Random fight narrator |
| `!slap @user` | 1.8M+ slap combinations, bot retaliates after 5/day |
| `!donger @user` | Raise your donger (30% chance of measurement) |
| `!bdsm @user` | BDSM scenario generator (720k+ combinations) |
| `!rekt @user` | Get Riggity Rekt (10% combo chance) |
| `!pickup @user` | Terrible pickup lines |
| `!lifestats @user` | Deterministic RPG character sheet |

### Utility & Info
| Command | Description |
|---------|-------------|
| `!weather <location>` | Weather with rich embeds |
| `!xkcd [number]` | XKCD comics (latest, random, or specific) |
| `!urban <word>` | Urban Dictionary lookup |
| `!chucknorris` | Random Chuck Norris fact |
| `!tarkov_time` | Escape from Tarkov in-game times |
| `!quote [add/get]` | Quote database |
| `!convert <value>` | Units & currency (e.g. `72f to c`, `100 usd to eur`, `5mi to km`) |
| `!roll NdN` | Dice roller |
| `!serverstats` | Server statistics embed |
| `!date` | Current date/time (`!date set <tz>` for your timezone) |
| `!remindme <time> <text>` | Set a reminder (`!reminders` / `!cancelreminder`) |
| `!achievements` | Track your achievements (`/achievements view` / `top`) |
| `/info me` | Your user info (ephemeral, slash only) |
| `/info channel` | Channel info (ephemeral, slash only) |
| `/info server` | Server info + bot reach (ephemeral, slash only) |

### Meme Images
`!lasaga` `!pineapple` `!ohio` `!hf` `!lenny`

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
- `data_files/thoughts.txt` — shower thoughts
- `data_files/therapy_responses.txt` — therapist responses
- `data_files/bad_advice.txt` — terrible life advice
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
