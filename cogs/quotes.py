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
                    print("Connected to {} using database {}".format(
                        dbtype, dbfile))
                    dbconn.close()
        print("Quotes module has been loaded\n-----")

    @commands.command(aliases=['Quote'])
    async def quote(self, ctx, subcommand: str = "get", *, quote: str = None):
        """ commands to add and retrieve quotes to/from the db"""
        if subcommand.lower() == 'add':
            if not quote:
                await ctx.send(
                    ":interrobang: You need to give me a quote to add!")
                pass

            if quote:
                if len(quote.strip()) > 0:
                    # add the quote to the database if it's non-zero
                    dbconn = sqlite3.connect(dbfile)
                    cur = dbconn.cursor()
                    cur.execute("INSERT INTO quotes VALUES (?)", [quote])
                    rowid = cur.lastrowid
                    dbconn.commit()
                    await ctx.send(":microphone: " + "[" + str(rowid) + "] " +
                                   quote + " added to database")
                    dbconn.close()

        if subcommand.lower() == "get":
            try:
                quote = int(quote)
                # user wants a specific quote ID
                dbconn = sqlite3.connect(dbfile)
                cur = dbconn.cursor()
                randquote = cur.execute(
                    "SELECT * FROM quotes WHERE rowid = ?;", [quote])
                randquote = randquote.fetchall()[0][0]
                id = quote
                await ctx.send("[" + str(id) + "] " + randquote)
                dbconn.close()
            except:
                # assume user wants a random quote back
                dbconn = sqlite3.connect(dbfile)
                cur = dbconn.cursor()
                randquote = cur.execute(
                    "SELECT * FROM quotes ORDER BY RANDOM() LIMIT 1;")
                randquote = randquote.fetchall()[0][0]
                rowid = cur.execute(
                    "SELECT rowid FROM quotes WHERE quote like (?)",
                    [randquote])
                id = rowid.fetchall()[0][0]
                await ctx.send("[" + str(id) + "] " + randquote)
                dbconn.close()


def setup(bot):
    bot.add_cog(Quotes(bot))
