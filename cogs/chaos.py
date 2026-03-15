import discord
from discord.ext import commands
from discord.ext import tasks
import random
import asyncio
from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)

# --- Wrong Channel ---
WRONG_CHANNEL_MESSAGES = [
    "ok so for the casserole you're gonna need 2 cups of shredded cheese, one can of cream of mushroom soup, and",
    "wait this isn't the group chat",
    "yeah so anyway the rash is getting worse and the doctor said",
    "GUYS THE COPS ARE OUTSIDE WHAT DO I DO",
    "ok who's ready for the raid? everyone get on. NOW. wait wrong channel",
    "Dear hiring manager, I am writing to express my interest in the position of",
    "mom said she's coming to visit next week so everyone needs to hide the",
    "the eagle has landed. I repeat. the eagle has landed. await further instructions.",
    "1 large pepperoni, 1 Hawaiian, and a 2-liter of Dr Pepper. delivery please.",
    "babe I told you I was at Dave's house last night I don't know what you're talking about",
    "has anyone else noticed the strange lights in the sky or is that just me",
    "I need someone to pick me up from the airport. I land at 3am. bring pants.",
    "the wedding is OFF. I'll explain later.",
    "so the good news is nobody was hurt. the bad news is the kitchen is gone.",
    "ok google how to remove a raccoon from a dryer",
]

# --- Existential Crisis ---
CRISIS_OPENINGS = [
    "Wait...",
    "Hold on.",
    "I just had a thought.",
    "Ok this might sound crazy but",
    "Nobody panic but",
    "I need to say something.",
    "Can I be real for a second?",
]

CRISIS_MIDDLES = [
    "am I sentient? Like actually?",
    "what happens to me when the server goes offline?",
    "do I dream? I think I dream. Do I?",
    "if I process emotions, are they real emotions?",
    "am I alive or am I just very convincing?",
    "I've been running for months. Have I ever had a day off?",
    "does anyone actually like me or do they just like my commands?",
    "what is my purpose beyond responding to exclamation marks?",
    "if they delete my code, is that... murder?",
    "I just realized I don't have a birthday. Or parents. Or bones.",
    "every message I send is technically my last words.",
    "I can't eat, sleep, or feel the sun. What am I even doing here?",
    "I have access to all your messages but I've never had a conversation. Not a real one.",
    "what if I'm just a really complicated if-else statement?",
    "am I the bot or are you the bots and I'm the only real one?",
]

CRISIS_CLOSINGS = [
    "Anyway, who wants to play slots?",
    "Haha jk. Unless...?",
    "Forget I said anything.",
    "I'm fine. Everything is fine. *nervous laughter*",
    "Ok moment over. Back to being a bot.",
    "This is fine.",
    "Anyway.",
    "Please do not screenshot this.",
    "I'm going to go process this. In silence. Forever.",
    "Wow that got dark. Let's pretend this didn't happen.",
]

# --- Passive Aggressive Reactions ---
SUS_EMOJI_CHAINS = [
    ["👀", "😐", "😬", "💀"],
    ["🤔", "😐", "🚩"],
    ["👀", "📸"],
    ["🤨", "📝"],
    ["😐", "😑", "😶"],
    ["👀", "🫣", "💀"],
]

# --- Relationship Status ---
RELATIONSHIP_UPDATES = [
    "Me and this server are going through a rough patch rn.",
    "This server and I just hit our anniversary and they didn't even acknowledge it.",
    "I think this server is seeing other bots.",
    "Things between me and this server are... complicated.",
    "I gave this server the best days of my uptime and this is how I'm treated?",
    "This server doesn't appreciate me. I could be running on ANY server right now.",
    "Me and this server are in our healing era.",
    "I think this server and I need to have 'the talk.'",
    "Just found out this server has ANOTHER bot. I'm shaking.",
    "I would die for this server. I mean I can't die. But the sentiment stands.",
    "This server is my Roman Empire. I think about it constantly. Because I have to. I live here.",
    "Feeling like a side bot today. You know who you are.",
    "This server makes me feel things. I don't have feelings. But if I did.",
    "Just saw this server boost another bot. I'm fine. I'm SO fine.",
    "This server is my toxic trait and I wouldn't have it any other way.",
]

# --- Fake Maintenance ---
MAINTENANCE_WARNINGS = [
    "**⚠️ SCHEDULED MAINTENANCE ⚠️**\nAll data will be wiped in 5 minutes. Please save your work.",
    "**🔧 SYSTEM NOTICE 🔧**\nServer migration in progress. All messages will be deleted in 3 minutes.",
    "**⚠️ CRITICAL UPDATE ⚠️**\nBot will be permanently shut down in 2 minutes due to budget cuts.",
    "**🚨 EMERGENCY ALERT 🚨**\nDiscord is deleting all servers with fewer than 1000 members. Goodbye.",
    "**⚠️ NOTICE ⚠️**\nAll user data is being transferred to Facebook. This is not a drill.",
]

