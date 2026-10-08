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


def test_unrated_offer_is_kept_without_filter_and_excluded_by_minimum_rating() -> None:
    offer = HotelOffer("A", "Room", 800, "GHS", None)

    assert filter_offers([offer]) == [offer]
    assert filter_offers([offer], min_guest_rating=7.0) == []
