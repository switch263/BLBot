import os

dbtype = 'sqlite'
DATA_DIR = os.environ.get('BOT_DATA_DIR', os.path.join(os.path.dirname(__file__), 'data'))
os.makedirs(DATA_DIR, exist_ok=True)
dbfile = os.path.join(DATA_DIR, 'quotes.db')

# Discord channel where admin commands are accepted, and where kev2tall's
# smite scatters the coins seized from anyone who bounties the memorial.
ADMIN_CHANNEL_ID = 401391297211924480
