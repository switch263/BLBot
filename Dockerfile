FROM python:3.12-slim

WORKDIR /app

# Copy and install dependencies first for better layer caching
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code after dependencies are installed
COPY . .

CMD ["python3", "./bot.py"]
