# BLBot
Discord bot for my gaming server full of idiots

Cogs (plugins) live in cogs/ and can be added / extended easily. 

# Dockerfile

Uses python:3.8 image.
```
git clone https://github.com/switch263/BLBot.git
cd BLBot/

docker build --tag blbot .

docker run -d --name blbot blbot
```

# Usage
This bot utilizes the py-cord fork of discord.py,sqlalchemy library for stats and quotes (plus more in the future possibly), meaning you can use various types of databases if you wish to run this at scale for whatever dumb reason.
By default it uses sqlite (located at data/blbot.db), but supports postgres out of the box.

## Compose Usage w/ Postgresql
```
version: '3'
services:
  blbot:
    image: ghcr.io/switch263/blbot:latest
    environment:
      - DISCORD_TOKEN=AAAA.BBBB.CCCC
      - DATABASE_URL=postgresql://blbot:blbot@pgsql:5432/blbot
  pgsql:
    image: postgres:latest
    environment:
      POSTGRES_USER: blbot
      POSTGRES_PASSWORD: blbot
      POSTGRES_DB: blbot
    volumes:
      - ./database:/var/lib/postgresql/data

```

## Compose Usage w/ Sqlite
```
version: '3'
services:
  blbot:
    image: ghcr.io/switch263/blbot:latest
    environment:
      - DISCORD_TOKEN=AAAA.BBBB.CCCC
    volumes:
      - ./data/blbot.db:/app/data/blbot.db
```
