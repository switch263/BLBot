import os
import time

dbtype = 'sqlite'
DATA_DIR = os.environ.get('BOT_DATA_DIR', os.path.join(os.path.dirname(__file__), 'data'))
os.makedirs(DATA_DIR, exist_ok=True)
dbfile = os.path.join(DATA_DIR, 'quotes.db')

# The bot reckons "now" / "calendar day" in local time, controlled by the
# standard POSIX `TZ` env var (e.g. TZ=America/New_York; defaults to the host's
# zone, ultimately UTC in most containers). This governs once-per-day gates
# (jail cards) and day-long effects (heist shields). datetime.now() already
# reads TZ; tzset() makes the C library pick up a TZ set programmatically too
# (absent on Windows — guarded). economy.now_local()/today_str() are the read
# points.
if hasattr(time, "tzset"):
    time.tzset()

# When this process started, for !uptime. Lives here rather than in a cog
# because config is imported once per process — a cog reload would reset it.
BOOT_TIME = time.time()

# Discord channel where admin commands are accepted, and where kev2tall's
# smite scatters the coins seized from anyone who bounties the memorial.
ADMIN_CHANNEL_ID = 401391297211924480
