import json
import os
import sqlite3
import logging
import discord
from discord.ext import commands

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = os.path.join("data", "blbot.db")
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.create_registered_table()

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("Stats module has been loaded\n-----")

    def create_registered_table(self):
        try:
            # Create the 'registered' table if it doesn't exist
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS stats_registered (
                                id INTEGER PRIMARY KEY,
                                cog TEXT UNIQUE,
                                enabled INTEGER,
                                columns_json TEXT)''')
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Error creating registered table: {e}")

    @staticmethod
    def register_cog(db_path, module, columns):
        try:
            # Check if columns is a list
            if not isinstance(columns, list):
                raise ValueError("Columns must be provided in a list format.")

            # Convert the list of columns to a JSON string
            columns_json = json.dumps(columns)

            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Insert the cog into the 'registered' table with columns_json
            cursor.execute("INSERT OR REPLACE INTO stats_registered (cog, enabled, columns_json) VALUES (?, ?, ?)",
                            (module, 1, columns_json))
            conn.commit()
            logging.info(f"{module} registered successfully.")

            # Create the table for the cog with the provided columns
            cursor.execute(f'''CREATE TABLE IF NOT EXISTS stats_{module} (
                                id INTEGER PRIMARY KEY,
                                userid TEXT,
                                {', '.join([f"{col} INTEGER DEFAULT 0" for col in columns])}
                                )''')
            conn.commit()
        except sqlite3.Error as e:
            logging.error(f"SQLite error: {e}")
        except ValueError as ve:
            logging.error(f"ValueError: {ve}")
        except Exception as ex:
            logging.error(f"An unexpected error occurred: {ex}")

    @commands.command()
    async def stats(self, ctx, module=None, *, member: discord.Member = None):
        try:
            if not module:
                await ctx.send("Please specify a module.")
                return

            # Determine the user ID to retrieve stats for
            if member is None:
                user_id = str(ctx.author.id)
                user_mention = ctx.author.mention
            else:
                user_id = str(member.id)
                user_mention = member.mention

            logging.debug(f"User ID: {user_id}")

            # Check if the module is registered
            self.cursor.execute("SELECT * FROM stats_registered WHERE cog=?", (module,))
            cog_info = self.cursor.fetchone()

            if cog_info is None:
                await ctx.send(f"No stats registered for {module}.")
                return

            logging.debug(f"Cog info: {cog_info}")

            # Look up stats for the specific user
            self.cursor.execute(f"SELECT * FROM stats_{module} WHERE userid=?", (user_id,))
            user_stats = self.cursor.fetchone()

            if user_stats:
                logging.debug(f"User stats for module {module}: {user_stats}")
                columns = json.loads(cog_info[3])
                stats_message = f"{module} stats for {user_mention}:"
                for i, column in enumerate(columns):
                    stats_message += f" {column}: {user_stats[i+2]}"
                await ctx.send(stats_message)
            else:
                logging.debug(f"No stats found for user {user_id} in module {module}.")
                await ctx.send(f"No stats found for {user_mention} in {module}.")
        except sqlite3.Error as e:
            logging.error(f"Error accessing database: {e}")
            await ctx.send("An error occurred while accessing the database.")
        except Exception as ex:
            logging.error(f"An unexpected error occurred: {ex}")

    async def update_stats(self, module, **kwargs):
        try:
            # Retrieve cog info
            self.cursor.execute(f"SELECT * FROM stats_registered WHERE cog=?", (module,))
            cog_info = self.cursor.fetchone()

            if cog_info is None:
                logging.error(f"No cog information found for module: {module}")
                return  # Module not registered, handle this case as needed

            user_id = kwargs.pop('userid', None)

            if user_id is None:
                logging.error("User ID not provided")
                return  # User ID not provided, handle this case as needed

            logging.debug(f"Cog info: {cog_info}")

            # Extract column names from cog_info
            columns = json.loads(cog_info[3])
            logging.debug(f"Columns JSON: {cog_info[3]}")
            logging.debug(f"Parsed Columns: {columns}")

            # Check if the user already has stats recorded
            self.cursor.execute(f"SELECT * FROM stats_{module} WHERE userid=?", (user_id,))
            user_stats = self.cursor.fetchone()

            if user_stats is None:
                # If user has no stats recorded, create a new entry
                placeholders = ', '.join(['?'] * (len(columns) + 1))  # Increment by 1 to account for the userid
                logging.debug(f"Placeholders: {placeholders}")
                values = [user_id] + [0] * len(columns)  # Remove -1 to account for the userid
                self.cursor.execute(
                    f"INSERT INTO stats_{module} (userid, {', '.join(columns)}) VALUES ({placeholders})",
                    values)
                self.conn.commit()
                user_stats = (user_id,) + tuple(values[1:])

            # Update the stats based on the kwargs
            for key, value in kwargs.items():
                if key in columns:
                    # Increment the current value by the provided value
                    logging.debug(f"Updating {key} for user {user_id}. Old value: {user_stats[columns.index(key) + 1]}. Increment: {value}")
                    old_value = user_stats[columns.index(key) + 2]  # Adjust index to account for userid
                    updated_value = old_value + value
                    logging.debug(f"New value: {updated_value}")
                    self.cursor.execute(f"UPDATE stats_{module} SET {key}=? WHERE userid=?", (updated_value, user_id))
                    self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Error updating stats: {e}")
        except Exception as ex:
            logging.error(f"An unexpected error occurred: {ex}")

def setup(bot):
    bot.add_cog(Stats(bot))