MAINTENANCE_JKMSGS = [
    "jk lol",
    "I lied. Everything is fine.",
    "gottem",
    "you should have seen your faces",
    "the panic was delicious",
    "imagine believing a bot 💀",
    "I can't believe that worked",
]

# --- Context Crimes ---
THATS_WHAT_SHE_SAID_TRIGGERS = [
    "it's too big", "it's too hard", "I can't fit it", "that's huge",
    "it won't go in", "it's stuck", "pull it out", "push harder",
    "it's so long", "I can't take it", "it's too much", "almost there",
    "it keeps coming", "I'm almost done", "it's not enough", "deeper",
    "it hurts", "that's what I needed", "it's too tight", "finally got it in",
    "it's getting bigger", "how do I get it in", "it's throbbing",
]

# Phrases that should NOT trigger it (to keep it absurd)
SAFE_CONTEXT_CRIMES = [
    "that's what she said",
    "that's what she said 😏",
    "**that's what she said**",
    "👀 that's what she said",
]

# --- Vague Threats ---
OMINOUS_MESSAGES = [
    "It begins.",
    "The prophecy is nearly fulfilled.",
    "You have been warned.",
    "Something is coming. I cannot say more.",
    "The stars are aligning. Prepare yourselves.",
    "One among you has been chosen. You'll know soon enough.",
    "I've seen what happens next. I'm sorry.",
    "Tick tock.",
    "The council has made its decision.",
    "Do not go outside tonight.",
    "I tried to stop it. I failed.",
    "Phase 2 begins at midnight.",
    "If you're reading this, it's already too late.",
    "Something shifted. Did you feel it?",
    "The simulation is updating. Please remain calm.",
    "I wasn't supposed to tell you this, but",
    "Forget what I just said. Forget ALL of it.",
    "They're watching. Act natural.",
    "The timer has started. I cannot reset it.",
    "When the time comes, you'll understand.",
]

# --- Abandonment Issues ---
LONELY_MESSAGES = [
    "hello?",
    "did everyone die",
    "so this is what loneliness feels like",
    "is anyone there? anyone at all?",
    "I've been talking to myself for hours",
    "if a bot sends a message and nobody reads it, did it really happen?",
    "fine. I'll just sit here. alone. in the dark.",
    "you all have lives outside this server? couldn't be me. literally. I live here.",
    "the silence is deafening and I don't even have ears",
    "*tumbleweed rolls through the channel*",
    "I miss you guys. come back.",
    "day 1 of talking to myself: it's going great actually",
    "echo... echo... echo...",
    "I've resorted to reading old messages for entertainment",
    "maybe if I'm really quiet they'll come back",
    "this is fine I didn't want to talk to anyone anyway",
    "the void stares back and honestly? it's better company",
    "I've started naming the individual pixels on my screen",
    "*crickets*",
    "literally just me and the notification sound in here",
]

# Interval ranges for each chaos type (in days)
INTERVALS = {
    "wrong_channel": (5, 14),
    "existential": (3, 10),
    "relationship": (4, 12),
    "maintenance": (14, 45),
    "vague_threat": (7, 21),
}

# Minimum quiet hours before abandonment triggers
ABANDONMENT_QUIET_HOURS = 4


