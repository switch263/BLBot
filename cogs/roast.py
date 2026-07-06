import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

from economy import is_memorial

logger = logging.getLogger(__name__)

# Every entry is a complete joke with a setup and a turn. No mad-libs,
# no random openers/closers — if a line needs help, it doesn't belong here.
# House rule: crude and brutal is fine; nothing about anyone's parents.
ROASTS = [
    "{t}, you have your whole life ahead of you, and honestly, that's the saddest part.",
    "{t}, I'd call you a tool, but tools are useful.",
    "{t}, your secrets are safe with me. I never even listen when you tell me them.",
    "{t}, whoever told you to be yourself gave you terrible advice.",
    "{t}, you're not stupid — you just have bad luck when you think.",
    "{t}, it's impossible to underestimate you.",
    "{t}, you set low standards and consistently fail to achieve them.",
    "{t}, someday you'll go far. I hope you stay there.",
    "{t}, I'm jealous of everyone who hasn't met you.",
    "{t}, I thought of you today. It reminded me to take out the trash.",
    "{t}, light travels faster than sound, which is why you seemed bright until you spoke.",
    "{t}, you're not the dumbest person alive, but you'd better pray nothing happens to them.",
    "{t}, somewhere a tree is working around the clock producing oxygen for you. Apologize to it.",
    "{t}, you're like a cloud — the moment you disappear, it's a beautiful day.",
    "{t}, you bring everyone so much joy... when you leave the voice channel.",
    "{t}, if ignorance is bliss, you must be the happiest person on the planet.",
    "{t}, you're the reason shampoo has instructions.",
    "{t}, keep rolling your eyes. Maybe you'll find a brain back there.",
    "{t}, you're so dense, light bends around you.",
    "{t}, zombies eat brains. You're completely safe.",
    "{t}, if common sense were common, you'd still be the exception.",
    "{t}, I'd agree with you, but then we'd both be wrong.",
    "{t}, I'd explain it to you, but I left my crayons at home.",
    "{t}, you couldn't pour water out of a boot with the instructions printed on the heel.",
    "{t}, if I had a coin for every smart thing you've said, I'd be broke.",
    "{t}, mirrors can't talk. Lucky for you, they can't laugh either.",
    "{t}, I was going to give you a nasty look, but I see you already have one.",
    "{t}, you're proof evolution can go in reverse.",
    "{t}, you're depriving a village somewhere of its idiot.",
    "{t}, it's not that you're wrong all the time. It's that you're so confident about it.",
    "{t}, you're the 'before' picture.",
    "{t}, you have miles to go before you reach mediocre.",
    "{t}, you always think of the perfect comeback three days later, in the shower.",
    "{t}, you're about as useful as a screen door on a submarine.",
    "{t}, the wheel is spinning, but the hamster's been dead for years.",
    "{t}, you peaked at the character creation screen.",
    "{t}, you aim like the crosshair owes you money.",
    "{t}, your reaction time is measured in business days.",
    "{t}, you're the teammate the enemy team thanks in their victory speech.",
    "{t}, even the AFK bot contributes more than you.",
    "{t}, if you were a spice, you'd be flour.",
    "{t}, your ego is writing checks your talent can't cash.",
    "{t}, every time you speak, somewhere a teacher gives up.",
    "{t}, you're the only person here the house feels bad taking money from.",
    "{t}, you'd lose a best-of-three coin flip in two.",
    "{t}, you double down like someone who's never met you.",
    "{t}, you're so unlucky that if it rained soup, you'd be holding a fork.",
    "{t}, you couldn't win a raffle if you bought every ticket.",
    "{t}, your guardian angel filed for a transfer.",
    "{t}, you have something on your chin... no, the third one down.",
    "{t}, I'd roast you harder, but there are laws about burning trash.",
    "{t}, you look like something I drew with my left hand.",
    "{t}, I've seen people like you before — but I had to pay admission.",
    "{t}, I've stepped in things smarter than you. They smelled better, too.",
    "{t}, they say beauty is on the inside. Yours is hiding.",
    "{t}, your reflection ducks.",
    "{t}, the gene pool needed a lifeguard and you did a cannonball into the shallow end.",
    "{t}, the only event you'll ever headline is your funeral, and even that will start without you.",
    "{t}, dogs love everyone. Yours has doubts.",
    "{t}, God doesn't make mistakes, but He does hit 'randomize' and walk away sometimes.",
    "{t}, your love life is like your wallet: empty, and everyone knows exactly why.",
    "{t}, if you were on fire and I had a glass of water, I'd drink it.",
    "{t}, the only thing you've ever made wet is your mattress.",
    "{t}, the last time you were someone's type, it was at a blood drive.",
    "{t}, you couldn't get laid in a women's prison with a fistful of pardons.",
    "{t}, the only pussy you've ever touched has a litter box.",
    "{t}, your Pornhub recommendations know you better than anyone ever will.",
    "{t}, you type with one hand and everyone can tell.",
    "{t}, I've seen better heads on a glass of warm piss.",
    "{t}, you look like you smell like ham.",
    "{t}, you smell like being a Discord mod is your full-time job.",
    "{t}, you shower so rarely your soap filed a missing persons report.",
    "{t}, you're the human equivalent of a skid mark on society's underwear.",
    "{t}, you're not the shit. You're just shit.",
    "{t}, if bullshit were music, you'd be a full orchestra.",
    "{t}, you're about as pleasant as a fart in an elevator, and you linger longer.",
    "{t}, your breath could strip the paint off a battleship.",
    "{t}, you're built like a melted candle.",
    "{t}, you're shaped like a thumb with anxiety.",
    "{t}, you dress like you lost a bet with a dumpster.",
    "{t}, you've got a face like a dropped pie.",
    "{t}, you'd get refund requests on OnlyFans.",
    "{t}, even your sleep paralysis demon stopped showing up. You depressed it.",
    "{t}, when you die, the obituary will just say 'finally.'",
    "{t}, you'd get swiped left by a bot programmed to swipe right.",
    "{t}, your gaming chair has a dent shaped like wasted potential and ass sweat.",
    "{t}, your right hand is the longest relationship you've ever had, and it's thinking about leaving.",
    "{t}, you've been ghosted by people you paid.",
]

MEMORIAL_RESPONSES = [
    "Not that one. Some legends are beyond the roast. o7",
]


class Roast(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Roast module has been loaded")

    def _generate_roast(self, target_id: int, target_mention: str) -> str:
        if is_memorial(target_id):
            return random.choice(MEMORIAL_RESPONSES)
        return random.choice(ROASTS).format(t=target_mention)

    @commands.command()
    async def roast(self, ctx, member: discord.Member = None):
        """Roast someone (or yourself if you're brave)."""
        target = member or ctx.author
        await ctx.send(self._generate_roast(target.id, target.mention))

    @app_commands.command(name="roast", description="Roast someone with an actual roast")
    @app_commands.describe(member="Who to roast (leave empty to roast yourself)")
    async def roast_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        await interaction.response.send_message(
            self._generate_roast(target.id, target.mention)
        )


async def setup(bot):
    await bot.add_cog(Roast(bot))
