import os
import discord
from discord.ext import commands
from sqlalchemy import create_engine, Column, Integer, String, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, exc
import logging
from datetime import datetime

Base = declarative_base()

class Quote(Base):
    __tablename__ = 'quotes'
    id = Column(Integer, primary_key=True)
    user_id = Column(String)
    submitted_by_user_id = Column(String)
    quote = Column(String)
    date = Column(DateTime, default=datetime.utcnow)
    guild_id = Column(String)

class Quotes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        db_url = os.getenv('DATABASE_URL', 'sqlite:///data/blbot.db')
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.check_role = bot.get_cog('BasicCommands')  # Assuming this is a separate cog with role-checking logic

    async def add_quote(self, ctx, quote_text):
        if not ctx.message.mentions:
            self.logger.debug("No mentioned users found.")
            await ctx.send("You must mention a user when adding a quote.")
            return

        highlighted_user = ctx.message.mentions[0]
        self.logger.debug(f"Adding quote for user: {highlighted_user.name} ({highlighted_user.id})")

        try:
            session = self.Session()
            quote = Quote(user_id=str(highlighted_user.id),
                          submitted_by_user_id=str(ctx.author.id),
                          quote=quote_text,
                          guild_id=str(ctx.guild.id))
            session.add(quote)
            session.commit()

            await ctx.send(f"Thanks {ctx.author.mention}. I have added the quote, its ID is {quote.id}")
        except exc.SQLAlchemyError as e:
            self.logger.error(f"An error occurred while adding a quote: {e}")
            await ctx.send("An error occurred while adding the quote.")
        finally:
            session.close()

    async def search_quote_by_user(self, ctx):
        if not ctx.message.mentions:
            await ctx.send("Please mention a user to search for their quotes.")
            return

        mentioned_user = ctx.message.mentions[0]
        try:
            session = self.Session()
            quotes = session.query(Quote).filter_by(user_id=str(mentioned_user.id)).all()
            session.close()
            if quotes:
                message = "Found quotes:\n"
                for quote in quotes:
                    message += f"ID: {quote.id} - {quote.quote}\n"
                await ctx.send(message[:2000])  # Discord message length limit
            else:
                await ctx.send("No quotes found for the mentioned user.")
        except exc.SQLAlchemyError as e:
            self.logger.error(f"An error occurred while searching for quotes by user: {e}")
            await ctx.send("An error occurred while searching for quotes by user.")

    async def get_random_quote(self, ctx):
        try:
            session = self.Session()
            random_quote = session.query(Quote).order_by(func.random()).first()
            session.close()
            if random_quote:
                await ctx.send(f"Random quote: {random_quote.quote}\nSubmitted by <@{random_quote.submitted_by_user_id}> on {random_quote.date}")
            else:
                await ctx.send("There are currently no quotes available.")
        except exc.SQLAlchemyError as e:
            self.logger.error(f"An error occurred while retrieving a random quote: {e}")
            await ctx.send("An error occurred while trying to retrieve a random quote.")

    @commands.command()
    async def quote(self, ctx, sub_command=None, *args):
        if sub_command == 'help':
            await ctx.send("Usage of !quote command:\n"
                           "- `!quote add <quote>` to add a quote mentioning a user.\n"
                           "- `!quote <ID>` to retrieve a specific quote.\n"
                           "- `!quote count` to get the total number of quotes.\n"
                           "- `!quote search @UserName` to search quotes by a mentioned user.")
        elif sub_command == 'add':
            await self.add_quote(ctx, ' '.join(args))
        elif sub_command == 'count':
            try:
                session = self.Session()
                quote_count = session.query(Quote).count()
                session.close()
                await ctx.send(f"Total quotes submitted: {quote_count}")
            except exc.SQLAlchemyError as e:
                self.logger.error(f"An error occurred while getting quote count: {e}")
                await ctx.send("An error occurred while getting quote count.")
        elif sub_command == 'search':
            await self.search_quote_by_user(ctx)
        elif sub_command and sub_command.isdigit():
            quote_id = int(sub_command)
            try:
                session = self.Session()
                quote = session.query(Quote).filter_by(id=quote_id).first()
                session.close()
                if quote:
                    await ctx.send(f"{quote.quote}\nSubmitted by <@{quote.submitted_by_user_id}> on {quote.date}")
                else:
                    await ctx.send("Quote not found.")
            except exc.SQLAlchemyError as e:
                self.logger.error(f"An error occurred while retrieving quote: {e}")
                await ctx.send("An error occurred while retrieving quote.")
        else:
            await self.get_random_quote(ctx)

def setup(bot):
    bot.add_cog(Quotes(bot))

