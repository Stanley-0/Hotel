# Hotel Bot

A Python hotel-search app with a Flask web interface and command-line workflow, configured for **Accra, Ghana**. The web app and CLI share the same search models, provider selection, filters, and Excel export service. The default browser provider searches Booking.com's public results page through local Chrome and Selenium.

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
├── search_parameters.py     # Shared fallback search defaults
├── config.yaml               # Search and provider configuration
├── main.py                   # Command-line entry point
├── web_app.py                # Flask web entry point
├── templates/                # Search and results pages
├── static/                   # Styles, browser behavior, and artwork
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

## Run the web app

The Flask interface uses the same provider, search validation, price/rating filters, and Excel exporter as the command-line app. After installing the requirements, start the server:

```powershell
py web_app.py
```

Open `http://localhost:3000`. Submit the search form to run the provider search; successful searches open a separate results page, where matching offers can be exported to Excel.

For a predictable local demo without opening Chrome, use the clearly labeled sample provider:

```powershell
$env:HOTEL_PROVIDER_OVERRIDE = "mock"
py web_app.py
```

Remove that environment variable before using the provider configured in `config.yaml`. The default Selenium provider requires local Chrome. Search shortlists are held in process memory for 30 minutes, so this setup is intended to run as one app process; results are cleared when the server restarts.

## Run the CLI

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

Edit the `search` section in `config.yaml` to set the destination, travel dates,
guests, rooms, currency, and price or rating filters for both the web app and
CLI. Values in this file override fallback values in `search_parameters.py`;
CLI flags override the configured values. Add each child's age to
`children_ages`, because Booking.com uses ages to return valid availability and
prices. Set `min_price`, `max_price`, or `min_rating` to `None` to leave that filter off.

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

`config.yaml` currently searches Accra from 10 to 15 December 2026 for two adults, one room, in Ghana cedi. Its search settings are the shared defaults for the web app and CLI; `search_parameters.py` supplies fallback values when a setting is omitted.
