# Hotel Bot

A small Python command-line hotel-search app configured for **Accra, Ghana**. By default it opens a local Chrome browser through Selenium and searches Booking.com's public results page with your chosen parameters.

## Important provider boundary

This project does not sign in or make bookings. It uses Selenium only to search and read public result cards in a local browser. It does not bypass CAPTCHAs, human verification, rate limits, or other access controls.

## Folder structure

```text
hotel_bot/
├── app/
│   ├── engines/              # search, filtering, booking boundary
│   ├── providers/            # mock and authorized-provider adapters
│   ├── services/             # provider selection
│   ├── config.py
│   ├── logging_config.py
│   └── models.py
├── tests/
├── search_parameters.py     # Edit your destination, guests, dates, and price range here
├── config.yaml               # Accra defaults
├── main.py
├── requirements.txt
└── .gitignore
```

## Setup in VS Code (Windows)

1. Open this project folder in VS Code: **File → Open Folder**.
2. Open **Terminal → New Terminal**.
3. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation, run the command shown in its error message for the current session, then activate again.

4. Install dependencies:

   ```powershell
   py -m pip install -r requirements.txt
   ```

5. Choose the `.venv` Python interpreter from the VS Code status bar if prompted.

## Run it

Run the local Selenium search:

```powershell
py main.py
```

Matching offers are printed in the terminal and saved by default to
`hotel_results.xlsx` in the current directory. The workbook contains one row
per matching hotel, with columns for hotel name, amount per night, total amount
for the stay, currency, guest rating, street address, latitude, and longitude
when the provider returns those details. Price and rating filters are applied
before the workbook is written. The browser search includes every hotel card returned on
the search results page, without a local `max_results` cutoff. The total
amount shown by the provider is used to calculate the nightly average across
the selected dates.
The workbook opens automatically in the default app for `.xlsx` files when the
search finishes. Add `--no-open-results` to save it without opening:

```powershell
py main.py --no-open-results
```

Set `output_excel` in `search_parameters.py` or pass `--output` to choose a
different workbook path:

```powershell
py main.py --output "output\japan-hotels.xlsx"
```

Optional filters and destination override:

```powershell
py main.py --max-price 1100 --min-rating 8.2
py main.py --destination "Osu, Accra"
```

## Change your search parameters

Open `search_parameters.py` and edit `SEARCH_PARAMETERS` before running the bot.
This is the single place for destination, travel dates, adults, children, rooms,
currency, and minimum/maximum nightly price. Add the age of each child to
`children_ages`, because Booking.com uses ages to return valid availability and
prices. Set `min_price`, `max_price`, or
`min_rating` to `None` to leave that filter off.

Set `headless` to `False` (the default) so you can see the browser. If Booking.com
shows a verification page, resolve it in a normal browser and retry; the bot will
not attempt to bypass it.

Run tests:

```powershell
py -m pytest
```

## Configure an authorized Booking.com integration

Only do this after Booking.com (or an authorized integration partner) has provided approved API access and documentation.

1. Copy `config.yaml` to `config.local.yaml` and keep it out of source control.
2. Set `provider.name` to `booking_com` and set `provider.booking_com.integration_base_url` to the approved API endpoint.
3. Set credentials in your terminal session, rather than in YAML:

   ```powershell
   $env:BOOKING_COM_API_KEY = "your-authorized-key"
   $env:BOOKING_COM_AFFILIATE_ID = "your-authorized-affiliate-id"
   ```

4. Implement the approved API request/response mapping inside `app/providers/booking_com_provider.py`. Keep booking completion in the provider's documented, authorized flow; do not add browser automation or scraping.
5. Run with your local configuration:

   ```powershell
   py main.py --config config.local.yaml
   ```

## Configuration

`config.yaml` currently searches Accra from 10 to 15 December 2026 for two adults, one room, in Ghana cedi. Change the values under `search` to suit your use case.
