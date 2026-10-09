import asyncio
from io import BytesIO

from httpx import ASGITransport, AsyncClient
from openpyxl import load_workbook

import app.web as web
from app.models import HotelOffer


def request(method: str, path: str, *, json: dict | None = None):
    async def send():
        async with AsyncClient(
            transport=ASGITransport(app=web.app),
            base_url="http://test",
        ) as client:
            return await client.request(method, path, json=json)

    return asyncio.run(send())


def test_search_returns_filtered_offers_and_downloads_the_same_results(monkeypatch) -> None:
    def mock_provider(config):
        assert config.data["provider"]["name"] == "booking_com_selenium"
        assert config.data["booking_parameters"]["headless"] is True
        assert config.data["booking_parameters"]["children_ages"] == [6]

        class ResultProvider:
            def search_hotels(self, _request):
                return [
                    HotelOffer(
                        "Accra City Hotel",
                        "Standard Double",
                        840.00,
                        "GHS",
                        8.1,
                        address="Barnes Road, Accra",
                        latitude=5.5557,
                        longitude=-0.2058,
                    )
                ]

        return ResultProvider()

    monkeypatch.setattr(web, "create_provider", mock_provider)
    response = request(
        "POST",
        "/api/search",
        json={
            "destination": "Accra, Ghana",
            "check_in": "2026-12-10",
            "check_out": "2026-12-15",
            "adults": 2,
            "children_ages": [6],
            "rooms": 1,
            "currency": "GHS",
            "min_price": 800,
            "max_price": 1000,
            "min_rating": 8,
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["count"] == 1
    assert result["nights"] == 5
    assert result["offers"][0]["hotel_name"] == "Accra City Hotel"
    assert result["offers"][0]["total_price"] == 4200
    assert result["offers"][0]["nightly_price"] == 840
    assert result["offers"][0]["latitude"] == 5.5557
    assert result["offers"][0]["longitude"] == -0.2058

    export = request("GET", f"/api/searches/{result['search_id']}/export")
    assert export.status_code == 200
    workbook = load_workbook(BytesIO(export.content), data_only=True)
    assert workbook["Hotel offers"]["A2"].value == "Accra City Hotel"
    assert workbook["Hotel offers"]["C2"].value == 4200


def test_search_rejects_checkout_before_checkin() -> None:
    response = request(
        "POST",
        "/api/search",
        json={
            "destination": "Accra",
            "check_in": "2026-12-15",
            "check_out": "2026-12-10",
        },
    )

    assert response.status_code == 422
    assert "Check-out must be after check-in." in response.text


def test_search_rejects_blank_destination() -> None:
    response = request(
        "POST",
        "/api/search",
        json={
            "destination": "  ",
            "check_in": "2026-12-10",
            "check_out": "2026-12-15",
        },
    )

    assert response.status_code == 422
    assert "at least two characters" in response.text


def test_export_rejects_unknown_search_id() -> None:
    response = request("GET", "/api/searches/not-a-search/export")

    assert response.status_code == 404
