from discord.ext import commands
import random

class donger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("Donger module has been loaded\n-----")

    @commands.command(aliases=['donger'])
    async def donger(self, ctx, *member: discord.Member):
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
        if member:
            random.seed()
            motion = motions[random.randrange(len(motions))]
            await ctx.send("{} {} thier donger at {} 8====D~ ~ ~").format(ctx.message.author.mention, motion, member)
        else:
            await ctx.send("8====D~ ~ ~")

def setup(bot):
    bot.add_cog(temperature(bot))

def donger(bot, trigger):
    nick = trigger.nick
    motions = ['neighs','negotiates','ogles','neglects','quavers','scowls','telephones','salivates','satisfys','sheathes','traipses','parades','offends','manipulates','compiles','mispronounces','murders','runs','vaginas','locks','whoolies','bangs','drops','itches','hugs','bakes','fastens','grabs','jumps','jogs','questions','rinses','opens','knits','addresses','bemoans','beseeches','chastises','deciphers','dawdles','dangles','cheers','decrys','antagonises','apologises','assaults','brandishes','brags','clucks','digests','emphasises','ensnares','gravitates','hogs','head-butts','butts','honks','fingers','eviscerates','excavates','folds','exclaims','hypnotises','interviews','raises','flaps','wobbles','shakes','gyrates','helicopters','flops','agitates','atobes','waves his donger in the air like he just dont care', 'blipps','reiterates','drives','leans','polishes','chokes', 'announces','applauds','compiles','displays','drags','greases','intensifies','irritates','loves','manipulates','overflows','preaches','queues','screams','thaws','thrusts','tickles','degloves','springs','stimulates', 'washes', 'inserts', 'bequeaths']
    random.seed()
    motion = motions[random.randrange(len(motions))]
    if trigger.group(2):
        if nick in trigger.group(2):
            out = "%s %s with their own donger 8====D~ ~ ~" % (nick, motion)
        else:
            out = "%s %s their donger at %s 8====D~ ~ ~" % (nick, motion, trigger.group(2))
            #out = "%s %s with %s's donger 8====D~ ~ ~" % (nick, motion, trigger.group(2))
    else:
        out = "8====D~ ~ ~"
    return bot.say(out)