FROM python:3.8

# Set environment variables
ENV OPENWEATHER_API_KEY=1234
ENV DISCORD_TOKEN=1234

# Copy the application files
COPY . /app

# Set the working directory
WORKDIR /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

RUN pip freeze > /tmp/pip.txt

# Run the application
CMD ["python", "./bot.py"]

