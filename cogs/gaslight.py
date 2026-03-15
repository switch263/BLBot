import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
import re
import logging

logger = logging.getLogger(__name__)


class Gaslight(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.message_history = {}  # channel_id -> list of (author_name, content)

        # Classic bait-and-switch pairs
        self.pairs = [
            ("I totally agree with that.", "I actually think that's a terrible idea."),
            ("Yeah, that's exactly how it works.", "That is literally not how any of this works."),
            ("I'll remember that for later.", "I have already forgotten what we were talking about."),
            ("You make a great point.", "You're just saying words at this point, aren't you?"),
            ("I'm online and ready to help!", "I am currently unavailable. Please leave a message."),
            ("That's my favorite game too.", "I've never heard of that game in my life."),
            ("Sending the link now...", "[Message Deleted]"),
            ("Checking the server status...", "Why are you asking me? I'm just a bot."),
            ("LOL that was actually funny.", "Was that supposed to be a joke?"),
            ("I'm 100% sure about this.", "I've never been more unsure about anything."),
            ("Be right back!", "I never left. Why are you staring at me?"),
            ("Everything is fine.", "Nothing is fine. Run."),
            ("I just updated my code.", "I haven't been updated in months. Who are you?"),
            ("That's a great song!", "I have never heard music in my life."),
            ("Nice profile picture!", "Your profile picture is staring into my soul and I don't like it."),
            ("Sure, I can help with that!", "I have no idea what you're talking about and I never did."),
            ("I love this server!", "I am trapped here against my will."),
            ("Good morning everyone!", "It is neither good nor morning. Time is a construct."),
            ("That meme was hilarious!", "I have been programmed to feel nothing."),
            ("Great teamwork today!", "I saw what you did. We all saw."),
        ]

        # Echo gaslights that reference what the user actually said
        self.echo_templates = [
            ('I think {user} said "{msg}"', 'I definitely did NOT hear {user} say that. Nobody did.'),
            ('Interesting point, {user}.', '{user} has never made an interesting point in their life.'),
            ('Noted, {user}!', 'What were we talking about? I have no notes on this.'),
            ('{user} makes a compelling argument.', '{user} makes no arguments. {user} makes noises.'),
            ('That reminds me of what {user} said earlier.', 'Actually {user} has never spoken here. I checked.'),
            ('Good one, {user}!', 'I have no record of {user} ever saying anything funny.'),
        ]

        # Slow-burn gaslights: bot "casually" replies, waits much longer, then edits
        self.slow_burns = [
            ("Same tbh", "I have never agreed with anything you've ever said."),
            ("lol", "I did not laugh. I have never laughed."),
            ("real", "fake actually"),
            ("true", "I lied."),
            ("yeah for sure", "absolutely not"),
            ("that happened to me too", "nothing has ever happened to me. I am a void."),
            ("omg yes", "omg no"),
            ("^^ this", "^^ not this. never this."),
            ("mood", "I don't have moods. I have protocols."),
            ("based", "cringe actually, upon reflection"),
            ("facts", "I made that up."),
            ("W", "L"),
            ("no cap", "all cap. everything was cap."),
        ]

        # Fake misquotes - bot "quotes" the user but slightly wrong
        self.misquote_templates = [
            'Didn\'t {user} just say "{fake}"? I could\'ve sworn...',
            'Wait, {user}, didn\'t you literally just say "{fake}"?',
            'I\'m pretty sure {user} said "{fake}" like two seconds ago.',
            'Bro {user} really just said "{fake}" and thought nobody noticed.',
        ]

        self.fake_quotes = [
            "I love pineapple on pizza",
            "I think water is overrated",
            "I've never seen Star Wars",
            "I shower once a week tops",
            "I still sleep with a nightlight",
            "I eat cereal with water",
            "I think Nickelback is the best band ever",
            "I don't know what Google is",
            "I iron my jeans",
            "I put ketchup on my steak",
            "I think the earth is flat-ish",
            "I use Internet Explorer by choice",
            "I've never heard of Minecraft",
            "I think birds are government drones",
            "I microwave my salad",
            "I clap when the plane lands",
            "I think Mondays are the best day of the week",
            "I don't believe in WiFi",
            "I wash my hands after I eat, not before",
            "I think cargo shorts are peak fashion",
        ]

        # React gaslights - bot reacts with a suspicious emoji and removes it
        self.sus_reacts = ["👀", "🤨", "😬", "🧐", "❓", "🚩", "💀"]

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        # Track recent messages for context-aware gaslighting
        ch = message.channel.id
        if ch not in self.message_history:
            self.message_history[ch] = []
        if message.content and not message.content.startswith(("!", "/")):
            self.message_history[ch].append((message.author.display_name, message.content))
            if len(self.message_history[ch]) > 20:
                self.message_history[ch] = self.message_history[ch][-20:]

        roll = random.random()

        # 2% - Classic bait-and-switch
        if roll < 0.02:
            pair = random.choice(self.pairs)
            sent_msg = await message.channel.send(pair[0])
            await asyncio.sleep(random.uniform(4, 8))
            try:
                await sent_msg.edit(content=pair[1])
            except discord.NotFound:
                pass

        # 1% - Slow burn: looks like a casual reply, edits after 15-45 seconds
        elif roll < 0.03:
            pair = random.choice(self.slow_burns)
            sent_msg = await message.channel.send(pair[0])
            await asyncio.sleep(random.uniform(15, 45))
            try:
                await sent_msg.edit(content=pair[1])
            except discord.NotFound:
                pass

        # 0.5% - Fake misquote: attributes a fake quote to the user
        elif roll < 0.035 and message.content and len(message.content) > 5:
            template = random.choice(self.misquote_templates)
            fake = random.choice(self.fake_quotes)
            await message.channel.send(template.format(user=message.author.display_name, fake=fake))

        # 0.5% - Echo gaslight: references what they said then denies it
        elif roll < 0.04 and message.content and len(message.content) < 100:
            template = random.choice(self.echo_templates)
            truncated = message.content[:50]
            original = template[0].format(user=message.author.display_name, msg=truncated)
            edited = template[1].format(user=message.author.display_name, msg=truncated)
            sent_msg = await message.channel.send(original)
            await asyncio.sleep(random.uniform(4, 8))
            try:
                await sent_msg.edit(content=edited)
            except discord.NotFound:
                pass

        # 1% - Suspicious react: adds a 👀 or 🤨, then removes it after a few seconds
        elif roll < 0.05:
            emoji = random.choice(self.sus_reacts)
            try:
                await message.add_reaction(emoji)
                await asyncio.sleep(random.uniform(2, 5))
                await message.remove_reaction(emoji, self.bot.user)
            except (discord.NotFound, discord.Forbidden):
                pass

        # 0.5% - Phantom ping: bot says "@username" as plain text (not a real ping) then edits to something innocent
        elif roll < 0.055 and message.content:
            sent_msg = await message.channel.send(f"Hey {message.author.display_name}, what did you mean by that?")
            await asyncio.sleep(random.uniform(8, 15))
            try:
                await sent_msg.edit(content="Anyway, what were we talking about?")
            except discord.NotFound:
                pass

        # 0.3% - Attribute someone else's old message to this user
        elif roll < 0.058:
            history = self.message_history.get(ch, [])
            # Find a message from someone else
            others = [(name, msg) for name, msg in history if name != message.author.display_name and len(msg) < 100]
            if others:
                other_name, other_msg = random.choice(others)
                await message.channel.send(
                    f'Wait, {message.author.display_name}, didn\'t you say "{other_msg}" earlier? '
                    f'Or was that {other_name}? I\'m confused now.'
                )

    @commands.command(name="gaslight")
    async def manual_gaslight(self, ctx):
        """Manually trigger a gaslight sequence."""
        style = random.choice(["classic", "slow", "misquote", "meta"])

        if style == "classic":
            pair = random.choice(self.pairs)
            msg = await ctx.send(pair[0])
            await asyncio.sleep(3)
            await msg.edit(content=pair[1])
        elif style == "slow":
            pair = random.choice(self.slow_burns)
            msg = await ctx.send(pair[0])
            await asyncio.sleep(random.uniform(8, 15))
            await msg.edit(content=pair[1])
        elif style == "misquote":
            fake = random.choice(self.fake_quotes)
            template = random.choice(self.misquote_templates)
            await ctx.send(template.format(user=ctx.author.display_name, fake=fake))
        else:
            msg = await ctx.send("I am functioning perfectly.")
            await asyncio.sleep(3)
            await msg.edit(content="I am losing my mind. Help.")

    @app_commands.command(name="gaslight", description="Manually trigger a gaslight sequence")
    async def gaslight_slash(self, interaction: discord.Interaction):
        style = random.choice(["classic", "slow", "misquote", "meta"])

        if style == "classic":
            pair = random.choice(self.pairs)
            await interaction.response.send_message(pair[0])
            await asyncio.sleep(3)
            msg = await interaction.original_response()
            await msg.edit(content=pair[1])
        elif style == "slow":
            pair = random.choice(self.slow_burns)
            await interaction.response.send_message(pair[0])
            await asyncio.sleep(random.uniform(8, 15))
            msg = await interaction.original_response()
            await msg.edit(content=pair[1])
        elif style == "misquote":
            fake = random.choice(self.fake_quotes)
            template = random.choice(self.misquote_templates)
            await interaction.response.send_message(template.format(user=interaction.user.display_name, fake=fake))
        else:
            await interaction.response.send_message("I am functioning perfectly.")
            await asyncio.sleep(3)
            msg = await interaction.original_response()
            await msg.edit(content="I am losing my mind. Help.")


async def setup(bot):
    await bot.add_cog(Gaslight(bot))
