FROM python:3.6.10-alpine3.11
ENV OPENWEATHER_API_KEY = 1234
ENV DISCORD_TOKEN = 1234

RUN apk upgrade --no-cache \
  && apk add --no-cache \
    musl \
    build-base \
  && pip3 install --no-cache-dir --upgrade pip \
  && pip3 install setuptools wheel \
  && rm -rf /var/cache/* \
  && rm -rf /root/.cache/*

COPY . /app
WORKDIR /app

RUN pip3 install -r requirements.txt
CMD python3 ./bot.py
