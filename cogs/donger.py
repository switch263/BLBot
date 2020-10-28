import discord
from discord.ext import commands
import random

class donger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("Donger module has been loaded\n-----")

    @commands.command(aliases=['donger'])
    async def Donger(self, ctx, member: discord.Member = None):
        motions = ['neighs', 'negotiates', 'ogles', 'neglects', 'quavers', 'scowls', 'telephones', 'salivates',
                   'satisfys', 'sheathes', 'traipses', 'parades', 'offends', 'manipulates', 'compiles', 'mispronounces',
                   'murders', 'runs', 'vaginas', 'locks', 'whoolies', 'bangs', 'drops', 'itches', 'hugs', 'bakes',
                   'fastens', 'grabs', 'jumps', 'jogs', 'questions', 'rinses', 'opens', 'knits', 'addresses', 'bemoans',
                   'beseeches', 'chastises', 'deciphers', 'dawdles', 'dangles', 'cheers', 'decrys', 'antagonises',
                   'apologises', 'assaults', 'brandishes', 'brags', 'clucks', 'digests', 'emphasises', 'ensnares',
                   'gravitates', 'hogs', 'head-butts', 'butts', 'honks', 'fingers', 'eviscerates', 'excavates', 'folds',
                   'exclaims', 'hypnotises', 'interviews', 'raises', 'flaps', 'wobbles', 'shakes', 'gyrates',
                   'helicopters', 'flops', 'agitates', 'atobes', 'waves his donger in the air like he just dont care',
                   'blipps', 'reiterates', 'drives', 'leans', 'polishes', 'chokes', 'announces', 'applauds', 'compiles',
                   'displays', 'drags', 'greases', 'intensifies', 'irritates', 'loves', 'manipulates', 'overflows',
                   'preaches', 'queues', 'screams', 'thaws', 'thrusts', 'tickles', 'degloves', 'springs', 'stimulates',
                   'washes', 'inserts', 'bequeaths']
        if member == ctx.message.author:
            random.seed()
            motion = motions[random.randrange(len(motions))]
            dongermsg = "{} {} with their own donger 8====D~ ~ ~"
            dongermsg = dongermsg.format(ctx.message.author.mention, motion)
            await ctx.send(dongermsg)
        elif member:
            random.seed()
            motion = motions[random.randrange(len(motions))]
            dongermsg = "{} {} their donger at {} 8====D~ ~ ~"
            dongermsg = dongermsg.format(ctx.message.author.mention, motion, member.mention)
            await ctx.send(dongermsg)
        elif not member:
            await ctx.send("8====D~ ~ ~")


def setup(bot):
    bot.add_cog(donger(bot))
