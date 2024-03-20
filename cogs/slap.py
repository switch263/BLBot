import discord
import random
import logging
from discord.ext import commands

logger = logging.getLogger(__name__)

class Slap(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ignored_users = ["kev2tall"]
        self.stats = bot.get_cog('Stats')

    async def slap_target(self, ctx, slapper, target):
        slap_message = f"{slapper.mention} slaps {target.mention} with a {self.get_random_slap_item()}!"
        await ctx.send(slap_message)

    def get_random_slap_item(self):
        slap_items = [
            "a penguin egg", "a dinosaur fossil", "a bag of potato crisps", "a bottle of water", "a rubber chicken",
            "a slice of pizza", "a feather boa", "a giant inflatable banana", "a squeaky toy", "a foam finger",
            "a fish", "a bouquet of flowers", "a stuffed unicorn", "a roll of duct tape", "a pineapple", "a rubber duck",
            "a plush toy", "a handful of confetti", "a foam sword", "a jello mold", "a rubber band ball", "a bag of cotton balls",
            "a rubber snake", "a jar of pickles", "a bag of gummy worms", "a rubber tire", "a bunch of balloons", "a feather duster",
            "a sponge", "a coconut", "a giant lollipop", "a slinky", "a whoopee cushion", "a beach ball", "a watermelon",
            "a marshmallow", "a bag of marbles", "a foam brick", "a rubber lobster", "a bag of rubber bands", "a toy lightsaber",
            "a rubber chicken", "a jar of jelly beans", "a loaf of bread", "a rubber mallet", "a bag of marshmallows",
            "a plush octopus", "a pool noodle", "a rubber fish", "a bag of googly eyes", "a bag of feathers", "a toy robot",
            "a rubber hammer", "a can of whipped cream", "a bag of glitter", "a rubber pig", "a fake spider", "a roll of toilet paper",
            "a bag of plastic spiders", "a toy rubber hammer", "a bag of rubber worms", "a rubber ball", "a bag of foam balls",
            "a toy rubber snake", "a bag of rubber ducks", "a rubber glove", "a bag of plastic flies", "a toy rubber fish",
            "a bag of plastic eyeballs", "a rubber banana", "a bag of rubber frogs", "a toy rubber duck", "a bag of rubber chickens",
            "a rubber horse", "a bag of rubber spiders", "a toy rubber spider", "a bag of rubber bats", "a rubber rat",
            "a bag of rubber rats", "a toy rubber rat", "a bag of rubber horses", "a rubber cow", "a bag of rubber cows",
            "a toy rubber cow", "a bag of rubber pigs", "a rubber cat", "a bag of rubber cats", "a toy rubber cat",
            "a bag of rubber dogs", "a rubber dog", "a toy rubber dog", "a bag of rubber birds", "a rubber bird",
            "a toy rubber bird", "a bag of rubber fish", "a rubber fish", "a toy rubber fish",
            "a computer mouse", "a keyboard", "a monitor", "a USB flash drive", "a computer mouse pad", "a headset", "a printer",
            "a webcam", "a microphone", "a graphics tablet", "a laptop bag", "a computer speaker", "a router", "a modem",
            "a computer case", "a laptop stand", "a mouse bungee", "a mouse pad with wrist rest", "a surge protector", "a UPS",
            "a external hard drive", "a SSD", "a HDD", "a CD/DVD drive", "a stylus", "a USB hub", "a network switch", "a joystick",
            "a gamepad", "a trackball", "a barcode scanner", "a touch screen monitor", "a VR headset", "a wireless presenter",
            "a wireless mouse", "a wireless keyboard", "a USB fan", "a USB LED light", "a USB cup warmer", "a USB mini fridge"
        ]

        return random.choice(slap_items)

    def get_valid_target(self, ctx):
        channel_members = [member for member in ctx.channel.members if member.display_name.lower() not in self.ignored_users]
        return random.choice(channel_members)

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Slap module has been loaded")
        try:
            if self.stats:
                self.stats.register_cog("slap", ["actor", "target"])
                logger.info("Registering slap with stats")
            else:
                logger.warning("Stats cog not found.")
        except Exception as e:
            logger.error(f"Error registering submodule with stats: {e}")


    @commands.command(name='slap', help='Slap someone in the channel. If no one is mentioned, a random person is slapped.')
    async def slap(self, ctx, target: discord.Member = None):
        slapper = ctx.author

        if target == self.bot.user:
            if self.stats:
                try:
                    await self.stats.update_stats("slap", userid=str(ctx.author.id), actor=1, target=1)
                    await self.stats.update_stats("slap", userid=str(self.bot.user.id), actor=1)
                except:
                    logger.debug("ERROR: Updating slap stats")
            await ctx.send(f"You think you can slap me {slapper.mention}? I don't think so. How about I slap you {slapper.mention}!\n_{self.bot.user.mention} slaps {slapper.mention} with a {self.get_random_slap_item()}_!")
            return

        if target == slapper:
            if self.stats:
                try:
                    await self.stats.update_stats("slap", userid=str(ctx.author.id), actor=1, target=1)
                    logger.debug("Updating slap stats")
                except:
                    logger.debug("ERROR: Updating slap stats")
            await ctx.send(f"Ha! Quit slapping yourself around {slapper.mention}")
            return

        if target is None:
            target = self.get_valid_target(ctx)

        if target.display_name.lower() in self.ignored_users:
            target = slapper

        if self.stats:
            try:
                await self.stats.update_stats("slap", userid=str(ctx.author.id), actor=1)
                await self.stats.update_stats("slap", userid=str(target.id), target=1)
                logger.debug("Updating slap stats")
            except:
                logger.debug("ERROR: Updating slap stats")
        
        await self.slap_target(ctx, slapper, target)

        logger.info(f"{slapper.display_name} slapped {target.display_name}")

def setup(bot):
    bot.add_cog(Slap(bot))

