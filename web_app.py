from __future__ import annotations

import logging
import math
import os
import secrets
import threading
import time
from collections import OrderedDict
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request, send_file, url_for
from selenium.common.exceptions import WebDriverException

from app.config import Config, ConfigError
from app.engines.filter_engine import filter_offers
from app.engines.search_engine import HotelSearchEngine
from app.models import HotelOffer, SearchRequest
from app.services.excel_exporter import export_offers_to_excel_buffer
from app.services.provider_factory import create_provider
from search_parameters import SEARCH_PARAMETERS


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent
CURRENCY_LABELS = (
    ("GHS", "Ghana cedi"),
    ("USD", "US dollar"),
    ("EUR", "Euro"),
    ("GBP", "British pound"),
)
RESULT_CACHE_TTL_SECONDS = 30 * 60
RESULT_CACHE_LIMIT = 25
MAX_CHILDREN = 8
MAX_PRICE = 1_000_000


def _bounded_integer(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a whole number between {minimum} and {maximum}.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a whole number between {minimum} and {maximum}.") from None
    if not math.isfinite(number) or not number.is_integer():
        raise ValueError(f"{field} must be a whole number between {minimum} and {maximum}.")
    result = int(number)
    if result < minimum or result > maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}.")
    return result


def _optional_number(value: Any, field: str, maximum: float) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number between 0 and {maximum:g}.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number between 0 and {maximum:g}.") from None
    if not math.isfinite(number) or number < 0 or number > maximum:
        raise ValueError(f"{field} must be a number between 0 and {maximum:g}.")
    return number


def _parse_iso_date(value: Any, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} is required.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field} must be a valid date.") from None
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must be a valid date.")
    return parsed


def _safe_external_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    if any(ord(character) < 32 for character in candidate):
        return None
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    return candidate


def _offer_payload(offer: HotelOffer, nights: int) -> dict[str, Any]:
    return {
        "hotel_name": offer.hotel_name,
        "room_name": offer.room_name,
        "nightly_price": offer.nightly_price,
        "total_price": round(offer.nightly_price * nights, 2),
        "currency": offer.currency,
        "guest_rating": offer.guest_rating,
        "address": offer.address,
        "deep_link": _safe_external_url(offer.deep_link),
    }


def _parse_search_payload(payload: dict[str, Any]) -> tuple[SearchRequest, dict[str, Any]]:
    destination_value = payload.get("destination")
    if not isinstance(destination_value, str):
        raise ValueError("Enter a destination to search.")
    destination = destination_value.strip()
    if not destination:
        raise ValueError("Enter a destination to search.")
    if len(destination) > 120:
        raise ValueError("Destination must be 120 characters or fewer.")

    check_in = _parse_iso_date(payload.get("check_in"), "Check-in")
    check_out = _parse_iso_date(payload.get("check_out"), "Check-out")
    if check_in < date.today():
        raise ValueError("Check-in must be today or a future date.")
    if check_out <= check_in:
        raise ValueError("Check-out must be after check-in.")
    nights = (check_out - check_in).days
    if nights > 365:
        raise ValueError("A stay cannot be longer than 365 nights.")

    adults = _bounded_integer(payload.get("adults", 2), "Adults", 1, 20)
    rooms = _bounded_integer(payload.get("rooms", 1), "Rooms", 1, 10)
    raw_ages = payload.get("children_ages", [])
    if not isinstance(raw_ages, list) or len(raw_ages) > MAX_CHILDREN:
        raise ValueError(f"Enter ages for up to {MAX_CHILDREN} children.")
    children_ages = [
        _bounded_integer(age, "Child age", 0, 17)
        for age in raw_ages
    ]

    currency = payload.get("currency", "GHS")
    if not isinstance(currency, str):
        raise ValueError("Choose a supported currency.")
    currency = currency.upper()
    if currency not in {code for code, _ in CURRENCY_LABELS}:
        raise ValueError("Choose a supported currency.")

    min_price = _optional_number(payload.get("min_price"), "Minimum price", MAX_PRICE)
    max_price = _optional_number(payload.get("max_price"), "Maximum price", MAX_PRICE)
    min_rating = _optional_number(payload.get("min_rating"), "Minimum rating", 10)
    if min_price is not None and max_price is not None and min_price > max_price:
        raise ValueError("Minimum price must not be greater than maximum price.")

    search_values = {
        "destination": destination,
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
        "adults": adults,
        "children_ages": children_ages,
        "rooms": rooms,
        "currency": currency,
        "min_price": min_price,
        "max_price": max_price,
        "min_rating": min_rating,
        "headless": True,
    }
    search_request = SearchRequest.from_mapping(search_values)
    return search_request, search_values


