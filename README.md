# Staysheet

A small Python bot that uses Selenium to search Booking.com, plus a one-page website to drive it.

Enter a **location**, **number of people**, **check-in / check-out dates**, **number of rooms** and a **currency**. The bot opens Booking.com in Chrome, reads the listings, and the page shows them as a table with:

| Accommodation | Rating | Price per night | Total stay |
| ------------- | ------ | --------------- | ---------- |

Columns are sortable and the table can be downloaded as CSV.

## Project layout

```text
run.py               One-command local start (installs deps, opens the browser)
scraper.py           Selenium bot (also usable from the command line)
server.py            Flask server: serves the page and POST /api/search
templates/index.html The one-page UI
static/              CSS, JS and favicon
Dockerfile           Image with Chromium bundled, for hosting online
render.yaml          One-click deploy to Render
tests/               pytest suite
```

## Run it on your computer

Requires Python 3.10+ and Google Chrome.

```bash
python run.py
```

That installs anything missing, starts the server and opens http://localhost:5000 in your browser.

**In VS Code:** open the folder, pick a Python interpreter (`Ctrl+Shift+P` → *Python: Select Interpreter*), then press **F5** and choose **Run Staysheet (web app)**.

Optional: create a virtual environment first with `python -m venv .venv` and activate it (Windows: `.venv\Scripts\activate`, macOS/Linux: `source .venv/bin/activate`). Set `SHOW_BROWSER=1` to watch Chrome while it scrapes, and `PORT` to change the port.

## Put it online

Selenium needs a real Chrome browser on the server, so this app can't run on serverless hosts like Vercel or Netlify. It runs on any host that supports Docker; the image ships with Chromium.

**Render (free tier):**

1. Push this repo to GitHub.
2. In Render, choose **New → Blueprint** and select the repo. It reads `render.yaml` and builds the `Dockerfile`.
3. When the deploy finishes, open the `https://staysheet-….onrender.com` URL.

**Railway / Fly.io / any VPS:** deploy the `Dockerfile` as-is. The container listens on `$PORT` (default 8000).

**Test the container locally:**

```bash
docker build -t staysheet .
docker run -p 8000:8000 staysheet
```

Notes for hosted use: free plans sleep when idle, so the first request can be slow. Booking.com is more likely to show a CAPTCHA to datacenter IPs than to your home connection; if that happens, the page shows a message instead of results.

## Run the bot from the terminal

```bash
python scraper.py --location "Accra" --adults 2 --rooms 1 \
  --check-in 2026-11-01 --check-out 2026-11-04 --currency USD
```

Add `--show-browser` to run Chrome visibly and `--max-results 25` to limit how many listings are read.

## Tests

```bash
python -m pytest
```

## How prices are calculated

Booking.com shows the total price for the whole stay on each card. The bot stores that as **Total stay** and divides it by the number of nights for **Price per night**.

## Limits

The bot reads public search results only. It never signs in, makes bookings, or bypasses CAPTCHAs. If Booking.com asks for human verification, the search stops with a message. Booking.com changes its markup from time to time; if results stop appearing, check the CSS selectors in `scraper.py`.
