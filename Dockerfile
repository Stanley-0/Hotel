FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium chromium-driver fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scraper.py server.py ./
COPY templates ./templates
COPY static ./static

EXPOSE 8000

# One worker so only one Chrome runs at a time; scrapes can take a minute, hence the long timeout.
CMD gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 180 server:app
