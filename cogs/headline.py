import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

logger = logging.getLogger(__name__)

SUBJECTS = [
    "Florida Man", "Local Gamer", "Area Dad", "Neighborhood Cat", "Drunk Uncle",
    "A Sentient Roomba", "Unnamed Discord Moderator", "Guy From Craigslist",
    "Walmart Shopper", "Former Child", "Self-Proclaimed Influencer",
    "Man Wearing Crocs", "Woman With 47 Cats", "HOA President",
    "Gas Station Employee", "Reddit User", "Town Mayor",
    "Church Bake Sale Organizer", "Little League Umpire", "Local Weatherman",
    "Middle School Principal", "Retired Wrestler", "Amateur Taxidermist",
    "Competitive Eater", "Part-Time Clown", "Unlicensed Dentist",
    "Aspiring SoundCloud Rapper", "Three Raccoons In A Trench Coat",
    "A Man Known Only As 'Big Tony'", "Freelance Exorcist",
]

VERBS = [
    "arrested after", "hospitalized after", "banned from Applebee's for",
    "wins Nobel Prize for", "goes viral after", "declares war on neighbors for",
    "starts GoFundMe after", "sues city over", "calls 911 over",
    "builds shrine dedicated to", "fistfights mailman over",
    "accidentally invents", "gets permanently banned from Costco for",
    "files lawsuit against God for", "elected mayor after",
    "survives bear attack using only", "crashes wedding while",
    "takes hostages at Denny's over", "steals ambulance to get to",
    "discovers new species while", "runs for president on platform of",
    "breaks world record for", "fires employee for refusing to",
    "smuggles 200 pounds of", "livestreams self while",
    "writes 800-page manifesto about", "tattoos face with",
]

OBJECTS = [
    "trying to microwave a phone charger",
    "a dispute over the last Hot Pocket",
    "refusing to accept that birds are real",
    "a gender reveal involving a cannon",
    "insisting the Earth is shaped like a velociraptor",
    "bringing an emotional support alligator to church",
    "arguing that cereal is a soup",
    "challenging a cop to a dance battle",
    "a pyramid scheme involving essential oils and NFTs",
    "feeding LSD to the neighborhood geese",
    "a heated debate about whether a hot dog is a sandwich",
    "claiming to be the rightful king of a Burger King",
    "riding a lawn mower on the highway at 3am",
    "insisting Shrek is a documentary",
    "trying to pay rent with Monopoly money",
    "a chainsaw juggling accident",
    "teaching karate to squirrels",
    "an argument about pineapple on pizza",
    "building a full-scale replica of the Death Star in their yard",
    "an underground cheese fighting ring",
    "refusing to leave Chuck E. Cheese without their tickets",
    "demanding to speak to the manager of the internet",
    "a plan to colonize the local Walmart",
    "claiming their dog is a licensed therapist",
    "attempting to baptize a cat",
    "a strongly worded letter to the moon",
]


class FakeNews(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Fake News module has been loaded")

    def _generate_headline(self) -> discord.Embed:
        """Generate a fake news headline embed."""
        subject = random.choice(SUBJECTS)
        verb = random.choice(VERBS)
        obj = random.choice(OBJECTS)

        headline = f"{subject} {verb} {obj}"

        embed = discord.Embed(
            title="BREAKING NEWS",
            description=f"**{headline}**",
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Source: Definitely Real News Network | {random.choice(['Developing story', 'More at 11', 'Witnesses stunned', 'Authorities baffled', 'Neighbors unsurprised'])}")

        return embed

    @commands.command(aliases=['headline', 'fakenews'])
    async def news(self, ctx):
        """Generate an absurd fake news headline."""
        await ctx.send(embed=self._generate_headline())

    @app_commands.command(name="headline", description="Generate an absurd fake news headline")
    async def headline_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self._generate_headline())


async def setup(bot):
    await bot.add_cog(FakeNews(bot))
