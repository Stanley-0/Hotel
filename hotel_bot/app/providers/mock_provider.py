"""Deterministic local provider for development and tests."""

from app.models import HotelOffer, SearchRequest


class MockHotelProvider:
    name = "mock"

    def search_hotels(self, request: SearchRequest) -> list[HotelOffer]:
        return [
            HotelOffer("Accra City Hotel", "Standard Double", 840.00, request.currency, 8.1),
            HotelOffer("Labadi Beach Hotel", "Garden View Room", 1450.00, request.currency, 8.6),
            HotelOffer("The Pelican Hotel", "Deluxe King", 1020.00, request.currency, 8.3),
        ]
