import discord
from discord.ext import commands
import sqlite3
import random
import time
import os
import logging
import datetime

logger = logging.getLogger(__name__)

class Duels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.stats = bot.get_cog('Stats')

        self.victory_cries = [
            "Annihilation! Utter domination!",
            "A flawless victory! A legend is born!",
            "They crushed their foe like a bug! Brutal!",
            "That was barely a challenge! Someone get them a worthy opponent!",
            "A triumph worthy of the history books!",
            "Their reign of terror begins!"
        ]
        self.preposition_phrases = ["with a", "using a", "through a", "by employing a", "with the help of a"]

        self.action_verbs = ["**BANG**", "**POW**", "**SLAM**", "**WHACK**", "**SLAP**", "**KAPOW**", "**ZAM**", "**BOOM**", "**TICKLE**", "**SNORT**"]

        self.victory_actions = [
            "crushing",
            "devastating",
            "unstoppable",
            "decisive",
            "remarkable",
            "dazzling",
            "inescapable",
            "valiant",
            "honorable",
            "awe-inspiring",
            "surprisingly lucky",
            "questionable",
            "unexpectedly fortunate",
            "baffling"
        ]

        self.victory_descriptions = [
            "pocket bees",
            "hank hill",
            "haymaker punch",
            "lightning-fast jab",
            "sneaky uppercut",
            "powerful roundhouse kick",
            "strategic counterattack",
            "swift left hook",
            "calculated strike",
            "masterful parry",
            "legendary shield bash",
            "flurry of misdirected blows",
            "sneeze-induced headbutt",
            "stumble that accidentally trips the opponent",
            "swarm of confused pigeons",
            "perfectly-timed dodge",
            "well-placed banana peel",
            "series of bewildering dance moves",
            "distractingly shiny object",
            "bout of uncontrollable laughter",
            "opponent's sudden sneeze attack",
            "ill-timed wardrobe malfunction",
            "well-timed intervention by a passing squirrel",
            "cloud of dust kicked up at the perfect moment",
            "tripping over one's own shoelace, but somehow winning",
            "Bill Cosby's chocolate puddin'",
            "barrage of pop culture references",
            "perfectly executed keyboard combo",
            "tactical deployment of a pocket protector",
            "hacking the opponent's muscle memory",
            "unexpected overflow error",
            "outmaneuvering with superior meme knowledge",
            "summoning the power of a rare collectible",
            "surprise attack with a foam LARP sword",
            "glitch in the opponent's battle algorithm",
            "short-circuiting the opponent with a logic paradox",
            "critical roll failure",
            "devastatingly accurate adult toy (narrator: Yes, it was that small)",
            "accidentally rolling a natural 20",
            "confusing the opponent with Klingon insults",
            "buffer overflow caused by excessive taunting",
            "outwitting the opponent with obscure trivia",
            "unleashing the power of an ancient ASCII sigil",
            "winning via flawless 8-bit pixel dodge",
            "blinding by the light of a CRT monitor",
            "forcing a ragequit with an unbalanced build",
            "poorly explained spell",
            "unveiling an unstoppable limited-edition action figure",
            "asserting dominance through a flawless \"your mom\" joke",
            "deploying a confusing array of fandom references",
            "bribing the opponent with rare comic book issues",
            "superior cosplay critique",
            "accidentally summoning a minor demon",
            "rewriting the laws of combat with an unpatched exploit",
            "activating hidden cheat codes",
            "repurposing a vintage game cartridge as a throwing weapon",
            "mesmerizing dice roll",
            "disrupting the space-time continuum to alter the outcome",
            "unleashing the fury of a limited edition energy drink",
            "summoning the spirits of forgotten video game characters",
            "redirecting a firewall to disrupt the opponent's flow",
            "laughable attempt at using a meme",
            "uno reverse followed by 3x draw 4's while also not shouting uno",
            "meeting them at Cars and Coffee while driving a mustang",
            "strategically re-rolling with a loaded die",
            "the power of an obscure fandom wiki",
            "overwhelming the opponent with a lengthy debate on memes",
            "weird uncle that talks about politics at holiday gatherings",
            "your mom jokes, that hit surprisingly to home cause your mom do be that way"
        ]


    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("duel module has been loaded")
        try:
            if self.stats:
                self.stats.register_cog("duel", ["wins", "losses"])
                logger.info("Registering duel with stats")
            else:
                logger.warning("Stats cog not found.")
        except Exception as e:
            logger.error(f"Error registering duel with stats: {e}")

    def generate_victory_message(self, winner_mention, loser_mention):
        actions = "! ".join(random.choices(self.action_verbs, k=3))
        victory_action = random.choice(self.victory_actions)
        victory_description = random.choice(self.victory_descriptions)
        random_preposition = random.choice(self.preposition_phrases)

        message = f"{actions}! {winner_mention} {victory_action} over {loser_mention} {random_preposition} {victory_description}."
        return message

    @commands.command(help="Challenge another member to a duel! Usage: `!duel @username`. Can only be used guild-wide once per hour.", description="Initiates a duel between the command invoker and the specified member. Best 2 out of 3.")
    @commands.cooldown(rate=1, per=3600, type=commands.BucketType.guild)
    async def duel(self, ctx, member: discord.Member = None):
        if member is None:
            await ctx.send("To duel someone, use `!duel @username`. For stats, use `!stats duel @username`.")
            return

        await ctx.send(f"ATTENTION EVERYONE....{ctx.author.mention} has challenged {member.mention} to a duel... let the battle commence, best 2/3")

        time.sleep(5)

        score = {ctx.author: 0, member: 0}

        for round_num in range(1, 4):
            await ctx.send(f"ROUND {round_num}")
            time.sleep(2)

            round_victor = random.choice([ctx.author, member])
            score[round_victor] += 1
            victory_message = self.generate_victory_message(round_victor.mention, (member if round_victor == ctx.author else ctx.author).mention)
            await ctx.send(victory_message)

            if score[round_victor] == 2:
                if self.stats:
                    await self.stats.update_stats("duel", userid=str(round_victor.id), wins=1)
                    await self.stats.update_stats("duel", userid=str((member if round_victor == ctx.author else ctx.author).id).strip("<!@>"), losses=1)
                    logger.debug("Updating duel stats")
                await ctx.send("GAME OVER! Victory to...")
                await ctx.send(f"{round_victor.mention}!! {random.choice(self.victory_cries)}")
                break
        
def setup(bot):
    bot.add_cog(Duels(bot))


