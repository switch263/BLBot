# BLBot
Discord bot for my gaming server full of idiots

Dependent upon discord.py (https://github.com/Rapptz/discord.py) and a few more common libraries.

Edit config.py to specify your weather API key and Discord bot token as appropriate before running bot.py directly.

Cogs (plugins) live in cogs/ and can be added / extended easily. There is a pre-built function (reload) that will unload all running cogs and then parse all files in cogs/ to load any that still exist on disk back into memory.

# Dockerfile

Built on Alpine, installs python3, pip, setuptools, wheel, before moving on to the application and requirements.

```
git clone https://github.com/switch263/BLBot.git
cd BLBot/
edit config.py to your liking

docker build --tag blbot .

docker run -d --name blbot blbot
```
