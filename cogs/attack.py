import discord
from discord.ext import commands
import random
import logging
import datetime
import os

logger = logging.getLogger(__name__)

class Attack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.stats = bot.get_cog('Stats')
        self.sounds = [
            "BAM", "BASH", "BATTLE CRY", "BEATDOWN", "BELLOW", "BLAM", "BLAST", "BLUDGEON", "BOOM", "BOUNCE",
            "BUM RUSH", "BUMP", "BURST", "CLANG", "CLAP", "CLATTER", "CRACK", "CRASH", "CRUNCH", "DETONATE",
            "EXPLODE", "FLAP", "FLICK", "FLOP", "GLITCH", "GONG", "GRUNT", "HISS", "HIT", "HOWL", "IMPACT",
            "JAB", "KABLAM", "KICK", "MELEE", "PUNCH", "QUAKE", "RAZZLE-DAZZLE", "RUMBLE", "RUSH", "SCRATCH",
            "SCREAM", "SHATTER", "SHOCK", "SHOVE", "SHRIEK", "SLAM", "SLAP", "SLICE", "SMACK", "SMASH", "SNAP",
            "SNARL", "SPLAT", "SPOOK", "STAMP", "STOMP", "STRIKE", "SWIPE", "THROB", "THRUST", "THUD", "THUMP",
            "THWACK", "TICK", "TINGLE", "TINK", "TINKLE", "WHACK", "WHAM", "WHIP", "WHIR", "WHIRR", "WHOOSH",
            "WOOSH", "ZAP", "ZING", "ZOOM", "BARRAGE", "CLATTER", "CRACKLE", "CROW", "CUT", "DING", "DING-DONG",
            "DRONE", "FLICKER", "FIZZ", "FLUTTER", "GASP", "GLARE", "GROAN", "GROWL", "GRUMBLE", "HEAVY BREATHING",
            "HOWL", "HUZZAH", "MAGIC", "MURMUR", "POOF", "PULSE", "ROAR", "RUMBLE", "SIZZLE", "SLITHER", "SNARL",
            "SQUEAK", "SWOOSH", "TICKLE", "TWANG", "TWITTER", "WAIL", "WHIRL", "WHISTLE", "YAWN"
        ]

        self.fight_phrases = {
            "blow": [
                "axe kick", "body slam", "butt strike", "dragon kick", "elbow strike", "falcon punch",
                "flying elbow", "flying knee", "front kick", "hammerfist", "haymaker punch", "heel kick",
                "headbutt", "judo chop", "knee strike", "palm strike", "pocket bees", "roundhouse kick",
                "shoulder strike", "side kick", "spinning backfist", "superman punch", "suplex"
            ],
            "blow_type": [
                "apocalyptic", "bone-breaking", "brutal", "catastrophic", "crushing", "damaging", "deadly",
                "destructive", "ferocious", "fierce", "horrendous", "intense", "lethal", "merciless", "overwhelming",
                "ruinous", "savage", "shattering", "soul-crushing", "spine-chilling", "traumatic", "violent"
            ],
            "victory": [
                "achieves victory", "claims the crown", "conquers", "crushes the opposition", "dominates",
                "emerges triumphant", "holds the title", "is the champion", "is the victor", "overcomes",
                "prevails", "proves superiority", "seizes the glory", "stands victorious", "triumphs",
                "vanquishes", "wins"
            ]
        }
        self.rekt_list = [
            '12 Years a Rekt', '2001: A Rekt Odyssey', 'A Game of Rekt', 'Batrekt Begins', 'Braverekt', 'Call of Rekt: Modern Reking 2',
            'Catcher in the Rekt', 'Cash4Rekt.com', 'Christopher Rektellston', 'Citizen Rekt', 'Finding Rekt', 'Fiddler on the Rekt',
            'Forrekt Gump', 'Gladirekt', 'Grapes of Rekt', 'Grand Rekt Auto V', 'Great Rektspectations', 'Gravirekt', 'Hachi: A Rekt Tale',
            'Harry Potter: The Half-Rekt Prince', 'I am Fire, I am Rekt', 'Left 4 Rekt', 'Legend Of Zelda: Ocarina of Rekt', 'Lord of the Rekts: The Reking of the King',
            'Oedipus rekt', 'Painting The Roses Rekt', 'Paper Scissors Rekt', 'Parks and Rekt', 'Pokemon: Fire Rekt', 'Professor Rekt',
            'Rekt', 'Rekt Box 360', 'Rekt It Ralph', 'Rekt TO REKT ass to ass', 'Rekt and Roll', 'Rekt markes the spot', 'Rekt-22',
            'RektCraft', 'RektE', 'Rektflix', 'Rektal Exam', 'Requiem for a Rekt', 'REKT-E', 'REKT TO REKT ass to ass', 'Shrekt',
            'Ship Rekt', 'Singin\' In The Rekt', 'Spirekted Away', 'Star Trekt', 'Star Wars: Episode VI - Return of the Rekt', 'Terminator 2: Rektment Day',
            'The Arekters', 'The Good, the Bad, and The Rekt', 'The Green Rekt', 'The Hunt for Rekt October', 'The Rekt Files', 'The Rekt Knight',
            'The Rekt Knight Rises', 'The Rekt Side Story', 'The Rekt Ultimatum', 'The Rektfather', 'The Shawshank Rektemption', 'The Silence of the Rekts',
            'There Will Be Rekt', 'Tyrannosaurus Rekt'
        ]

        self.motions = [
            'addresses', 'agitates', 'ambles', 'antagonises', 'applauds', 'apologises', 'assaults', 'bangs',
            'bakes', 'bequeaths', 'bemoans', 'beseeches', 'blipps', 'brandishes', 'brags', 'butts', 'chastises',
            'cheers', 'chokes', 'clucks', 'compiles', 'deciphers', 'decrys', 'dangles', 'digests', 'displays',
            'dives', 'donger', 'drops', 'drags', 'drives', 'dawdles', 'eviscerates', 'excavates', 'exclaims',
            'fingers', 'flops', 'folds', 'fastens', 'flaps', 'folds', 'flutters', 'gathers', 'gravitates',
            'greases', 'grabs', 'gyrates', 'helicopters', 'hogs', 'honks', 'hugs', 'hypnotises', 'inserts',
            'intensifies', 'interviews', 'irritates', 'itches', 'jogs', 'jumps', 'leans', 'loves', 'locks',
            'manipulates', 'mispronounces', 'manipulates', 'manipulates', 'manipulates', 'murders', 'neglects',
            'negotiates', 'neighs', 'offends', 'opens', 'overflows', 'parades', 'polishes', 'preaches', 'prowls',
            'queues', 'questions', 'raises', 'rinses', 'reiterates', 'runs', 'salivates', 'satisfys', 'scowls',
            'screams', 'shakes', 'sheathes', 'screams', 'shakes', 'springs', 'stimulates', 'sways', 'swings',
            'taps', 'telephones', 'tickles', 'traipses', 'thaws', 'thrusts', 'twirls', 'twists', 'vaginas',
            'waves', 'washes', 'whoolies', 'wobbles', 'wobbles', 'zigzags'
        ]
        insults_file = os.path.join("data", "list-of-insults.txt")
        try:
            with open(insults_file) as f:
                self.insult_list = [line.strip() for line in f]
        except Exception as e:
            logger.error(f"Error loading insult list: {e}")
            self.insult_list = ["error opening the list"]

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Attack module has been loaded")
        try:
            if self.stats:
                # Donger
                self.stats.register_cog(self.stats.db_path, "donger", ["initiated", "attacked"])
                logger.info("Registering donger with stats")
                # Fight
                self.stats.register_cog(self.stats.db_path, "fight", ["win", "lose"])
                logger.info("Registering fight with stats")
                # Rekt
                self.stats.register_cog(self.stats.db_path, "rekt", ["initated", "rekt"])
                # Insult
                self.stats.register_cog(self.stats.db_path, "insult", ["insulting", "insulted"])
            else:
                logger.warning("Stats cog not found.")
        except Exception as e:
            logger.error(f"Error registering submodule with stats: {e}")


    @commands.command(aliases=['donger'], help="Motions your donger Example: !donger <user>")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def Donger(self, ctx, member: discord.Member = None):
        if member == ctx.message.author:
            random.seed()
            motion = self.motions[random.randrange(len(self.motions))]
            dongermsg = f"{ctx.message.author.mention} {motion} with their own donger 8====D~ ~ ~"
            if self.stats:
                try:
                    await self.stats.update_stats("donger", userid=str(ctx.author.id), initiated=1)
                    logger.debug("Updating donger stats")
                except:
                    logger.debug("ERROR: Updating donger stats")
            await ctx.send(dongermsg)
        elif member:
            random.seed()
            motion = self.motions[random.randrange(len(self.motions))]
            dongermsg = f"{ctx.message.author.mention} {motion} their donger at {member.mention} 8====D~ ~ ~"
            if self.stats:
                await self.stats.update_stats("donger", userid=str(ctx.author.id), initiated=1)
                await self.stats.update_stats("donger", userid=str(member.mention.strip("<!@>")), attacked=1)
                logger.debug("Updating donger stats")
            await ctx.send(dongermsg)
        elif not member:
            await ctx.send("8====D~ ~ ~")

    @commands.command(aliases=['fight'], help="Fights another user. Example: !fight <userA> [<userB>]")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def Fight(self, ctx, member: discord.Member = None, member2: discord.Member = None):
        fighter1 = member2.mention if member2 else ctx.author.mention
        fighter2 = member.mention if member else random.choice(ctx.channel.members).mention
        random.seed()
        if random.random() < 0.5:
            out = f"{random.choice(self.sounds)}! {random.choice(self.sounds)}! {random.choice(self.sounds)}! {fighter1} {random.choice(self.fight_phrases['victory'])} over {fighter2} with a {random.choice(self.fight_phrases['blow_type'])} {random.choice(self.fight_phrases['blow'])}."
            if self.stats:
                await self.stats.update_stats("fight", userid=str(fighter1.strip("<!@>")), win=1)
                await self.stats.update_stats("fight", userid=str(fighter2.strip("<!@>")), lose=1)
                logger.debug("Updating fight stats")
        else:
            out = f"{random.choice(self.sounds)}! {random.choice(self.sounds)}! {random.choice(self.sounds)}! {fighter2} {random.choice(self.fight_phrases['victory'])} over {fighter1} with a {random.choice(self.fight_phrases['blow_type'])} {random.choice(self.fight_phrases['blow'])}."
            if self.stats:
                await self.stats.update_stats("fight", userid=str(fighter2.strip("<!@>")), win=1)
                await self.stats.update_stats("fight", userid=str(fighter1.strip("<!@>")), lose=1)
                logger.debug("Updating fight stats")
        await ctx.send(out)

    @commands.command(aliases=['rekt'], help="Rekts another user. Example: !rekt <userA>")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def Rekt(self, ctx, member: discord.Member = None):
        if member:
            message = f"{member.mention} {random.choice(self.rekt_list)}"
            if self.stats:
                await self.stats.update_stats("rekt", userid=str(ctx.author.mention).strip("<!@>"), initated=1)
                await self.stats.update_stats("rekt", userid=str(member.mention).strip("<!@>"), rekt=1)
        else:
            message = random.choice(self.rekt_list)
        await ctx.send(message)


    @commands.command(help="Insult another member! Usage: `!insult @username`.")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def insult(self, ctx, member: discord.Member = None):
        random.seed()
        insult_msg = random.choice(self.insult_list).strip()
        target = member.mention if member else ctx.author.mention
        if self.stats:
            await self.stats.update_stats("insult", userid=str(ctx.author.mention).strip("<!@>"), insulting=1)
            await self.stats.update_stats("insult", userid=str(member.mention).strip("<!@>"), insulted=1)
        await ctx.send(f"Hey, {target}! You're a {insult_msg}!")

def setup(bot):
    bot.add_cog(Attack(bot))

