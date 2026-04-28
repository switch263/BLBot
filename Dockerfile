FROM python:3.12-slim

WORKDIR /app

# DejaVu fonts are needed for the lootdrop card renderer (Pillow truetype).
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Copy and install dependencies first for better layer caching
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code after dependencies are installed
COPY . .

CMD ["python3", "./bot.py"]
