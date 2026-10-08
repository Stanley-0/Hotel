"""Interface every hotel provider must satisfy."""

from typing import Protocol

from app.models import HotelOffer, SearchRequest


class HotelProvider(Protocol):
    name: str

    def search_hotels(self, request: SearchRequest) -> list[HotelOffer]:
        """Return normalized offers for a search request."""