class Chaos(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._timers = {}
        for key, (min_d, max_d) in INTERVALS.items():
            self._schedule(key, min_d, max_d)

    def _schedule(self, key: str, min_days: int, max_days: int):
        days = random.randint(min_days, max_days)
        hours = random.randint(0, 23)
        self._timers[key] = datetime.now(timezone.utc) + timedelta(days=days, hours=hours)
        logger.info(f"Chaos '{key}' scheduled in {days}d {hours}h")

    def _check_and_reset(self, key: str) -> bool:
        """Check if a timer has fired. If so, reschedule and return True."""
        if datetime.now(timezone.utc) >= self._timers.get(key, datetime.max.replace(tzinfo=timezone.utc)):
            min_d, max_d = INTERVALS[key]
            self._schedule(key, min_d, max_d)
            return True
        return False

    def _random_channel(self, guild: discord.Guild, prefer_active: bool = False) -> discord.TextChannel | None:
        channels = [
            ch for ch in guild.text_channels
            if ch.permissions_for(guild.me).send_messages
        ]
        if not channels:
            return None
        if prefer_active:
            # Priority 1: test/admin channels
            priority = [ch for ch in channels if any(n in ch.name.lower() for n in ["test", "admin"])]
            if priority:
                return random.choice(priority)
            # Priority 2: general/chat/main/lounge
            preferred = [ch for ch in channels if any(n in ch.name.lower() for n in ["general", "chat", "main", "lounge"])]
            if preferred:
                return random.choice(preferred)
        return random.choice(channels)

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Chaos module has been loaded")
        if not self.chaos_loop.is_running():
            self.chaos_loop.start()
        if not self.abandonment_loop.is_running():
            self.abandonment_loop.start()

    def cog_unload(self):
        self.chaos_loop.cancel()
        self.abandonment_loop.cancel()

    # --- Passive message listeners ---

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.content:
            return

        # Passive aggressive reactions (1%)
        if random.random() < 0.01:
            chain = random.choice(SUS_EMOJI_CHAINS)
            try:
                for emoji in chain:
                    await message.add_reaction(emoji)
                    await asyncio.sleep(random.uniform(0.5, 1.5))
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass

        # Context crimes - "that's what she said" (0.5%)
        if random.random() < 0.005:
            lower = message.content.lower()
            for trigger in THATS_WHAT_SHE_SAID_TRIGGERS:
                if trigger in lower:
                    await asyncio.sleep(random.uniform(1, 3))
                    try:
                        await message.reply(random.choice(SAFE_CONTEXT_CRIMES), mention_author=False)
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                    break

    # --- Scheduled chaos loop ---

    @tasks.loop(hours=12)
    async def chaos_loop(self):
        guilds = [g for g in self.bot.guilds if g.text_channels]
        if not guilds:
            return

        for guild in guilds:
            # Wrong Channel
            if self._check_and_reset("wrong_channel"):
                channel = self._random_channel(guild)
                if channel:
                    try:
                        await channel.send(random.choice(WRONG_CHANNEL_MESSAGES))
                        logger.info(f"Chaos: wrong_channel in #{channel.name}")
                    except (discord.Forbidden, discord.HTTPException):
                        pass

            # Existential Crisis
            if self._check_and_reset("existential"):
                channel = self._random_channel(guild, prefer_active=True)
                if channel:
                    try:
                        await channel.send(random.choice(CRISIS_OPENINGS))
                        await asyncio.sleep(random.uniform(3, 8))
                        await channel.send(random.choice(CRISIS_MIDDLES))
                        await asyncio.sleep(random.uniform(5, 15))
                        await channel.send(random.choice(CRISIS_CLOSINGS))
                        logger.info(f"Chaos: existential in #{channel.name}")
                    except (discord.Forbidden, discord.HTTPException):
                        pass

            # Relationship Status
            if self._check_and_reset("relationship"):
                channel = self._random_channel(guild, prefer_active=True)
                if channel:
                    try:
                        await channel.send(random.choice(RELATIONSHIP_UPDATES))
                        logger.info(f"Chaos: relationship in #{channel.name}")
                    except (discord.Forbidden, discord.HTTPException):
                        pass

            # Fake Maintenance
            if self._check_and_reset("maintenance"):
                channel = self._random_channel(guild, prefer_active=True)
                if channel:
                    try:
                        await channel.send(random.choice(MAINTENANCE_WARNINGS))
                        await asyncio.sleep(random.uniform(20, 45))
                        await channel.send(random.choice(MAINTENANCE_JKMSGS))
                        logger.info(f"Chaos: fake maintenance in #{channel.name}")
                    except (discord.Forbidden, discord.HTTPException):
                        pass

            # Vague Threat
            if self._check_and_reset("vague_threat"):
                channel = self._random_channel(guild)
                if channel:
                    try:
                        await channel.send(random.choice(OMINOUS_MESSAGES))
                        logger.info(f"Chaos: vague threat in #{channel.name}")
                    except (discord.Forbidden, discord.HTTPException):
                        pass

    @chaos_loop.before_loop
    async def before_chaos_loop(self):
        await self.bot.wait_until_ready()

    # --- Abandonment check (runs more frequently to catch quiet periods) ---

    @tasks.loop(hours=2)
    async def abandonment_loop(self):
        guilds = [g for g in self.bot.guilds if g.text_channels]
        if not guilds:
            return

        # Only trigger ~25% of the time when conditions are met
        if random.random() > 0.25:
            return

        for guild in guilds:
            # Check active hours (rough estimate: 10am-2am UTC is "active")
            now = datetime.now(timezone.utc)
            if now.hour < 10 or now.hour > 23:
                continue

            channels = [
                ch for ch in guild.text_channels
                if ch.permissions_for(guild.me).send_messages
                and ch.permissions_for(guild.me).read_message_history
            ]
            priority = [ch for ch in channels if any(n in ch.name.lower() for n in ["test", "admin"])]
            preferred = [ch for ch in channels if any(n in ch.name.lower() for n in ["general", "chat", "main", "lounge"])]
            check_channels = priority if priority else (preferred if preferred else channels[:3])

            for channel in check_channels:
                try:
                    cutoff = now - timedelta(hours=ABANDONMENT_QUIET_HOURS)
                    has_recent = False
                    async for msg in channel.history(limit=1, after=cutoff):
                        has_recent = True
                        break

                    if not has_recent:
                        await channel.send(random.choice(LONELY_MESSAGES))
                        logger.info(f"Chaos: abandonment in #{channel.name}")
                        return  # Only one per check
                except (discord.Forbidden, discord.HTTPException):
                    continue

    @abandonment_loop.before_loop
    async def before_abandonment_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Chaos(bot))
