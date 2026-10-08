from datetime import date, timedelta

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


def test_mock_search_and_excel_download_work_end_to_end() -> None:
    client = make_client()
    response = client.post("/api/search", json=make_search_payload())

    assert response.status_code == 200
    data = response.get_json()
    assert data["is_sample"] is True
    assert len(data["offers"]) == 3
    assert data["offers"][0]["total_price"] == 2520

    results = client.get(f"/results/{data['search_id']}")
    assert results.status_code == 200
    assert b"3 stays found" in results.data
    assert b"Sample results from the local demo provider" in results.data

    export = client.get(f"/api/search/{data['search_id']}/export")
    assert export.status_code == 200
    assert export.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert export.data.startswith(b"PK")


def test_search_rejects_checkout_before_checkin() -> None:
    payload = make_search_payload()
    payload["check_out"] = payload["check_in"]

    response = make_client().post("/api/search", json=payload)

    assert response.status_code == 400
    assert response.get_json()["error"] == "Check-out must be after check-in."
