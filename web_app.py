from __future__ import annotations

import logging
import math
import os
import re
import secrets
import time
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
SUPPORTED_CURRENCIES = {code for code, _ in CURRENCY_LABELS}
RESULT_TTL_MS = 30 * 60 * 1000
RESULT_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{20,64}")
MAX_CHILDREN = 8
MAX_PRICE = 1_000_000
MAX_EXPORT_OFFERS = 100
MAX_EXPORT_TEXT_LENGTH = 1_000


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


def _bounded_number(
    value: Any,
    field: str,
    minimum: float,
    maximum: float,
    *,
    optional: bool = False,
) -> float | None:
    if optional and (value is None or value == ""):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number between {minimum:g} and {maximum:g}.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number between {minimum:g} and {maximum:g}.") from None
    if not math.isfinite(number) or number < minimum or number > maximum:
        raise ValueError(f"{field} must be a number between {minimum:g} and {maximum:g}.")
    return number


def _optional_number(value: Any, field: str, maximum: float) -> float | None:
    return _bounded_number(value, field, 0, maximum, optional=True)


def _optional_text(value: Any, field: str, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text.")
    text = value.strip()
    if required and not text:
        raise ValueError(f"{field} is required.")
    if len(text) > MAX_EXPORT_TEXT_LENGTH:
        raise ValueError(f"{field} must be {MAX_EXPORT_TEXT_LENGTH} characters or fewer.")
    return text or None


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
        "latitude": offer.latitude,
        "longitude": offer.longitude,
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
    children_ages = [_bounded_integer(age, "Child age", 0, 17) for age in raw_ages]

    currency_value = payload.get("currency", "GHS")
    if not isinstance(currency_value, str):
        raise ValueError("Choose a supported currency.")
    currency = currency_value.upper()
    if currency not in SUPPORTED_CURRENCIES:
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
    return SearchRequest.from_mapping(search_values), search_values


def _parse_export_payload(
    payload: dict[str, Any],
    expected_search_id: str,
) -> tuple[SearchRequest, list[HotelOffer]]:
    if payload.get("search_id") != expected_search_id:
        raise ValueError("These results do not match the requested export.")

    created_at_ms = payload.get("created_at_ms")
    if isinstance(created_at_ms, bool) or not isinstance(created_at_ms, int):
        raise ValueError("These results are incomplete. Run the search again to export them.")
    age_ms = int(time.time() * 1000) - created_at_ms
    if age_ms < -60_000 or age_ms > RESULT_TTL_MS:
        raise ValueError("These results have expired. Run the search again to export them.")

    raw_search = payload.get("search")
    if not isinstance(raw_search, dict):
        raise ValueError("Search details are missing. Run the search again to export results.")
    search_request, _ = _parse_search_payload(raw_search)

    raw_offers = payload.get("offers")
    if not isinstance(raw_offers, list) or len(raw_offers) > MAX_EXPORT_OFFERS:
        raise ValueError(f"The export must contain no more than {MAX_EXPORT_OFFERS} offers.")

    offers: list[HotelOffer] = []
    for item in raw_offers:
        if not isinstance(item, dict):
            raise ValueError("One of the hotel offers is invalid.")

        hotel_name = _optional_text(item.get("hotel_name"), "Hotel name", required=True)
        room_name = _optional_text(item.get("room_name"), "Room name") or "Best available room"
        nightly_price = _bounded_number(
            item.get("nightly_price"), "Nightly price", 0, MAX_PRICE
        )
        currency_value = item.get("currency")
        if not isinstance(currency_value, str) or currency_value.upper() not in SUPPORTED_CURRENCIES:
            raise ValueError("One of the hotel offers has an unsupported currency.")
        guest_rating = _optional_number(item.get("guest_rating"), "Guest rating", 10)
        address = _optional_text(item.get("address"), "Hotel address")
        latitude = _bounded_number(
            item.get("latitude"), "Latitude", -90, 90, optional=True
        )
        longitude = _bounded_number(
            item.get("longitude"), "Longitude", -180, 180, optional=True
        )

        offers.append(
            HotelOffer(
                hotel_name=hotel_name,
                room_name=room_name,
                nightly_price=nightly_price,
                currency=currency_value.upper(),
                guest_rating=guest_rating,
                deep_link=_safe_external_url(item.get("deep_link")),
                address=address,
                latitude=latitude,
                longitude=longitude,
            )
        )

    return search_request, offers


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
    if currency not in SUPPORTED_CURRENCIES:
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
    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024
    app.config["HOTEL_CONFIG_PATH"] = Path(
        config_path or os.environ.get("HOTEL_CONFIG_PATH", PROJECT_ROOT / "config.yaml")
    )
    app.config["HOTEL_PROVIDER_OVERRIDE"] = (
        provider_name if provider_name is not None else os.environ.get("HOTEL_PROVIDER_OVERRIDE")
    )

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
            )[:MAX_EXPORT_OFFERS]
        except ConfigError:
            LOGGER.exception("Hotel search configuration could not be loaded")
            return jsonify(error="The search configuration could not be loaded."), 503
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except WebDriverException:
            LOGGER.exception("The Selenium browser could not complete the hotel search")
            return jsonify(
                error=(
                    "The browser could not complete the Booking.com search. Check your local Chrome "
                    "installation or Selenium remote browser settings, then try again."
                )
            ), 502
        except RuntimeError as error:
            LOGGER.warning("Hotel search failed: %s", error)
            return jsonify(error=str(error)), 502
        except Exception:
            LOGGER.exception("Hotel search failed unexpectedly")
            return jsonify(
                error="The search could not be completed. Check the configured provider and try again."
            ), 502

        search_id = secrets.token_urlsafe(18)
        nights = (search_request.check_out - search_request.check_in).days
        created_at_ms = int(time.time() * 1000)
        return jsonify(
            search_id=search_id,
            results_url=url_for("show_results", search_id=search_id),
            created_at_ms=created_at_ms,
            provider=provider.name,
            is_sample=provider.name == "mock",
            search={
                "destination": search_request.destination,
                "check_in": search_request.check_in.isoformat(),
                "check_out": search_request.check_out.isoformat(),
                "adults": search_request.adults,
                "children_ages": search_values["children_ages"],
                "rooms": search_request.rooms,
                "currency": search_request.currency,
            },
            offers=[_offer_payload(offer, nights) for offer in offers],
        )

    @app.get("/results/<search_id>")
    def show_results(search_id: str):
        return render_template("results.html", search_id=search_id)

    @app.post("/api/search/<search_id>/export")
    def export_search(search_id: str):
        if not RESULT_ID_PATTERN.fullmatch(search_id):
            return jsonify(error="These results are not available. Run the search again."), 404
        if not request.is_json:
            return jsonify(error="Send the search results as JSON."), 415
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="Search results could not be read."), 400

        try:
            search_request, offers = _parse_export_payload(payload, search_id)
            workbook = export_offers_to_excel_buffer(offers, search_request)
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except Exception:
            LOGGER.exception("Hotel results could not be exported")
            return jsonify(error="The Excel file could not be created. Please try again."), 500

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
