import discord
from discord.ext import commands
import sqlite3
import random
import time
import asyncio
import os

class Duels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_file = "duel.db"
        self.create_tables()

        self.round_announcements = [
            "The tension is palpable! Get ready for...",
            "Buckle up folks, this round's gonna be wild...",
            "May the odds be ever in your favor (or not)...",
            "Let the chaotic combat commence!",
            "A battle for the ages is about to unfold...",
            "Witness the clash of titans!"
        ]

        self.combat_quips = [
            "A flurry of furious fingers!",
            "An epic clash of keyboards!",
            "The sound of frantic typing echoes through the server...",
            "Sweat drips from their brows as they strategize...",
            "A surprise meme attack! It's super effective!",
            "They unleash a devastating emote barrage!",
            "With a mighty keystroke, they land a critical hit!"
        ]

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
            "uno reverse followed by 3x draw 4's while also not shouting uno"
            "meeting them at Cars and Coffee while driving a mustang",
            "strategically re-rolling with a loaded die",
            "the power of an obscure fandom wiki",
            "overwhelming the opponent with a lengthy debate on memes",
            "weird uncle that talks about politics at holiday gatherings",
            "your mom jokes, that hit surprisingly to home cause your mom do be that way"
        ]

    def create_tables(self):
        # Security: Use context manager for database connections
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS cooldowns (
                        guild_id INTEGER,
                        channel_id INTEGER,
                        last_duel INTEGER
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS stats (
                        guild_id INTEGER,
                        user_id INTEGER,
                        wins INTEGER DEFAULT 0,
                        losses INTEGER DEFAULT 0,
                        PRIMARY KEY (guild_id, user_id)
                    )
                ''')
                conn.commit()
        except sqlite3.Error as e:
            print(f"Database error creating tables: {e}")

    def get_user_stats(self, guild_id, user_id):
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT wins, losses FROM stats WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
                stats = cursor.fetchone()
                return stats if stats else (0, 0)
        except sqlite3.Error as e:
            print(f"Database error getting stats: {e}")
            return (0, 0)

    def get_top_stats(self, guild_id):
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id, wins, losses FROM stats WHERE guild_id = ? ORDER BY wins DESC LIMIT 3", (guild_id,))
                top_stats = cursor.fetchall()
                return top_stats
        except sqlite3.Error as e:
            print(f"Database error getting top stats: {e}")
            return []

    def record_duel_result(self, guild_id, winner_id, loser_id):
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO stats (guild_id, user_id, wins) VALUES (?, ?, 1) ON CONFLICT(guild_id, user_id) DO UPDATE SET wins = wins + 1", (guild_id, winner_id))
                cursor.execute("INSERT INTO stats (guild_id, user_id, losses) VALUES (?, ?, 1) ON CONFLICT(guild_id, user_id) DO UPDATE SET losses = losses + 1", (guild_id, loser_id))
                conn.commit()
        except sqlite3.Error as e:
            print(f"Database error recording duel result: {e}")

    def is_on_cooldown(self, guild_id, channel_id):
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM cooldowns WHERE guild_id = ? AND channel_id = ?", (guild_id, channel_id))
                result = cursor.fetchone()
        except sqlite3.Error as e:
            print(f"Database error checking cooldown: {e}")
            return False, 0, 0

        if result is not None:
            last_duel_time = result[2]
            # Security: Validate and sanitize environment variable
            duel_cooldown = os.getenv('DUEL_COOLDOWN', '60')
            try:
                duel_cooldown = int(duel_cooldown)
                # Ensure cooldown is reasonable (1 second to 1 day)
                duel_cooldown = max(1, min(duel_cooldown, 86400))
            except ValueError:
                duel_cooldown = 60

            cooldown_end_time = last_duel_time + duel_cooldown
            current_time = int(time.time())
            if current_time < cooldown_end_time:
                seconds_remaining = max(0, cooldown_end_time - current_time)
                minutes, seconds = divmod(seconds_remaining, 60)
                return True, minutes, seconds
        return False, 0, 0


    def record_cooldown(self, guild_id, channel_id):
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO cooldowns (guild_id, channel_id, last_duel) VALUES (?, ?, ?)", (guild_id, channel_id, int(time.time())))
                conn.commit()
        except sqlite3.Error as e:
            print(f"Database error recording cooldown: {e}")

    def generate_victory_message(self, winner_mention, loser_mention):
        actions = "! ".join(random.choices(self.action_verbs, k=3))
        victory_action = random.choice(self.victory_actions)
        victory_description = random.choice(self.victory_descriptions)
        random_preposition = random.choice(self.preposition_phrases)

        message = f"{actions}! {winner_mention} {victory_action} over {loser_mention} {random_preposition} {victory_description}."
        return message


    @commands.command()
    async def duel(self, ctx, member: discord.Member = None):
        if member is None:
            await ctx.send("To duel someone, use `!duel @username`. For stats, use `!duel_stats @username`.")
            return

        is_cooldown, minutes, seconds = self.is_on_cooldown(ctx.guild.id, ctx.channel.id)
        if is_cooldown:
            await ctx.send(f"Hold your horses! Duels in this channel are on cooldown. Try again in {minutes} minutes and {seconds} seconds.")
            return

        await ctx.send(f"ATTENTION EVERYONE....{ctx.author.mention} has challenged {member.mention} to a duel... let the battle commence, best 2/3")

        # Security: Use asyncio.sleep instead of blocking time.sleep
        await asyncio.sleep(5)

        score = {ctx.author: 0, member: 0}

        for round_num in range(1, 4):
            await ctx.send(f"ROUND {round_num}")
            await ctx.send(random.choice(self.round_announcements))
            await ctx.send(random.choice(self.combat_quips))
            # Security: Use asyncio.sleep instead of blocking time.sleep
            await asyncio.sleep(2)

            round_victor = random.choice([ctx.author, member])
            score[round_victor] += 1
            victory_message = self.generate_victory_message(round_victor.mention, (member if round_victor == ctx.author else ctx.author).mention)
            await ctx.send(victory_message)

            if score[round_victor] == 2:
                self.record_duel_result(ctx.guild.id, round_victor.id, (member if round_victor == ctx.author else ctx.author).id)
                await ctx.send("GAME OVER! Victory to...")
                await ctx.send(f"{round_victor.mention}!! {random.choice(self.victory_cries)}")
                break

        self.record_cooldown(ctx.guild.id, ctx.channel.id)

    @commands.command()
    async def duel_stats(self, ctx, member: discord.Member = None):
        if member is None:
            member = ctx.author
        wins, losses = self.get_user_stats(ctx.guild.id, member.id)
        await ctx.send(f"{member.display_name}'s Duel Stats:\n**{wins}** wins, **{losses}** losses")

    @commands.command()
    async def duel_cooldown(self, ctx):
        is_cooldown, minutes, seconds = self.is_on_cooldown(ctx.guild.id, ctx.channel.id)
        if is_cooldown:
            await ctx.send(f"Duels in this channel are on cooldown. Come back in {minutes} minutes and {seconds} seconds.")
        else:
            await ctx.send("There's no duel cooldown currently. Challenge away!")

async def setup(bot):
    await bot.add_cog(Duels(bot))


