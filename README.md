# BLBot
Discord bot for my gaming server full of idiots

Dependent upon discord.py (https://github.com/Rapptz/discord.py) and a few more common libraries.

Edit config.py to specify your weather API key and Discord bot token as appropriate before running bot.py directly.


# Dockerfile

Built on Alpine, installs python3, pip, setuptools, wheel, before moving on to the application and requirements.

```
git clone https://github.com/switch263/BLBot.git
cd BLBot/
edit config.py to your liking

docker build --tag blbot .

docker run -d --name blbot blbot
```
