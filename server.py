"""One-page web UI for the Booking.com scraper.

    python server.py            # http://localhost:5000
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import date

from flask import Flask, jsonify, render_template, request

from scraper import CURRENCIES, MAX_GUESTS, MAX_ROOMS, ScrapeError, SearchQuery, scrape_booking

app = Flask(__name__)
log = logging.getLogger(__name__)

# One Chrome instance at a time keeps memory use predictable on a laptop.
_browser_lock = threading.Lock()


def _parse_int(value, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a whole number.")
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a whole number.") from None
    return number


def _parse_date(value, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a valid date.") from None


def query_from_payload(payload: dict) -> SearchQuery:
    query = SearchQuery(
        location=str(payload.get("location", "")).strip(),
        adults=_parse_int(payload.get("adults"), "Number of people"),
        check_in=_parse_date(payload.get("check_in"), "Check-in"),
        check_out=_parse_date(payload.get("check_out"), "Check-out"),
        rooms=_parse_int(payload.get("rooms"), "Number of rooms"),
        currency=str(payload.get("currency", "")).upper(),
    )
    query.validate()
    return query


@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


@app.get("/")
def index():
    return render_template(
        "index.html",
        currencies=CURRENCIES,
        today=date.today().isoformat(),
        max_guests=MAX_GUESTS,
        max_rooms=MAX_ROOMS,
    )


@app.post("/api/search")
def search():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Send the search as JSON."), 400

    try:
        query = query_from_payload(payload)
    except ValueError as error:
        return jsonify(error=str(error)), 400

    if not _browser_lock.acquire(blocking=False):
        return jsonify(error="A search is already running. Wait for it to finish."), 429

    try:
        results = scrape_booking(query, headless=os.environ.get("SHOW_BROWSER") != "1")
    except ScrapeError as error:
        return jsonify(error=str(error)), 502
    except Exception:
        log.exception("Scrape failed")
        return jsonify(
            error="Couldn't start Chrome. Make sure Google Chrome is installed on this machine."
        ), 503
    finally:
        _browser_lock.release()

    return jsonify(
        query={
            "location": query.location,
            "adults": query.adults,
            "rooms": query.rooms,
            "check_in": query.check_in.isoformat(),
            "check_out": query.check_out.isoformat(),
            "nights": query.nights,
            "currency": query.currency,
        },
        results=[item.to_dict() for item in results],
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
