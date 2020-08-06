from discord.ext import commands
from mcstatus import MinecraftServer


class minecraft(commands.Cog):
  def __init__(self, bot):
    self.bot = bot

  @commands.Cog.listener()
  async def on_ready(self):
    print("Minecraft Lookup has been loaded\n-----")

  @commands.command(aliases=['mc'])
  async def minecraft(self, ctx, server: str):
    """ Lookup players on a given host name."""
    server = MinecraftServer.lookup(server)
    status = server.status()
    print(server.status())
    await ctx.send(":cowboy:" +
                   " The server has {0} players and replied in {1} ms".format(
                       status.players.online, status.latency))


def setup(bot):
  bot.add_cog(minecraft(bot))
