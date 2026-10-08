from types import SimpleNamespace

import app.providers.booking_com_selenium_provider as selenium_provider
from app.models import SearchRequest
from app.providers.booking_com_selenium_provider import BookingComSeleniumProvider
from selenium.common.exceptions import StaleElementReferenceException


def test_search_url_reflects_guest_and_date_parameters() -> None:
    provider = BookingComSeleniumProvider(children_ages=[4, 8])
    request = SearchRequest.from_mapping({
        "destination": "Accra, Ghana", "check_in": "2026-12-10", "check_out": "2026-12-15",
        "adults": 2, "children_ages": [4, 8], "rooms": 1, "currency": "GHS",
    })

    url = provider.build_search_url(request)

    assert "ss=Accra%2C+Ghana" in url
    assert "checkin=2026-12-10" in url
    assert "group_adults=2" in url
    assert "group_children=2" in url
    assert "age=4&age=8" in url
    assert "no_rooms=1" in url


def test_search_returns_all_result_cards_and_converts_total_to_nightly(monkeypatch) -> None:
    request = SearchRequest.from_mapping({
        "destination": "Kyoto",
        "check_in": "2026-12-10",
        "check_out": "2026-12-15",
    })
    cards = [
        FakeCard(f"Hotel {number}", "GHS 1,000")
        for number in range(12)
    ]
    driver = FakeDriver()

    class FakeWait:
        def __init__(self, _driver, _timeout: int) -> None:
            pass

        def until(self, _condition):
            return cards

    provider = BookingComSeleniumProvider()
    monkeypatch.setattr(provider, "_create_driver", lambda: driver)
    monkeypatch.setattr(selenium_provider, "WebDriverWait", FakeWait)

    offers = provider.search_hotels(request)

    assert len(offers) == 12
    assert offers[0].hotel_name == "Hotel 0"
    assert offers[0].nightly_price == 200
    assert offers[0].guest_rating == 8.6
    assert offers[0].address == "1 River Road"
    assert offers[0].latitude == 35.0116
    assert offers[0].longitude == 135.7681
    assert driver.closed


def test_search_retries_when_result_cards_go_stale(monkeypatch) -> None:
    request = SearchRequest.from_mapping({
        "destination": "Kyoto",
        "check_in": "2026-12-10",
        "check_out": "2026-12-15",
    })
    cards = [FakeCard("Hotel 1", "GHS 1,000", stale_once=True)]
    driver = FakeDriver()
    wait_count = 0

    class FakeWait:
        def __init__(self, _driver, _timeout: int) -> None:
            pass

        def until(self, _condition):
            nonlocal wait_count
            wait_count += 1
            return cards

    provider = BookingComSeleniumProvider()
    monkeypatch.setattr(provider, "_create_driver", lambda: driver)
    monkeypatch.setattr(selenium_provider, "WebDriverWait", FakeWait)

    offers = provider.search_hotels(request)

    assert len(offers) == 1
    assert wait_count == 2
    assert driver.closed


class FakeDriver:
    page_source = "<html>hotel search results</html>"

    def __init__(self) -> None:
        self.closed = False

    def set_page_load_timeout(self, _timeout: int) -> None:
        pass

    def get(self, _url: str) -> None:
        pass

    def quit(self) -> None:
        self.closed = True


class FakeCard:
    def __init__(self, hotel_name: str, price: str, *, stale_once: bool = False) -> None:
        self.hotel_name = hotel_name
        self.price = price
        self.stale_once = stale_once

    def find_elements(self, _by: str, selector: str) -> list[SimpleNamespace]:
        if self.stale_once:
            self.stale_once = False
            raise StaleElementReferenceException("test stale card")
        if selector == '[data-testid="title"]':
            return [SimpleNamespace(text=self.hotel_name)]
        if selector == '[data-testid="price-and-discounted-price"]':
            return [SimpleNamespace(text=self.price)]
        if selector == '[data-testid="review-score"]':
            return [SimpleNamespace(text="Scored 8.6")]
        if selector == '[data-testid="address"]':
            return [SimpleNamespace(text="1 River Road")]
        if selector == '[data-testid="map-trigger"], a[href*="lat"], a[href*="lon"]':
            return [
                FakeMapElement(
                    {
                        "data-atlas-latlng": "35.0116,135.7681",
                        "href": "https://example.com/map",
                    }
                )
            ]
        return []


class FakeMapElement:
    def __init__(self, attributes: dict[str, str]) -> None:
        self.attributes = attributes

    def get_attribute(self, name: str) -> str | None:
        return self.attributes.get(name)
