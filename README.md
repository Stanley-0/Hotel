# Staysheet

A small Python bot that uses Selenium to search Booking.com, plus a one-page website to drive it.

Enter a **location**, **number of people**, **check-in / check-out dates**, **number of rooms** and a **currency**. The bot opens Booking.com in Chrome, reads the listings, and the page shows them as a table with:

| Accommodation | Rating | Price per night | Total stay |
| ------------- | ------ | --------------- | ---------- |

Columns are sortable and the table can be downloaded as CSV.

## Project layout

```text
scraper.py           Selenium bot (also usable from the command line)
server.py            Flask server: serves the page and POST /api/search
templates/index.html The one-page UI
static/              CSS, JS and favicon
tests/               pytest suite
```

## Setup

Requires Python 3.10+ and Google Chrome. Selenium 4 downloads the matching ChromeDriver automatically.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

## Run the website

```bash
python server.py
```

Open http://localhost:5000. Set `SHOW_BROWSER=1` to watch Chrome while it scrapes, and `PORT` to change the port.

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
