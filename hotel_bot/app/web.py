"""Local web interface and JSON API for hotel searches."""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from collections import OrderedDict
from datetime import date, timedelta
from pathlib import Path
from secrets import token_urlsafe
from typing import Annotated

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator
from selenium.common.exceptions import WebDriverException
from starlette.background import BackgroundTask

from app.config import Config
from app.engines.filter_engine import filter_offers
from app.engines.search_engine import HotelSearchEngine
from app.models import HotelOffer, SearchRequest
from app.services.excel_exporter import export_offers_to_excel
from app.services.provider_factory import create_provider
from search_parameters import SEARCH_PARAMETERS

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_SAVED_SEARCHES = 32

app = FastAPI(title="The Stay Edit", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class SearchPayload(BaseModel):
    destination: Annotated[str, Field(min_length=2, max_length=120)]
    check_in: date
    check_out: date
    adults: Annotated[int, Field(ge=1, le=30)] = 2
    children_ages: Annotated[list[Annotated[int, Field(ge=0, le=17)]], Field(max_length=10)] = Field(
        default_factory=list,
    )
    rooms: Annotated[int, Field(ge=1, le=30)] = 1
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] = "GHS"
    min_price: Annotated[float | None, Field(ge=0)] = None
    max_price: Annotated[float | None, Field(ge=0)] = None
    min_rating: Annotated[float | None, Field(ge=0, le=10)] = None

    @field_validator("destination")
    @classmethod
    def trim_destination(cls, value: str) -> str:
        destination = value.strip()
        if len(destination) < 2:
            raise ValueError("Enter a destination with at least two characters.")
        return destination

    @model_validator(mode="after")
    def validate_trip(self) -> SearchPayload:
        if self.check_out <= self.check_in:
            raise ValueError("Check-out must be after check-in.")
        if self.min_price is not None and self.max_price is not None:
            if self.min_price > self.max_price:
                raise ValueError("Minimum price cannot be greater than maximum price.")
        return self


saved_searches: OrderedDict[str, tuple[SearchRequest, list[HotelOffer]]] = OrderedDict()
saved_searches_lock = threading.Lock()


def _config() -> Config:
    config_path = Path(os.environ.get("HOTEL_BOT_CONFIG", ROOT / "config.yaml"))
    return Config(config_path)


def _search_defaults() -> dict[str, object]:
    config = _config()
    return {**(config.get("search") or {}), **SEARCH_PARAMETERS}


def _remember_search(request: SearchRequest, offers: list[HotelOffer]) -> str:
    search_id = token_urlsafe(24)
    with saved_searches_lock:
        saved_searches[search_id] = (request, offers)
        while len(saved_searches) > MAX_SAVED_SEARCHES:
            saved_searches.popitem(last=False)
    return search_id


def _remove_export(path: str) -> None:
    Path(path).unlink(missing_ok=True)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config")
def get_config() -> dict[str, object]:
    config = _config()
    settings = _search_defaults()
    today = date.today()
    check_in = settings.get("check_in", today.isoformat())
    provider_name = config.get("provider", "name", "mock")
    provider_labels = {
        "booking_com_selenium": "Booking.com · background search",
        "booking_com": "Booking.com · authorized API",
        "mock": "Demo data",
    }
    return {
        "search": {
            "destination": settings.get("destination", "Accra, Ghana"),
            "check_in": check_in,
            "check_out": settings.get("check_out", (today + timedelta(days=1)).isoformat()),
            "adults": settings.get("adults", 2),
            "children_ages": settings.get("children_ages", []),
            "rooms": settings.get("rooms", 1),
            "currency": settings.get("currency", "GHS"),
            "min_price": settings.get("min_price"),
            "max_price": settings.get("max_price"),
            "min_rating": settings.get("min_rating"),
        },
        "provider": provider_labels.get(provider_name, provider_name),
    }


@app.post("/api/search")
def search(payload: SearchPayload) -> dict[str, object]:
    request = SearchRequest.from_mapping(payload.model_dump(mode="json"))
    config = _config()
    settings = _search_defaults()
    settings.update(payload.model_dump(mode="json"))
    settings["headless"] = True
    config.data["booking_parameters"] = settings

    try:
        provider = create_provider(config)
    except ValueError as error:
        logger.error("Invalid hotel-search provider configuration: %s", error)
        raise HTTPException(status_code=500, detail=f"Search provider configuration is invalid: {error}") from error

    try:
        offers = HotelSearchEngine(provider).search(request)
    except (RuntimeError, ValueError, WebDriverException) as error:
        logger.exception("Hotel search failed for %s", request.destination)
        raise HTTPException(status_code=502, detail=str(error)) from error

    offers = filter_offers(
        offers,
        min_nightly_price=payload.min_price,
        max_nightly_price=payload.max_price,
        min_guest_rating=payload.min_rating,
    )
    search_id = _remember_search(request, offers)
    nights = (request.check_out - request.check_in).days
    return {
        "search_id": search_id,
        "destination": request.destination,
        "nights": nights,
        "count": len(offers),
        "offers": [
            {
                "hotel_name": offer.hotel_name,
                "room_name": offer.room_name,
                "nightly_price": offer.nightly_price,
                "currency": offer.currency,
                "guest_rating": offer.guest_rating,
                "deep_link": offer.deep_link,
                "address": offer.address,
                "latitude": offer.latitude,
                "longitude": offer.longitude,
                "total_price": round(offer.nightly_price * nights, 2),
            }
            for offer in offers
        ],
    }


@app.get("/api/searches/{search_id}/export")
def export_search(search_id: str) -> FileResponse:
    with saved_searches_lock:
        saved = saved_searches.get(search_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="This search has expired. Run it again to export the results.")

    request, offers = saved
    file_descriptor, output_path = tempfile.mkstemp(suffix=".xlsx", prefix="stay-edit-")
    os.close(file_descriptor)
    try:
        export_offers_to_excel(offers, request, output_path)
    except (OSError, ValueError) as error:
        _remove_export(output_path)
        logger.exception("Could not create the hotel-search workbook")
        raise HTTPException(status_code=500, detail="The spreadsheet could not be created.") from error

    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"stays-{request.check_in.isoformat()}.xlsx",
        background=BackgroundTask(_remove_export, output_path),
    )
