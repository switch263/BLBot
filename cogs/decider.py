import discord
from discord.ext import commands
import random
import re
import logging

logger = logging.getLogger(__name__)

class Decider(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.should_options = ["Yes", "No", "Maybe"]


    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Decider module has been loaded")

    #
    # Pick Command
    #

    @commands.command(aliases=['choose'])
    async def pick(self, ctx, *, text: str):
        """Picks between multiple options or parses a 'should' question."""
        logging.debug(f"Received pick command: '{text}'")

        # Remove 'my'
        text = text.replace('my', 'your')

        # Normalize the text for easier handling
        normalized_text = text.lower().strip()

        # Check if the message starts with 'should'
        if normalized_text.startswith('should'):
            # Extract the question part after 'should'
            question = text[len('should'):].strip('? ')

            # Adjust the question in case it starts with 'I'
            if normalized_text.startswith('should i'):
                question = question.lstrip(' iI').strip()  # Remove 'I' with space

            decision = random.choice(self.should_options)  # Select a random decision

            # Special handling for the "No" decision
            if decision == "No" and random.choice([True, False]):
                decision = "No, I don't think"  # Modify the decision text for a 50% chance

            # Special handling for @everyone and @here mentions
            if '@everyone' in normalized_text or '@here' in normalized_text:
                response = f"{ctx.author.mention}, {decision}, everyone should {question.replace('@everyone', '').replace('@here', '').strip()}."
            else:
                # Extract mentioned users and roles
                mentioned_users = ctx.message.mentions
                mentioned_roles = ctx.message.role_mentions

                # Check if the bot user is mentioned
                bot_mentioned = self.bot.user in mentioned_users

                # Construct response based on mentioned entities
                mentions_str = " ".join(user.mention for user in mentioned_users) + " " + " ".join(role.mention for role in mentioned_roles)
                mentions_str = mentions_str.strip()
                question_without_mention = question.split(' ', 1)[1] if len(question.split(' ', 1)) > 1 else question

                # Apply the decision to the response
                if bot_mentioned:
                    response = "Ha! I'll do whatever I like."
                elif decision.startswith("No, I don't think"):
                    response = f"{ctx.author.mention}, {decision} {mentions_str} should {question_without_mention}."
                else:
                    response = f"{ctx.author.mention}, {decision}, {mentions_str} should {question_without_mention}."

            await ctx.send(response)
        else:
            # Use regular expression to split choices by comma, but only if not within quotes
            choices = re.findall(r'"([^"]+)"|([^,]+)', text)
            # Flatten the list of tuples and strip whitespace from each choice
            choices = [choice.strip() for group in choices for choice in group if choice.strip()]
            logging.debug(f"Choices: {choices}")

            # If there's only one choice, return a random "Yes", "No", or "Maybe"
            if len(choices) == 1:
                decision = random.choice(["Yes", "No", "Maybe"])
            else:
                # Pick a random choice from the list
                decision = random.choice(choices)

            await ctx.send(decision)

    #
    # Eightball Command
    #
    @commands.command(aliases=['8ball', '8b'])
    async def eightball(self, ctx):
        """ Return an 8-ball response."""
        answers = [
            "Ask Again Later",
            "Better Not Tell You Now",
            "Concentrate and Ask Again",
            "Don't Count on It",
            "It Is Certain",
            "Most Likely",
            "My Reply is No",
            "My Sources Say No",
            "No",
            "Outlook Good",
            "Outlook Not So Good",
            "Reply Hazy, Try Again",
            "Signs Point to Yes",
            "Yes",
            "Yes, Definitely",
            "You May Rely On It",
        ]
        await ctx.send(":8ball:" + random.choice(answers))



def setup(bot):
    bot.add_cog(Decider(bot))


