import discord
from discord.ext import commands
import random


class fight(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("Fight module has been loaded\n-----")

    @commands.command(aliases=['Fight'])
    async def fight(self, ctx, member: discord.Member = None, member2: discord.Member = None):
        if member2:
            fighter1 == member.mention
        else:
            fighter1 = ctx.message.author.mention
        if member:
            fighter2 = member.mention
        else:
            fighter2 = random.choice(ctx.message.channel.members).mention
        bang = ["BANG", "POW", "SLAM", "WHACK", "SLAP", "KAPOW", "ZAM", "BOOM"]
        blow_type = ["devastating", "destructive", "ruthless", "damaging", "ruinous", "catastrophic",
                     "traumatic", "shattering", "overwhelming", "crushing", "fierce", "deadly", "lethal",
                     "fatal", "savage", "violent"]
        victory = ["wins", "stands victorious", "triumphs", "conquers", "is the champion", "is the victor"]
        blow = ["uppercut", "hammerfist", "elbow strike", "shoulder strike", "front kick", "side kick",
                "roundhouse kick", "knee strike", "butt strike", "headbutt", "haymaker punch", "palm strike",
                "pocket bees"]

        random.seed()
        if random.random() < .5:
            out = "{}! {}! {}! {} {} over {} with a {} {}.".format(random.choice(bang), random.choice(bang),
                                                                   random.choice(bang), fighter1,
                                                                   random.choice(victory), fighter2,
                                                                   random.choice(blow_type), random.choice(blow))
        else:
            out = "{}! {}! {}! {} {} over {} with a {} {}.".format(random.choice(bang), random.choice(bang),
                                                                   random.choice(bang), fighter2,
                                                                   random.choice(victory),fighter1,
                                                                   random.choice(blow_type), random.choice(blow))

        await ctx.send(out)


def setup(bot):
    bot.add_cog(fight(bot))
