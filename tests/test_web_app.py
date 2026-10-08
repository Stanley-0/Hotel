from datetime import date, timedelta

import web_app
from web_app import create_app


def make_search_payload() -> dict[str, object]:
    check_in = date.today() + timedelta(days=14)
    check_out = check_in + timedelta(days=3)
    return {
        "destination": "Accra, Ghana",
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
        "adults": 2,
        "children_ages": [],
        "rooms": 1,
        "currency": "GHS",
        "min_price": None,
        "max_price": None,
        "min_rating": None,
    }


def make_client():
    app = create_app(provider_name="mock")
    app.config.update(TESTING=True)
    return app.test_client()


def test_home_page_renders_the_hotel_search_form() -> None:
    response = make_client().get("/")

    assert response.status_code == 200
    assert b"Find your" in response.data
    assert b"check-in" in response.data
    assert b"accra-hotel-terrace.png" in response.data


def test_mock_search_results_page_and_excel_download_work_end_to_end() -> None:
    client = make_client()
    response = client.post("/api/search", json=make_search_payload())

    assert response.status_code == 200
    data = response.get_json()
    assert data["is_sample"] is True
    assert len(data["offers"]) == 3
    assert data["offers"][0]["total_price"] == 2520
    assert data["results_url"] == f"/results/{data['search_id']}"

    results = client.get(data["results_url"])
    assert results.status_code == 200
    assert results.headers["Cache-Control"] == "private, no-store"
    assert b"Your next stay" in results.data
    assert b"spreadsheet-table" in results.data
    assert b"results.js" in results.data
    assert f'data-search-id="{data["search_id"]}"'.encode() in results.data

    export = client.post(f"/api/search/{data['search_id']}/export", json=data)
    assert export.status_code == 200
    assert export.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert export.data.startswith(b"PK")


def test_search_rejects_checkout_before_checkin() -> None:
    payload = make_search_payload()
    payload["check_out"] = payload["check_in"]

    response = make_client().post("/api/search", json=payload)

    assert response.status_code == 400
    assert response.get_json()["error"] == "Check-out must be after check-in."


def test_search_forwards_children_ages_to_provider(monkeypatch) -> None:
    received: dict[str, object] = {}

    class CapturingProvider:
        name = "test-provider"

        def search_hotels(self, search_request):
            received["children"] = search_request.children
            return []

    def create_capturing_provider(config):
        received["children_ages"] = config.data["booking_parameters"]["children_ages"]
        return CapturingProvider()

    monkeypatch.setattr(web_app, "create_provider", create_capturing_provider)
    payload = make_search_payload()
    payload["children_ages"] = [4, 8]

    response = make_client().post("/api/search", json=payload)

    assert response.status_code == 200
    assert received == {"children": 2, "children_ages": [4, 8]}


def test_home_uses_configured_search_defaults(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """search:
  destination: 'Osu, Accra'
  check_in: '2030-03-11'
  check_out: '2030-03-15'
  adults: 3
  rooms: 2
  currency: USD
""",
        encoding="utf-8",
    )
    app = create_app(config_path=config_path, provider_name="mock")
    app.config.update(TESTING=True)

    response = app.test_client().get("/")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'value="Osu, Accra"' in page
    assert 'value="2030-03-11"' in page
    assert 'value="3"' in page
    assert '<option value="USD" selected>' in page


def test_results_route_rejects_invalid_search_ids() -> None:
    response = make_client().get("/results/not-a-valid-id")

    assert response.status_code == 404


def test_excel_export_rejects_mismatched_search_id() -> None:
    client = make_client()
    search = client.post("/api/search", json=make_search_payload()).get_json()
    payload = {**search, "search_id": "different-search-id-with-valid-length"}

    response = client.post(f"/api/search/{search['search_id']}/export", json=payload)

    assert response.status_code == 400
    assert response.get_json()["error"] == "These results do not match the requested export."
