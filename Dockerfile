FROM python:3
ENV OPENWEATHER_API_KEY = 1234
ENV DISCORD_TOKEN = 1234

COPY . /app
WORKDIR /app

RUN pip3 install -r requirements.txt
CMD python3 ./bot.py
