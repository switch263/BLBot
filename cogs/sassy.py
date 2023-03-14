import random
from discord.ext import commands

class SassyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.message_count = 0
        self.mock_interval = random.randint(42069, 69420)
        self.sassy_replies = [
            'Oh please, you think you\'re so clever, $name.',
            '$name, you\'re just the wittiest, aren\'t you?',
            'Wow $name, you really outdid yourself this time. Not.',
            'I see $name is trying their best to be funny again...',
            'You\'re so hilarious, $name. Except not really.',
            '$name, you must be the life of the party. If the party was really, really lame.',
            'A for effort, $name. Too bad it\'s a participation trophy.',
            'I\'ve heard better jokes from a broken speaker, $name.',
            'Oh, $name. You just never cease to amaze... with your lack of wit.',
            'I think $name needs to take a class in comedic timing. Or just give up.',
            'At least $name tried. Too bad it wasn\'t very hard.',
            '$name, that joke was about as funny as a root canal.',
            'If laughter is the best medicine, $name should be in a coma.',
            'You know what they say, $name. If at first you don\'t succeed, stop trying.',
            '$name, did you hear the one about the person who wasn\'t funny? Oh wait, that\'s you.',
            'I bet $name thinks they\'re hilarious. Too bad nobody else does.',
            '$name, maybe you should stick to your day job. Assuming you have one.',
            'You\'re a real comedian, $name. Except not really.',
            '$name, your joke was so bad, it deserves its own Netflix special.',
            'I have to hand it to you, $name. I\'ve never heard a joke fall so flat before.',
            'I\'d tell $name to quit while they\'re ahead, but they were never ahead to begin with.',
            'You should take that joke on the road, $name. Just don\'t expect anyone to follow you.',
            '$name, I don\'t know what\'s worse - your joke or your delivery.',
            'I\'ve heard better material from a broken elevator, $name.',
            'You\'re a real hoot, $name. If hoots were completely unfunny.',
            '$name, I didn\'t know they allowed dad jokes on this server.',
            'I didn\'t realize we were in the presence of such a comedic genius, $name.',
            '$name, you might want to consider taking up mime instead.',
            'You should write that one down, $name. So you can make sure to never tell it again.',
            'I think $name might need to attend a humor intervention.',
            'I thought $name\'s joke was bad, but then I realized it wasn\'t even a joke.',
            '$name, I\'m pretty sure the punchline was supposed to be funny. Oops.',
            'You must be the funniest person in your own head, $name.',
            '$name, if that joke were any worse, it would have been a meme.',
            'I can see $name has a future in stand-up comedy. As the person who laughs at their own jokes.',
            'You\'re the life of the party, $name. The party being a funeral.',
            '$name, that joke was so bad, it made me want to claw my own eyes out.',
            'I\'ve seen funnier things at a funeral, $name.',
            '$name, I\'m pretty sure a tumbleweed just rolled...through the chat after that joke.',
            'I hope $name doesn\'t quit their day job. Unless their day job is telling jokes.',
            '$name, I think it\'s time to retire the joke-telling for good.',
            'I didn\'t realize we had a comedian in our midst, $name. Oh wait, we don\'t.',
            'That joke was so bad, it made me question the existence of comedy altogether, $name.',
            '$name, you should try writing for a sitcom. Assuming they don\'t want to be funny.',
            'I\'m not sure what\'s more painful, $name\'s joke or the fact that they thought it was funny.',
            '$name, have you ever considered a career in being painfully unfunny?',
            'I think $name just set the bar for the worst joke of the century.',
            'You\'re a real crowd-pleaser, $name. Assuming the crowd is made up of people who hate laughter.',
            '$name, I think it\'s time to hang up the comedy hat. Assuming you ever had one.',
            'I\'m pretty sure $name\'s joke just broke the world record for the least amount of laughs.',
            'You know what they say, $name. If you can\'t be funny, at least be quiet.',
            'I\'m pretty sure $name\'s joke just got its own spot in the Hall of Fame. For bad jokes, that is.']


    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: # ignore messages from bots
            return
        self.message_count += 1
        if self.message_count >= self.mock_interval: # time to mock!
            self.message_count = 0
            self.mock_interval = random.randint(42069, 69420) # randomize next interval
            sassy_reply = random.choice(self.sassy_replies) # choose a sassy reply
            sassy_reply = sassy_reply.replace('$name', message.author.name) # replace $name with user's name
            sassy_reply += ' ' + self._alternate_case(message.content) # alternate case for user's message
            await message.channel.send(sassy_reply)

    def _alternate_case(self, message):
        result = ''
        upper = True
        for letter in message:
            if letter.isalpha():
                if upper:
                    result += letter.upper()
                else:
                    result += letter.lower()
                upper = not upper
            else:
                result += letter
        return result

def setup(bot):
    bot.add_cog(SassyCog(bot))


