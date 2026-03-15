import os

dbtype = 'sqlite'
DATA_DIR = os.environ.get('BOT_DATA_DIR', os.path.join(os.path.dirname(__file__), 'data'))
os.makedirs(DATA_DIR, exist_ok=True)
dbfile = os.path.join(DATA_DIR, 'quotes.db')
