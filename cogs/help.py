import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger(__name__)


def _build_pages() -> list[discord.Embed]:
    """Build the help page embeds."""
    pages = []

    e1 = discord.Embed(title="BLBot Help (1/6) - Basics & Utility", description="Use `/command` or `!command`", color=discord.Color.blurple())
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
        "`/urban` - Urban Dictionary lookup\n"
        "`/xkcd` - Get an xkcd comic\n"
    ), inline=False)
    pages.append(e1)

    e2 = discord.Embed(title="BLBot Help (2/6) - Humor & Memes", color=discord.Color.green())
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

    e3 = discord.Embed(title="BLBot Help (3/6) - Text & Formatting", color=discord.Color.teal())
    e3.add_field(name="Text Tools", value=(
        "`/clap` - Put 👏 between 👏 every 👏 word\n"
        "`/vaporwave` - Ｆｕｌｌｗｉｄｔｈ ａｅｓｔｈｅｔｉｃ\n"
        "`/zalgo` - C̸̛o̷r̶r̵u̸p̵t̷ ̴t̵e̵x̷t̵\n"
        "`/emojify` - Turn text into emoji\n"
        "`/soup` - Scramble last message\n"
        "`/gaslight` - Trigger a gaslight sequence\n"
        "`/rekt` - Get Riggity Rekt\n"
    ), inline=False)
    e3.add_field(name="Images & Reactions", value=(
        "`/lasaga` - Lasaga meme\n"
        "`/pineapple` - Pineapple meme\n"
        "`/ohio` - Express feelings about Ohio\n"
        "`/hf` - C:\\\\HOTFUCKIN\\\\\n"
    ), inline=False)
    pages.append(e3)

    e4 = discord.Embed(title="BLBot Help (4/6) - Social & Interactive", color=discord.Color.orange())
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
        "`/tarkov_time` - Escape from Tarkov times\n"
        "`/quote` - Get a quote from the database\n"
        "`/quote_add` - Add a quote\n"
    ), inline=False)
    pages.append(e4)

    e5 = discord.Embed(title="BLBot Help (5/6) - Economy", color=discord.Color.gold())
    e5.add_field(name="Gambling", value=(
        "`/slots` - Slot machine (optional bet amount)\n"
        "`/coinflip` - Double or nothing coin flip\n"
        "`/roulette` - Russian Roulette (multiplayer)\n"
        "`/loot` - Daily loot drop for random coins\n"
    ), inline=False)
    e5.add_field(name="Economy", value=(
        "`/slots_daily` - Claim daily bonus coins\n"
        "`/slots_balance` - Check your wallet\n"
        "`/gift` - Send coins to another user\n"
        "`/heist` - Rob another user's coins\n"
        "`/richest` - Leaderboard & economy stats\n"
        "`/slots_leaderboard` - Top slot players\n"
    ), inline=False)
    pages.append(e5)

    e6 = discord.Embed(title="BLBot Help (6/6) - Quick Reference", color=discord.Color.dark_grey())
    e6.add_field(name="Prefix Commands", value=(
        "All commands work with both `/slash` and `!prefix`.\n"
        "Some have aliases: `!cf` = `!coinflip`, `!ud` = `!urban`,\n"
        "`!rob` = `!heist`, `!rr` = `!roulette`, etc."
    ), inline=False)
    e6.add_field(name="Economy Tips", value=(
        "Start with **100** coins. Earn more via:\n"
        "• `/slots_daily` - Daily bonus (once per day)\n"
        "• `/loot` - Daily loot drop (once per day)\n"
        "• `/slots`, `/coinflip` - Gambling\n"
        "• `/heist` - Rob other players (risky!)\n"
        "• `/roulette` - Multiplayer, winner takes pot"
    ), inline=False)
    e6.set_footer(text="BLBot | https://github.com/switch263/BLBot")
    pages.append(e6)

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
