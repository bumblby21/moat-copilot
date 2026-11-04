FROM python:3.11-slim

# Install system fonts and dependencies for matplotlib Korean rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run bot
CMD ["python", "bot.py"]
