import discord
from discord.ext import commands
from config import dbtype, dbfile
import sqlite3
from sqlite3 import Error


class Quotes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        if dbtype == 'sqlite':
            dbconn = None
            try:
                dbconn = sqlite3.connect(dbfile)
                print(sqlite3.version)
                c = dbconn.cursor()
                c.execute(''' CREATE TABLE quotes (quote text)''')
                dbconn.commit()
                c.close()
            except Error as e:
                print(e)
            finally:
                if dbconn:
                    print("Connected to {} using database {}".format(dbtype, dbfile))
                    dbconn.close()
        print("Quotes module has been loaded\n-----")

    @commands.command(aliases=['Quote'])
    async def quote(self, ctx, subcommand: str = "get", *, quote: str = None):
        """ commands to add and retrieve quotes to/from the db"""
        if subcommand.lower() == 'add':
            if not quote:
                await ctx.send(":interrobang: You need to give me a quote to add!")
                return

            # Security: Validate input length
            if len(quote.strip()) == 0:
                await ctx.send(":interrobang: Quote cannot be empty!")
                return
                
            if len(quote) > 2000:
                await ctx.send(":interrobang: Quote is too long! Maximum 2000 characters.")
                return

            # Security: Use context manager to ensure connection is closed
            try:
                with sqlite3.connect(dbfile) as dbconn:
                    cur = dbconn.cursor()
                    cur.execute("INSERT INTO quotes VALUES (?)", [quote])
                    rowid = cur.lastrowid
                    dbconn.commit()
                    await ctx.send(":microphone: " + "[" + str(rowid) + "] " + quote + " added to database")
            except sqlite3.Error as e:
                await ctx.send("Error adding quote to database.")
                print(f"Database error: {e}")

        elif subcommand.lower() == "get":
            try:
                quote_id = int(quote) if quote else None
                
                with sqlite3.connect(dbfile) as dbconn:
                    cur = dbconn.cursor()
                    
                    if quote_id:
                        # user wants a specific quote ID
                        randquote = cur.execute("SELECT * FROM quotes WHERE rowid = ?;", [quote_id])
                        result = randquote.fetchall()
                        if not result:
                            await ctx.send(f"No quote found with ID {quote_id}")
                            return
                        randquote = result[0][0]
                        id = quote_id
                    else:
                        # user wants a random quote
                        randquote = cur.execute("SELECT * FROM quotes ORDER BY RANDOM() LIMIT 1;")
                        result = randquote.fetchall()
                        if not result:
                            await ctx.send("No quotes in database yet!")
                            return
                        randquote = result[0][0]
                        rowid = cur.execute("SELECT rowid FROM quotes WHERE quote like (?)", [randquote])
                        id = rowid.fetchall()[0][0]
                    
                    await ctx.send("[" + str(id) + "] " + randquote)
                    
            except ValueError:
                await ctx.send("Invalid quote ID. Please provide a number or leave empty for random.")
            except sqlite3.Error as e:
                await ctx.send("Error retrieving quote from database.")
                print(f"Database error: {e}")
            except IndexError:
                await ctx.send("No quotes in database yet!")
            except Exception as e:
                await ctx.send("An error occurred.")
                print(f"Unexpected error: {e}")


async def setup(bot):
    await bot.add_cog(Quotes(bot))
