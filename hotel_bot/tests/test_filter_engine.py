from app.engines.filter_engine import filter_offers
from app.models import HotelOffer


def test_filtering_by_price_and_rating() -> None:
    offers = [
        HotelOffer("A", "Room", 800, "GHS", 8.2),
        HotelOffer("B", "Room", 1200, "GHS", 8.8),
    ]

    assert filter_offers(offers, max_nightly_price=900, min_guest_rating=8.0) == [offers[0]]


def test_filtering_by_minimum_price() -> None:
    offers = [
        HotelOffer("A", "Room", 800, "GHS", 8.2),
        HotelOffer("B", "Room", 1200, "GHS", 8.8),
    ]

    assert filter_offers(offers, min_nightly_price=1000) == [offers[1]]
