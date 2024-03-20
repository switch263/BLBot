# stats
import json
import os
import logging
import discord
from discord.ext import commands
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, DateTime, ARRAY, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.inspection import inspect
from sqlalchemy.exc import NoSuchTableError
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    userid = Column(String, unique=True)
    guildid = Column(String)
    user_display_name = Column(ARRAY(String))
    member_join = Column(DateTime)
    member_seen = Column(DateTime, nullable=True)

class StatsRegistered(Base):
    __tablename__ = 'stats_registered'

    id = Column(Integer, primary_key=True)
    cog = Column(String, unique=True)
    enabled = Column(Boolean)
    columns_json = Column(Text)

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        db_url = os.getenv("DATABASE_URL", "sqlite:///data/blbot.db")  # Fixed typo here, added '///' before 'data'
        engine = create_engine(db_url, echo=False)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("Stats module has been loaded\n-----")
        await self.seed_users()

    def register_cog(self, module, columns):
        try:
            # Check if columns is a list
            if not isinstance(columns, list):
                raise ValueError("Columns must be provided in a list format.")

            # Convert the list of columns to a JSON string
            columns_json = json.dumps(columns)

            session = self.Session()

            # Insert the cog into the 'stats_registered' table with columns_json
            registered_cog = session.query(StatsRegistered).filter_by(cog=module).first()
            if registered_cog:
                registered_cog.enabled = True
                registered_cog.columns_json = columns_json
            else:
                registered_cog = StatsRegistered(cog=module, enabled=True, columns_json=columns_json)
                session.add(registered_cog)

            # Create the table for the cog with the provided columns
            stats_table_name = f'stats_{module}'
            inspector = inspect(session.bind)
            if not inspector.has_table(stats_table_name):
                create_table_sql = f'''CREATE TABLE {stats_table_name} (
                        id SERIAL PRIMARY KEY,
                        userid TEXT,
                        {', '.join([f"{col} INTEGER DEFAULT 1" for col in columns])}
                        )'''
                session.execute(text(create_table_sql))
                session.commit()
                logging.info(f"{stats_table_name} created successfully.")
            else:
                logging.info(f"{stats_table_name} already exists.")

            logging.info(f"{module} registered successfully.")
        except ValueError as ve:
            logging.error(f"ValueError: {ve}")
        except Exception as ex:
            logging.error(f"An unexpected error occurred: {ex}")
        finally:
            session.close()

    async def update_stats(self, module, **kwargs):
        try:
            # Retrieve cog info
            session = self.Session()
            registered_cog = session.query(StatsRegistered).filter_by(cog=module).first()
            if not registered_cog:
                logging.error(f"No cog information found for module: {module}")
                return  # Module not registered, handle this case as needed

            user_id = kwargs.pop('userid', None)

            if user_id is None:
                logging.error("User ID not provided")
                return  # User ID not provided, handle this case as needed

            logging.debug(f"Cog info: {registered_cog}")

            # Extract column names from cog_info
            columns = json.loads(registered_cog.columns_json)
            logging.debug(f"Parsed Columns: {columns}")

            # Check if the user already has stats recorded
            stats_table_name = f'stats_{module}'
            inspector = inspect(session.bind)
            if not inspector.has_table(stats_table_name):
                logging.error(f"No stats table found for module: {module}")
                return  # Stats table not found, handle this case as needed

            user_stats = session.execute(text(f"SELECT * FROM {stats_table_name} WHERE userid = :userid"), {"userid": user_id}).fetchone()

            if user_stats is None:
                # If user has no stats recorded, create a new entry
                placeholders = ', '.join([':' + col for col in columns if col != 'id'])  # Exclude 'id' column
                insert_query = f"INSERT INTO {stats_table_name} (userid, {', '.join(columns)}) VALUES (:userid, {placeholders})"
                values = {'userid': user_id}
                for col in columns:
                    if col != 'id':
                        values[col] = 0
                session.execute(text(insert_query), values)
                session.commit()
            else:
                # Update the stats based on the kwargs
                update_values = ', '.join([f"{column} = {column} + :{column}" for column in kwargs.keys() if column in columns])
                update_query = f"UPDATE {stats_table_name} SET {update_values} WHERE userid = :userid"
                session.execute(text(update_query), {**kwargs, "userid": user_id})
                session.commit()
        except Exception as ex:
            logging.error(f"An unexpected error occurred: {ex}")
        finally:
            session.close()
    #######
    @commands.command()
    async def top10(self, ctx, module=None, column=None):
        if not module:
            module = 'user'
            column = 'messages'

        try:
            session = self.Session()
            stats_table_name = f'stats_{module}'

            if not self.is_module_enabled(module):
                await ctx.send(f"{module} module is not enabled.")
                return

            if not column:
                registered_cog = session.query(StatsRegistered).filter_by(cog=module).first()
                if registered_cog:
                    data_json = registered_cog.columns_json
                    await ctx.send(f"No column specified. You can try !top10 {module} {data_json}.")
                else:
                    await ctx.send(f"No column specified. You can try !top10 {module}.")
                return

            if not self.is_valid_column(module, column):
                await ctx.send(f"{column} is not a valid column for module {module}.")
                return

            # Fetch top 10 stats sorted by the specified column
            query = f"SELECT userid, {column} FROM {stats_table_name} ORDER BY {column} DESC LIMIT 10"
            result = session.execute(text(query)).fetchall()

            if result:
                output = f"Top 10 stats for {module} sorted by {column}:\n"
                for index, row in enumerate(result, start=1):
                    user = ctx.guild.get_member(int(row[0]))
                    if user:
                        output += f"{index}. {user.mention}, {column}: {row[1]}\n"
                    else:
                        output += f"{index}. *User left server*, {column}: {row[1]}\n"
                await ctx.send(output)
            else:
                await ctx.send("No stats found.")

        except NoSuchTableError:
            await ctx.send(f"No stats found for module {module}.")
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")
        finally:
            session.close()

    def is_module_enabled(self, module):
        session = self.Session()
        registered_cog = session.query(StatsRegistered).filter_by(cog=module).first()
        session.close()
        return registered_cog.enabled if registered_cog else False

    def is_valid_column(self, module, column):
        session = self.Session()
        registered_cog = session.query(StatsRegistered).filter_by(cog=module).first()
        session.close()
        if registered_cog:
            valid_columns = json.loads(registered_cog.columns_json)
            return column in valid_columns
        return False

    #####################
    async def seed_users(self):
        try:
            for guild in self.bot.guilds:
                for member in guild.members:
                    self.add_or_update_user(member)
            logging.info("User seeding completed successfully.")
        except Exception as ex:
            logging.error(f"An unexpected error occurred during user seeding: {ex}")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        try:
            self.add_or_update_user(member)
            logging.info("New user added successfully.")
        except Exception as ex:
            logging.error(f"An unexpected error occurred when adding a new user: {ex}")

    def add_or_update_user(self, member):
        try:
            session = self.Session()
            user_entry = session.query(User).filter_by(userid=str(member.id)).first()
            if user_entry:
                # Check if member.display_name is in user_display_name array
                if member.display_name not in user_entry.user_display_name:
                    user_entry.user_display_name.append(member.display_name)
            else:
                # Insert new user with member_seen set to None
                new_user = User(
                    userid=str(member.id),
                    guildid=str(member.guild.id),
                    user_display_name=[member.display_name],
                    member_join=member.joined_at,
                    member_seen=None
                )
                session.add(new_user)
            session.commit()
        except Exception as ex:
            logging.error(f"An unexpected error occurred when adding a new user: {ex}")
        finally:
            session.close()

    def update_member_seen(self, userid):
        try:
            session = self.Session()
            user_entry = session.query(User).filter_by(userid=str(userid)).first()

            if user_entry:
                user_entry.member_seen = datetime.utcnow()
                session.commit()
                logging.info(f"Member seen updated for user_id: {userid}")
            else:
                logging.error(f"User with user_id {userid} not found.")
        except Exception as ex:
            logging.error(f"An unexpected error occurred while updating member_seen: {ex}")
            session.rollback()  # Rollback changes in case of error
        finally:
            if session:
                session.close()

    def update_display_name(self, userid, new_name):
        try:
            session = self.Session()
            user_entry = session.query(User).filter_by(userid=str(userid)).first()

            if user_entry:
                if new_name not in user_entry.user_display_name:
                    user_entry.user_display_name.append(new_name)
                    session.commit()
                    logging.info(f"Display name updated for user_id: {userid}")
                else:
                    logging.info(f"Display name already exists for user_id: {userid}")
            else:
                logging.error(f"User with user_id {userid} not found.")
        except Exception as ex:
            logging.error(f"An unexpected error occurred while updating display name: {ex}")
            session.rollback()  # Rollback changes in case of error
        finally:
            if session:
                session.close()                
    ##############################

def setup(bot):
    bot.add_cog(Stats(bot))

