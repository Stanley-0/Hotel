"""Booking.com Demand API adapter for authorised partner credentials only."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.models import HotelOffer, SearchRequest


class BookingComProvider:
    name = "booking_com"

    def __init__(
        self, *, integration_base_url: str | None, api_key_env: str, affiliate_id_env: str,
        booker_country: str = "gh", children_ages: list[int] | None = None,
        min_price: float | None = None, max_price: float | None = None,
        min_rating: float | None = None, max_results: int = 10,
    ) -> None:
        self.integration_base_url = integration_base_url
        self.api_key = os.getenv(api_key_env)
        self.affiliate_id = os.getenv(affiliate_id_env)
        self.booker_country = booker_country
        self.children_ages = children_ages or []
        self.min_price = min_price
        self.max_price = max_price
        self.min_rating = min_rating
        self.max_results = max_results

    def search_hotels(self, request: SearchRequest) -> list[HotelOffer]:
        if not self.integration_base_url or not self.api_key or not self.affiliate_id:
            raise RuntimeError(
                "Booking.com is not ready. Set BOOKING_COM_API_KEY and BOOKING_COM_AFFILIATE_ID "
                "to your authorised Demand API credentials."
            )
        response = self._post_json(self._build_payload(request))
        nights = (request.check_out - request.check_in).days
        return [
            self._to_offer(item, request.currency, nights)
            for item in response.get("data", [])
        ]

    def _build_payload(self, request: SearchRequest) -> dict[str, Any]:
        guests: dict[str, Any] = {
            "number_of_adults": request.adults,
            "number_of_rooms": request.rooms,
        }
        if self.children_ages:
            guests["children"] = self.children_ages

        filters: dict[str, Any] = {}
        if self.min_price is not None or self.max_price is not None:
            filters["price"] = {
                key: value for key, value in {"minimum": self.min_price, "maximum": self.max_price}.items()
                if value is not None
            }
        if self.min_rating is not None:
            filters["rating"] = {"minimum_review_score": self.min_rating}

        payload: dict[str, Any] = {
            "search_query": request.destination,
            "checkin": request.check_in.isoformat(),
            "checkout": request.check_out.isoformat(),
            "booker": {"country": self.booker_country.lower(), "platform": "desktop"},
            "guests": guests,
            "currency": request.currency,
            "rows": self.max_results,
            "extras": ["products"],
        }
        if filters:
            payload["filters"] = filters
        return payload

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            self.integration_base_url.rstrip("/") + "/accommodations/smart-search",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-Affiliate-Id": self.affiliate_id,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Booking.com returned HTTP {error.code}: {detail}") from error
        except URLError as error:
            raise RuntimeError(f"Could not reach Booking.com: {error.reason}") from error

    @staticmethod
    def _to_offer(item: dict[str, Any], requested_currency: str, nights: int) -> HotelOffer:
        price = item.get("price", {})
        total = price.get("total", {}) if isinstance(price, dict) else {}
        amount = total.get("booker_currency", total.get("accommodation_currency", 0))
        currency = item.get("currency", {})
        if isinstance(currency, dict):
            currency = currency.get("booker", currency.get("accommodation", requested_currency))
        products = item.get("products") or []
        room_name = products[0].get("room", "Best available room") if products else "Best available room"
        name = item.get("name", item.get("accommodation_name", "Booking.com property"))
        rating = item.get("review_score", item.get("rating"))
        try:
            guest_rating = float(rating) if rating not in (None, "") else None
        except (TypeError, ValueError):
            guest_rating = None
        location = item.get("location") or {}
        if not isinstance(location, dict):
            location = {}
        address = item.get("address") or location.get("address") or location.get("address_line")
        coordinates = item.get("coordinates") or location.get("coordinates") or {}
        if not isinstance(coordinates, dict):
            coordinates = {}
        latitude = item.get("latitude", location.get("latitude", coordinates.get("latitude")))
        longitude = item.get("longitude", location.get("longitude", coordinates.get("longitude")))
        url = item.get("url", item.get("deep_link"))
        if isinstance(url, dict):
            url = url.get("url")
        nightly_price = round(float(amount) / nights, 2)
        return HotelOffer(
            str(name),
            str(room_name),
            nightly_price,
            str(currency),
            guest_rating,
            url,
            str(address) if address else None,
            float(latitude) if latitude is not None else None,
            float(longitude) if longitude is not None else None,
        )
