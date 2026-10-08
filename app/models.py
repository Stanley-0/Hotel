
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping


@dataclass(frozen=True)
class SearchRequest:
    destination: str
    check_in: date
    check_out: date
    adults: int = 2
    children: int = 0
    rooms: int = 1
    currency: str = "GHS"

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | None, *, destination: str | None = None) -> "SearchRequest":
        if not values:
            raise ValueError("The 'search' configuration section is required.")
        request = cls(
            destination=destination or str(values["destination"]),
            check_in=date.fromisoformat(str(values["check_in"])),
            check_out=date.fromisoformat(str(values["check_out"])),
            adults=int(values.get("adults", 2)),
            children=len(values["children_ages"]) if "children_ages" in values else int(values.get("children", 0)),
            rooms=int(values.get("rooms", 1)),
            currency=str(values.get("currency", "GHS")),
        )
        if request.check_out <= request.check_in:
            raise ValueError("check_out must be after check_in.")
        if request.adults < 1 or request.children < 0 or request.rooms < 1:
            raise ValueError("adults and rooms must be at least 1; children cannot be negative.")
        return request


@dataclass(frozen=True)
class HotelOffer:
    hotel_name: str
    room_name: str
    nightly_price: float
    currency: str
    guest_rating: float
    deep_link: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
