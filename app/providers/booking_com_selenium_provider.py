"""Local, visible Selenium search for Booking.com public result pages.

This provider does not sign in, make bookings, or attempt to evade CAPTCHAs and
other access controls. If Booking.com asks for human verification, it stops.
"""

from __future__ import annotations

import re
from typing import Final
from urllib.parse import urlencode

from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as conditions
from selenium.webdriver.support.ui import WebDriverWait

from app.models import HotelOffer, SearchRequest


class BookingComSeleniumProvider:
    name: Final[str] = "booking_com_selenium"

    def __init__(self, *, children_ages: list[int] | None = None, headless: bool = False) -> None:
        self.children_ages = children_ages or []
        self.headless = headless

    def build_search_url(self, request: SearchRequest) -> str:
        query = {
            "ss": request.destination,
            "checkin": request.check_in.isoformat(),
            "checkout": request.check_out.isoformat(),
            "group_adults": request.adults,
            "group_children": len(self.children_ages),
            "no_rooms": request.rooms,
            "selected_currency": request.currency,
        }
        return "https://www.booking.com/searchresults.html?" + urlencode(query)

    def search_hotels(self, request: SearchRequest) -> list[HotelOffer]:
        driver = self._create_driver()
        try:
            driver.set_page_load_timeout(30)
            driver.get(self.build_search_url(request))
            self._raise_if_human_verification(driver)
            nights = (request.check_out - request.check_in).days
            last_stale_error = None
            for _ in range(3):
                cards = WebDriverWait(driver, 20).until(
                    conditions.presence_of_all_elements_located(
                        (By.CSS_SELECTOR, '[data-testid="property-card"]')
                    )
                )
                try:
                    offers = [
                        self._parse_card(card, request.currency, nights)
                        for card in cards
                    ]
                except StaleElementReferenceException as error:
                    last_stale_error = error
                    continue
                return [offer for offer in offers if offer is not None]
            raise RuntimeError(
                "Hotel results kept changing while they were being read. Retry the search."
            ) from last_stale_error
        except TimeoutException as error:
            self._raise_if_human_verification(driver)
            raise RuntimeError("Booking.com results did not load within 20 seconds. Try again in the visible browser.") from error
        finally:
            driver.quit()

    def _create_driver(self) -> webdriver.Chrome:
        options = webdriver.ChromeOptions()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-notifications")
        options.add_argument("--start-maximized")
        return webdriver.Chrome(options=options)

    @staticmethod
    def _raise_if_human_verification(driver: webdriver.Chrome) -> None:
        page_text = driver.page_source.lower()
        markers = ("captcha", "verify you are human", "unusual traffic", "security check")
        if any(marker in page_text for marker in markers):
            raise RuntimeError(
                "Booking.com requested human verification. Complete it manually in a normal browser, then retry; "
                "this program does not bypass CAPTCHAs or access controls."
            )

    @staticmethod
    def _parse_card(card, currency: str, nights: int) -> HotelOffer | None:
        def text(selector: str) -> str:
            matches = card.find_elements(By.CSS_SELECTOR, selector)
            return matches[0].text.strip() if matches else ""

        hotel_name = text('[data-testid="title"]')
        price_text = text('[data-testid="price-and-discounted-price"]')
        if not hotel_name or not price_text:
            return None
        price_matches = re.findall(r"\d[\d,]*(?:\.\d+)?", price_text.replace(" ", ""))
        if not price_matches:
            return None
        score_text = text('[data-testid="review-score"]')
        score_match = re.search(r"\d+(?:\.\d+)?", score_text.replace(",", "."))
        links = card.find_elements(By.CSS_SELECTOR, 'a[data-testid="title-link"]')
        deep_link = links[0].get_attribute("href") if links else None
        address = text('[data-testid="address"]') or None
        latitude, longitude = BookingComSeleniumProvider._coordinates_from_card(card)
        return HotelOffer(
            hotel_name=hotel_name,
            room_name="Best available room",
            nightly_price=round(float(price_matches[-1].replace(",", "")) / nights, 2),
            currency=currency,
            guest_rating=float(score_match.group()) if score_match else 0.0,
            deep_link=deep_link,
            address=address,
            latitude=latitude,
            longitude=longitude,
        )

    @staticmethod
    def _coordinates_from_card(card) -> tuple[float | None, float | None]:
        map_elements = card.find_elements(
            By.CSS_SELECTOR,
            '[data-testid="map-trigger"], a[href*="lat"], a[href*="lon"]',
        )
        for element in map_elements:
            atlas_coordinates = element.get_attribute("data-atlas-latlng")
            if atlas_coordinates:
                match = re.search(
                    r"(-?\d+(?:\.\d+)?)\s*[,/]\s*(-?\d+(?:\.\d+)?)",
                    atlas_coordinates,
                )
                if match:
                    return float(match.group(1)), float(match.group(2))

            latitude = element.get_attribute("data-latitude")
            longitude = element.get_attribute("data-longitude")
            if latitude is not None and longitude is not None:
                return float(latitude), float(longitude)

            href = element.get_attribute("href") or ""
            match = re.search(
                r"(?:@|lat=)(-?\d+(?:\.\d+)?)[,/](?:lon=)?(-?\d+(?:\.\d+)?)",
                href,
            )
            if match:
                return float(match.group(1)), float(match.group(2))
        return None, None
