import discord
from discord.ext import commands
from discord import app_commands
from config import dbtype, dbfile
import sqlite3
from sqlite3 import Error
import logging

logger = logging.getLogger(__name__)


class Quotes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        if dbtype == 'sqlite':
            dbconn = None
            try:
                dbconn = sqlite3.connect(dbfile)
                logger.debug("SQLite version: %s", sqlite3.version)
                c = dbconn.cursor()
                c.execute(''' CREATE TABLE IF NOT EXISTS quotes (quote text)''')
                dbconn.commit()
                c.close()
            except Error as e:
                logger.error("Database error: %s", e)
            finally:
                if dbconn:
                    logger.info("Connected to %s using database %s", dbtype, dbfile)
                    dbconn.close()
        logger.info("Quotes module has been loaded")

    def _add_quote(self, quote: str) -> tuple[bool, str]:
        """Add a quote to the database. Returns (success, message)."""
        if not quote or len(quote.strip()) == 0:
            return False, ":interrobang: Quote cannot be empty!"
        if len(quote) > 2000:
            return False, ":interrobang: Quote is too long! Maximum 2000 characters."
        try:
            with sqlite3.connect(dbfile) as dbconn:
                cur = dbconn.cursor()
                cur.execute("INSERT INTO quotes VALUES (?)", [quote])
                rowid = cur.lastrowid
                dbconn.commit()
                return True, ":microphone: [" + str(rowid) + "] " + quote + " added to database"
        except sqlite3.Error as e:
            logger.error("Database error: %s", e)
            return False, "Error adding quote to database."

    def _get_quote(self, quote_id: int = None) -> tuple[bool, str]:
        """Get a quote from the database. Returns (success, message)."""
        try:
            with sqlite3.connect(dbfile) as dbconn:
                cur = dbconn.cursor()
                if quote_id:
                    randquote = cur.execute("SELECT * FROM quotes WHERE rowid = ?;", [quote_id])
                    result = randquote.fetchall()
                    if not result:
                        return False, f"No quote found with ID {quote_id}"
                    return True, "[" + str(quote_id) + "] " + result[0][0]
                else:
                    randquote = cur.execute("SELECT * FROM quotes ORDER BY RANDOM() LIMIT 1;")
                    result = randquote.fetchall()
                    if not result:
                        return False, "No quotes in database yet!"
                    quote_text = result[0][0]
                    rowid = cur.execute("SELECT rowid FROM quotes WHERE quote like (?)", [quote_text])
                    qid = rowid.fetchall()[0][0]
                    return True, "[" + str(qid) + "] " + quote_text
        except sqlite3.Error as e:
            logger.error("Database error: %s", e)
            return False, "Error retrieving quote from database."
        except IndexError:
            return False, "No quotes in database yet!"
        except Exception as e:
            logger.error("Unexpected error: %s", e)
            return False, "An error occurred."

    @commands.command(aliases=['Quote'])
    async def quote(self, ctx, subcommand: str = "get", *, quote: str = None):
        """ commands to add and retrieve quotes to/from the db"""
        if subcommand.lower() == 'add':
            if not quote:
                await ctx.send(":interrobang: You need to give me a quote to add!")
                return
            _, msg = self._add_quote(quote)
            await ctx.send(msg)
        elif subcommand.lower() == "get":
            try:
                quote_id = int(quote) if quote else None
            except ValueError:
                await ctx.send("Invalid quote ID. Please provide a number or leave empty for random.")
                return
            _, msg = self._get_quote(quote_id)
            await ctx.send(msg)

    @app_commands.command(name="quote_add", description="Add a quote to the database")
    @app_commands.describe(quote="The quote to add")
    async def quote_add_slash(self, interaction: discord.Interaction, quote: str):
        _, msg = self._add_quote(quote)
        await interaction.response.send_message(msg)

    @app_commands.command(name="quote", description="Get a quote from the database")
    @app_commands.describe(quote_id="Specific quote ID (leave empty for random)")
    async def quote_get_slash(self, interaction: discord.Interaction, quote_id: int = None):
        _, msg = self._get_quote(quote_id)
        await interaction.response.send_message(msg)


async def setup(bot):
    await bot.add_cog(Quotes(bot))
