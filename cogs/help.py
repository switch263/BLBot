import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger(__name__)


def _build_pages() -> list[discord.Embed]:
    """Build the help page embeds."""
    pages = []

    e1 = discord.Embed(title="BLBot Help (1/8) - Basics & Utility",
                       description="Use `/command` or `!command`",
                       color=discord.Color.blurple())
    e1.add_field(name="Basics", value=(
        "`/ping` - Check if the bot is alive\n"
        "`/roll` - Roll dice in NdN format (e.g. 2d6)\n"
        "`/choose` - Choose between multiple options\n"
        "`/joined` - See when a member joined\n"
        "`/lenny` - Random lenny face\n"
    ), inline=False)
    e1.add_field(name="Utility", value=(
        "`/weather` - Get weather for a location\n"
        "`/ctf` / `/ftc` - Temperature conversion\n"
        "`/serverstats` - Server statistics\n"
        "`/whoami` - Your user info (ephemeral)\n"
        "`/channelinfo` - Channel info (ephemeral)\n"
        "`/guildinfo` - Server info + bot reach (ephemeral)\n"
        "`/urban` - Urban Dictionary lookup\n"
        "`/xkcd` - Get an xkcd comic\n"
    ), inline=False)
    pages.append(e1)

    e2 = discord.Embed(title="BLBot Help (2/8) - Humor & Memes",
                       color=discord.Color.green())
    e2.add_field(name="Humor", value=(
        "`/8ball` - Ask the magic 8-ball\n"
        "`/mock` - SpOnGeBoB mOcKiNg tExT\n"
        "`/roast` - Roast someone\n"
        "`/insult` - Insult someone\n"
        "`/fortune` - Crack a fortune cookie\n"
        "`/headline` - Fake news headline\n"
        "`/floridaman` - Florida Man headline\n"
        "`/conspiracy` - Unhinged conspiracy theory\n"
        "`/therapy` - Professional(?) advice\n"
        "`/thought` - Deep(?) shower thought\n"
        "`/advice` - Terrible life advice\n"
        "`/excuse` - Absurd excuse generator\n"
    ), inline=False)
    pages.append(e2)

    e3 = discord.Embed(title="BLBot Help (3/8) - Text & Formatting",
                       color=discord.Color.teal())
    e3.add_field(name="Text Tools", value=(
        "`/clap` - Put 👏 between 👏 every 👏 word\n"
        "`/emojify` - Turn text into emoji\n"
        "`/rekt` - Get Riggity Rekt\n"
    ), inline=False)
    e3.add_field(name="Images & Reactions", value=(
        "`/lasaga` - Lasaga meme\n"
        "`/pineapple` - Pineapple meme\n"
        "`!ohio` - Express feelings about Ohio (prefix only)\n"
        "`!hf` - C:\\\\HOTFUCKIN\\\\ (prefix only)\n"
    ), inline=False)
    pages.append(e3)

    e4 = discord.Embed(title="BLBot Help (4/8) - Social & Interactive",
                       color=discord.Color.orange())
    e4.add_field(name="Social", value=(
        "`/fight` - Start a fight between two people\n"
        "`/slap` - Slap someone\n"
        "`/donger` - Raise your donger\n"
        "`/bdsm` - Generate a BDSM scenario\n"
        "`/pickup` - Terrible pickup lines\n"
        "`/villain` - Dramatic villain monologue\n"
        "`/lifestats` - Fake RPG character sheet\n"
    ), inline=False)
    e4.add_field(name="Info & Reference", value=(
        "`/chucknorris` - Random Chuck Norris fact\n"
        "`!tarkov_time` - Escape from Tarkov times (prefix only)\n"
        "`/quote` - Get a quote from the database\n"
        "`/quote_add` - Add a quote\n"
    ), inline=False)
    pages.append(e4)

    e5 = discord.Embed(title="BLBot Help (5/8) - Casino: Classic",
                       description="Classic gambling games. Lose responsibly.",
                       color=discord.Color.gold())
    e5.add_field(name="Card & Chance", value=(
        "`/blackjack` - Multi-player blackjack with buy-in lobby\n"
        "`/highlow` - Predict the next card, build streak multiplier\n"
        "`/vault` - Crack a 4-digit code, Mastermind-style deduction\n"
        "`/vault_hard` - 5 digits from 1-9, **3 attempts**, lose = bet goes to the house\n"
        "`/slots` - Slot machine with weighted reels\n"
        "`/coinflip` - Heads or tails, double or nothing\n"
    ), inline=False)
    e5.add_field(name="Roulette", value=(
        "`/bet` - Casino roulette: red/black/even/odd/number\n"
        "`/pot` - Show the house pot (hit 🟢 green to claim it all)\n"
    ), inline=False)
    pages.append(e5)

    e6 = discord.Embed(title="BLBot Help (6/8) - Casino: Solo Chaos",
                       description="Single-player push-your-luck and chaos games.",
                       color=discord.Color.purple())
    e6.add_field(name="Push Your Luck", value=(
        "`/gauntlet` - High-roller ladder: cash out or push your luck (bet scales with the house, no flat 100k cap)\n"
        "`/mines` - Reveal gems, dodge mines; each gem raises the multiplier, cash out or boom\n"
        "`/dig` - Raccoon Den: dig bins, avoid feral raccoons\n"
        "`/bigfoot` - Hunt Bigfoot, dodge bears, rare ×10 jackpot\n"
        "`/dogs` - Hot Dog Eating Contest — stack multiplier, don't hurl\n"
        "`/vault` - Mastermind-style 4-digit safecrack\n"
    ), inline=False)
    e6.add_field(name="Pure Chaos", value=(
        "`/wheel` - Wheel of Misfortune — spin for cursed outcomes\n"
        "`/vend` - The Vending Machine From Hell — pick a cursed soda\n"
        "`/sushi` - Gas Station Sushi — wide variance on absurd rolls\n"
        "`/methgator` - You are a gator on meth. Pick a rampage.\n"
        "`/sunnyvale` - A day in Sunnyvale Trailer Park (TPB-themed)\n"
        "`/mayor` - Run for Trailer Park Mayor — 3 rounds of strategy\n"
        "`/troll` - Troll Bridge — answer the nonsense riddle\n"
    ), inline=False)
    pages.append(e6)

    e7 = discord.Embed(title="BLBot Help (7/8) - Casino: Multiplayer & PvP",
                       description="Games where you bring friends (or eat them).",
                       color=discord.Color.red())
    e7.add_field(name="Lobby Games", value=(
        "`/blackjack` - 60s buy-in lobby, up to 8 players\n"
        "`/roulette` - Russian Roulette — **ALL IN**, winner takes all\n"
        "`/pigderby` - 5-pig race with odds-based payouts\n"
    ), inline=False)
    e7.add_field(name="PvP & Confrontation", value=(
        "`/heist` - Rob another user (or the bot — jail if caught)\n"
        "`/roach` - Cockroach Fight Club — 1v1 challenge, winner takes pot\n"
        "`/insure buy` - Buy heist insurance; `/insure claim` recovers % of a robbery from the bank\n"
        "`/jail` - Check casino jail status (blocks all gambling)\n"
    ), inline=False)
    pages.append(e7)

    e8 = discord.Embed(title="BLBot Help (8/8) - Economy & Quick Reference",
                       color=discord.Color.dark_grey())
    e8.add_field(name="Earn Coins", value=(
        "`/loot` - Daily loot drop with rarity tiers\n"
        "Win at any of the casino games\n"
    ), inline=False)
    e8.add_field(name="Manage Coins", value=(
        "`/wallet` - Balance + stats across games\n"
        "`/gift` - Send coins to another user\n"
        "`/burn` - Donate coins to the house (or `vanish:True` to destroy)\n"
        "`/charity` - Disperse coins to random members of this channel\n"
        "`/richest` - Leaderboard & economy stats\n"
        "`/slots_leaderboard` - Top slot players\n"
    ), inline=False)
    e8.add_field(name="Tips", value=(
        "All commands work as `/slash` or `!prefix`.\n"
        "Aliases: `!cf` = coinflip, `!ud` = urban, `!rob` = heist,\n"
        "`!rr` = roulette (Russian), `!tpb` = sunnyvale, `!gator` = methgator,\n"
        "`!bj` = blackjack, `!dive`/`!raccoon` = dig, `!hilo` = highlow.\n"
        "**The bot itself is the house.** Try `/heist @bot` if you feel lucky."
    ), inline=False)
    e8.set_footer(text="BLBot | https://github.com/switch263/BLBot")
    pages.append(e8)

    return pages


class HelpPaginator(discord.ui.View):
    def __init__(self, pages: list[discord.Embed], author_id: int):
        super().__init__(timeout=120)
        self.pages = pages
        self.current = 0
        self.author_id = author_id
        self._update_buttons()

    def _update_buttons(self):
        self.prev_button.disabled = self.current == 0
        self.next_button.disabled = self.current == len(self.pages) - 1

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your help menu!", ephemeral=True)
            return
        self.current -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your help menu!", ephemeral=True)
            return
        self.current += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Help module has been loaded")

    @app_commands.command(name="help", description="Show all available commands")
    async def help_slash(self, interaction: discord.Interaction):
        pages = _build_pages()
        view = HelpPaginator(pages, interaction.user.id)
        await interaction.response.send_message(embed=pages[0], view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Help(bot))
