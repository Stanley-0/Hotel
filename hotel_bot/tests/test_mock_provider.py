from app.models import SearchRequest
from app.providers.mock_provider import MockHotelProvider


def test_mock_provider_returns_accra_offers() -> None:
    request = SearchRequest.from_mapping(
        {"destination": "Accra, Ghana", "check_in": "2026-12-10", "check_out": "2026-12-15"}
    )
    offers = MockHotelProvider().search_hotels(request)

    assert len(offers) == 3
    assert offers[0].hotel_name == "Accra City Hotel"