def _read_settings(config_path: str | Path) -> dict[str, Any]:
    config = Config(config_path)
    return {**SEARCH_PARAMETERS, **(config.get("search") or {})}


def _page_defaults(settings: dict[str, Any]) -> dict[str, Any]:
    today = date.today()
    try:
        check_in = date.fromisoformat(str(settings.get("check_in", "")))
    except ValueError:
        check_in = today + timedelta(days=14)
    if check_in < today:
        check_in = today + timedelta(days=14)

    try:
        check_out = date.fromisoformat(str(settings.get("check_out", "")))
    except ValueError:
        check_out = check_in + timedelta(days=5)
    if check_out <= check_in:
        check_out = check_in + timedelta(days=5)

    currency = str(settings.get("currency", "GHS")).upper()
    if currency not in {code for code, _ in CURRENCY_LABELS}:
        currency = "GHS"
    children_ages = settings.get("children_ages") or []

    return {
        "destination": str(settings.get("destination") or "Accra, Ghana"),
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
        "adults": max(1, min(20, int(settings.get("adults", 2)))),
        "rooms": max(1, min(10, int(settings.get("rooms", 1)))),
        "children_ages": ", ".join(str(age) for age in children_ages),
        "currency": currency,
        "today": today.isoformat(),
    }


def create_app(
    config_path: str | Path | None = None,
    *,
    provider_name: str | None = None,
) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024
    app.config["HOTEL_CONFIG_PATH"] = Path(
        config_path or os.environ.get("HOTEL_CONFIG_PATH", PROJECT_ROOT / "config.yaml")
    )
    app.config["HOTEL_PROVIDER_OVERRIDE"] = (
        provider_name if provider_name is not None else os.environ.get("HOTEL_PROVIDER_OVERRIDE")
    )

    result_cache: OrderedDict[str, tuple[float, SearchRequest, list[HotelOffer], str]] = OrderedDict()
    cache_lock = threading.Lock()

    def save_result(
        search_request: SearchRequest,
        offers: list[HotelOffer],
        provider_name: str,
    ) -> str:
        now = time.monotonic()
        search_id = secrets.token_urlsafe(18)
        with cache_lock:
            expired = [
                key
                for key, (created_at, _, _, _) in result_cache.items()
                if now - created_at > RESULT_CACHE_TTL_SECONDS
            ]
            for key in expired:
                result_cache.pop(key, None)
            result_cache[search_id] = (now, search_request, offers, provider_name)
            while len(result_cache) > RESULT_CACHE_LIMIT:
                result_cache.popitem(last=False)
        return search_id

    def get_result(search_id: str) -> tuple[float, SearchRequest, list[HotelOffer], str] | None:
        with cache_lock:
            cached = result_cache.get(search_id)
            if cached and time.monotonic() - cached[0] > RESULT_CACHE_TTL_SECONDS:
                result_cache.pop(search_id, None)
                return None
            return cached

    @app.get("/")
    def home():
        settings = _read_settings(app.config["HOTEL_CONFIG_PATH"])
        return render_template(
            "index.html",
            defaults=_page_defaults(settings),
            currencies=CURRENCY_LABELS,
        )

    @app.post("/api/search")
    def search():
        if not request.is_json:
            return jsonify(error="Send search details as JSON."), 415
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="Search details could not be read."), 400

        try:
            search_request, search_values = _parse_search_payload(payload)
            config = Config(app.config["HOTEL_CONFIG_PATH"])
            search_settings = {
                **SEARCH_PARAMETERS,
                **(config.get("search") or {}),
                **search_values,
            }
            config.data["booking_parameters"] = search_settings
            override = app.config["HOTEL_PROVIDER_OVERRIDE"]
            if override:
                provider_settings = config.data.setdefault("provider", {})
                if not isinstance(provider_settings, dict):
                    provider_settings = {}
                    config.data["provider"] = provider_settings
                provider_settings["name"] = str(override)

            provider = create_provider(config)
            offers = HotelSearchEngine(provider).search(search_request)
            offers = filter_offers(
                offers,
                min_nightly_price=search_values["min_price"],
                max_nightly_price=search_values["max_price"],
                min_guest_rating=search_values["min_rating"],
            )
        except ConfigError:
            LOGGER.exception("Hotel search configuration could not be loaded")
            return jsonify(error="The search configuration could not be loaded."), 503
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except (RuntimeError, WebDriverException) as error:
            LOGGER.warning("Hotel search failed: %s", error)
            return jsonify(error=str(error)), 502
        except Exception:
            LOGGER.exception("Hotel search failed unexpectedly")
            return jsonify(error="The search could not be completed. Check the configured provider and try again."), 502

        search_id = save_result(search_request, offers, provider.name)
        nights = (search_request.check_out - search_request.check_in).days
        return jsonify(
            search_id=search_id,
            results_url=url_for("show_results", search_id=search_id),
            provider=provider.name,
            is_sample=provider.name == "mock",
            search={
                "destination": search_request.destination,
                "check_in": search_request.check_in.isoformat(),
                "check_out": search_request.check_out.isoformat(),
                "nights": nights,
                "adults": search_request.adults,
                "children": search_request.children,
                "rooms": search_request.rooms,
                "currency": search_request.currency,
            },
            offers=[_offer_payload(offer, nights) for offer in offers],
        )

    @app.get("/results/<search_id>")
    def show_results(search_id: str):
        cached = get_result(search_id)
        if cached is None:
            return render_template("results.html", expired=True), 404

        _, search_request, offers, provider_name = cached
        nights = (search_request.check_out - search_request.check_in).days
        check_in = search_request.check_in
        check_out = search_request.check_out
        date_range = (
            f"{check_in.strftime('%b')} {check_in.day} – "
            f"{check_out.strftime('%b')} {check_out.day}, {check_out.year}"
        )
        return render_template(
            "results.html",
            expired=False,
            search_id=search_id,
            search=search_request,
            search_dates=date_range,
            nights=nights,
            offers=[_offer_payload(offer, nights) for offer in offers],
            provider_name=provider_name.replace("_", " "),
            is_sample=provider_name == "mock",
        )

    @app.get("/api/search/<search_id>/export")
    def export_search(search_id: str):
        cached = get_result(search_id)
        if cached is None:
            return jsonify(error="These results have expired. Run the search again to export them."), 404

        _, search_request, offers, _ = cached
        workbook = export_offers_to_excel_buffer(offers, search_request)
        return send_file(
            workbook,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name="hotel-search-results.xlsx",
            max_age=0,
        )

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Strict-Transport-Security", "max-age=63072000")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy-Report-Only",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; font-src 'self'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'",
        )
        if request.endpoint in {"search", "show_results", "export_search"}:
            response.headers["Cache-Control"] = "private, no-store"
        return response

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("WEB_HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "3000")),
        debug=False,
        threaded=True,
    )


__all__ = ["app", "create_app"]
