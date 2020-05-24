import discord
from discord.ext import commands
from config import dbtype, dbfile
import sqlite3
from sqlite3 import Error
import sqlalchemy

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
    async def quote(self, ctx, subcommand: str = "get", quote: str = None):
        """ commands to add and retrieve quotes to/from the db"""
        if subcommand.lower() == 'add':
            if len(quote.strip()) > 0:
                dbconn = sqlite3.connect(dbfile)
                cur = dbconn.cursor()
                cur.execute("INSERT INTO quotes VALUES (?)", [quote])
                rowid = cur.lastrowid
                dbconn.commit()
                await ctx.send(":microphone: " + "[" + str(rowid) + "] " + quote + " added to database")
                dbconn.close()

        if subcommand.lower() == "get":
            # assume user wants a random quote back
            dbconn = sqlite3.connect(dbfile)
            cur = dbconn.cursor()
            randquote = cur.execute("SELECT * FROM quotes ORDER BY RANDOM() LIMIT 1;")
            randquote = randquote.fetchall()[0][0]
            await ctx.send(randquote)
            dbconn.close()


def setup(bot):
    bot.add_cog(Quotes(bot))
