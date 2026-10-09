from datetime import date, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

import server
from scraper import Accommodation, SearchQuery, build_search_url, parse_price, parse_rating


def make_query(**overrides) -> SearchQuery:
    start = date.today() + timedelta(days=10)
    values = dict(
        location="Accra",
        adults=2,
        check_in=start,
        check_out=start + timedelta(days=3),
        rooms=1,
        currency="USD",
    )
    values.update(overrides)
    return SearchQuery(**values)


def test_search_url_contains_every_parameter():
    query = make_query(adults=4, rooms=2, currency="GHS")
    params = parse_qs(urlsplit(build_search_url(query)).query)
    assert params["ss"] == ["Accra"]
    assert params["group_adults"] == ["4"]
    assert params["no_rooms"] == ["2"]
    assert params["selected_currency"] == ["GHS"]
    assert params["checkin"] == [query.check_in.isoformat()]
    assert params["checkout"] == [query.check_out.isoformat()]


@pytest.mark.parametrize(
    "text, expected",
    [("US$1,234", 1234.0), ("GHS 2,100 GHS 1,850", 1850.0), ("€ 99.50", 99.5), ("", None)],
)
def test_parse_price(text, expected):
    assert parse_price(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [("Scored 8.4\n8.4\nVery good\n1,203 reviews", 8.4), ("9,1 Superb", 9.1), ("New to Booking", None)],
)
def test_parse_rating(text, expected):
    assert parse_rating(text) == expected


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"location": " "}, "location"),
        ({"rooms": 3, "adults": 2}, "per room"),
        ({"check_in": date.today() - timedelta(days=1)}, "past"),
        ({"currency": "XYZ"}, "currency"),
    ],
)
def test_query_validation(overrides, message):
    with pytest.raises(ValueError, match=message):
        make_query(**overrides).validate()


@pytest.fixture
def client():
    server.app.config.update(TESTING=True)
    return server.app.test_client()


def test_index_renders_form(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="search-form"' in html
    assert 'value="GHS"' in html


def test_search_returns_results(client, monkeypatch):
    def fake_scrape(query, **_):
        return [Accommodation("Labadi Beach Hotel", 8.6, 150.0, 450.0, "https://www.booking.com/x")]

    monkeypatch.setattr(server, "scrape_booking", fake_scrape)
    q = make_query()
    response = client.post(
        "/api/search",
        json={
            "location": "Accra",
            "adults": 2,
            "rooms": 1,
            "check_in": q.check_in.isoformat(),
            "check_out": q.check_out.isoformat(),
            "currency": "usd",
        },
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["query"]["nights"] == 3
    assert body["query"]["currency"] == "USD"
    assert body["results"][0]["total_price"] == 450.0


def test_search_rejects_bad_input(client):
    response = client.post("/api/search", json={"location": "Accra", "adults": "two"})
    assert response.status_code == 400
    assert "whole number" in response.get_json()["error"]
