import discord
from discord.ext import commands
import random

class FightCommand(commands.Cog):
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


    @commands.command(help="Fightds another user. Example: !fight <@userA> [<userB>]")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def fight(self, ctx, member: discord.Member = None, member2: discord.Member = None):
        fighter1 = member2.mention if member2 else ctx.author.mention
        fighter2 = member.mention if member else random.choice(ctx.channel.members).mention
        random.seed()
        if random.random() < 0.5:
            out = f"{random.choice(self.sounds)}! {random.choice(self.sounds)}! {random.choice(self.sounds)}! {fighter1} {random.choice(self.fight_phrases['victory'])} over {fighter2} with a {random.choice(self.fight_phrases['blow_type'])} {random.choice(self.fight_phrases['blow'])}."
        else:
            out = f"{random.choice(self.sounds)}! {random.choice(self.sounds)}! {random.choice(self.sounds)}! {fighter2} {random.choice(self.fight_phrases['victory'])} over {fighter1} with a {random.choice(self.fight_phrases['blow_type'])} {random.choice(self.fight_phrases['blow'])}."
        await ctx.send(out)

def setup(bot):
    bot.add_cog(FightCommand(bot))

