import json
import os
import logging
import discord
import random
from discord.ext import commands

class Donger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.stats = bot.get_cog('Stats')

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


    @commands.Cog.listener()
    async def on_ready(self):
        self.logger.info("Donger module has been loaded")
        try:
            if self.stats:
                self.stats.register_cog("donger", ["actor", "target"])
                logger.info("Registering duel with stats")
            else:
                logger.warning("Stats cog not found.")
        except Exception as e:
            logger.error(f"Error registering duel with stats: {e}")


    @commands.command(aliases=['donger'], help="Motions your donger Example: !donger <@user>")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def Donger(self, ctx, member: discord.Member = None):
        try:
            if member == ctx.message.author:
                motion = random.choice(self.motions)
                dongermsg = f"{ctx.message.author.mention} {motion} with their own donger 8====D~ ~ ~"
                if self.stats:
                    await self.stats.update_stats("donger", userid=str(ctx.author.id), actor=1)
                await ctx.send(dongermsg)
            elif member:
                motion = random.choice(self.motions)
                dongermsg = f"{ctx.message.author.mention} {motion} their donger at {member.mention} 8====D~ ~ ~"
                if self.stats:
                    await self.stats.update_stats("donger", userid=str(ctx.author.id), actor=1)
                    await self.stats.update_stats("donger", userid=str(member.id), target=1)
                await ctx.send(dongermsg)
            else:
                await ctx.send("8====D~ ~ ~")
        except Exception as e:
            self.logger.error(f"An error occurred: {e}")
            await ctx.send("Oops! Something went wrong.")

def setup(bot):
    bot.add_cog(Donger(bot))

