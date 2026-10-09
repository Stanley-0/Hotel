from app.models import SearchRequest
from app.providers.booking_com_provider import BookingComProvider


def test_booking_payload_includes_all_search_parameters() -> None:
    provider = BookingComProvider(
        integration_base_url="https://example.test/3.2",
        api_key_env="UNUSED_KEY",
        affiliate_id_env="UNUSED_AFFILIATE",
        booker_country="GH",
        children_ages=[5, 9],
        min_price=100,
        max_price=300,
        min_rating=8.5,
        max_results=20,
    )
    request = SearchRequest.from_mapping({
        "destination": "Accra, Ghana", "check_in": "2026-12-10", "check_out": "2026-12-15",
        "adults": 2, "children_ages": [5, 9], "rooms": 1, "currency": "GHS",
    })

    payload = provider._build_payload(request)

    assert payload["search_query"] == "Accra, Ghana"
    assert payload["guests"] == {"number_of_adults": 2, "number_of_rooms": 1, "children": [5, 9]}
    assert payload["filters"] == {"price": {"minimum": 100, "maximum": 300}, "rating": {"minimum_review_score": 8.5}}


def test_booking_offer_converts_total_stay_price_to_nightly_price() -> None:
    offer = BookingComProvider._to_offer(
        {
            "name": "Example Hotel",
            "price": {"total": {"booker_currency": 1000}},
            "currency": {"booker": "GHS"},
            "location": {
                "address": "1 River Road",
                "coordinates": {"latitude": 5.6037, "longitude": -0.187},
            },
            "review_score": 8.4,
        },
        "GHS",
        5,
    )

    assert offer.nightly_price == 200
    assert offer.guest_rating == 8.4
    assert offer.address == "1 River Road"
    assert offer.latitude == 5.6037
    assert offer.longitude == -0.187
