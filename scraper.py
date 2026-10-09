"""Selenium bot that reads public Booking.com search results.

It does not sign in, book anything, or try to get around CAPTCHAs. If
Booking.com asks for human verification the search stops with an error.

Run it from the terminal:

    python scraper.py --location "Accra" --adults 2 --check-in 2026-11-01 \
        --check-out 2026-11-04 --rooms 1 --currency USD
"""

from __future__ import annotations

import argparse
import re
import time
from dataclasses import asdict, dataclass
from datetime import date
from urllib.parse import urlencode

CURRENCIES: dict[str, str] = {
    "USD": "US dollar",
    "EUR": "Euro",
    "GBP": "British pound",
    "GHS": "Ghanaian cedi",
    "NGN": "Nigerian naira",
    "KES": "Kenyan shilling",
    "ZAR": "South African rand",
    "CAD": "Canadian dollar",
    "AUD": "Australian dollar",
    "AED": "UAE dirham",
    "INR": "Indian rupee",
    "JPY": "Japanese yen",
}

MAX_GUESTS = 30
MAX_ROOMS = 30
MAX_NIGHTS = 90
DEFAULT_MAX_RESULTS = 50

CARD_SELECTOR = '[data-testid="property-card"]'
VERIFICATION_MARKERS = ("captcha", "verify you are human", "unusual traffic", "security check")


class ScrapeError(RuntimeError):
    """Raised when Booking.com results could not be read."""


@dataclass(frozen=True)
class SearchQuery:
    location: str
    adults: int
    check_in: date
    check_out: date
    rooms: int
    currency: str

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days

    def validate(self, today: date | None = None) -> None:
        today = today or date.today()
        if not self.location.strip():
            raise ValueError("Enter a location.")
        if len(self.location) > 120:
            raise ValueError("Location must be 120 characters or fewer.")
        if not 1 <= self.adults <= MAX_GUESTS:
            raise ValueError(f"Number of people must be between 1 and {MAX_GUESTS}.")
        if not 1 <= self.rooms <= MAX_ROOMS:
            raise ValueError(f"Number of rooms must be between 1 and {MAX_ROOMS}.")
        if self.rooms > self.adults:
            raise ValueError("You need at least one person per room.")
        if self.check_in < today:
            raise ValueError("Check-in date can't be in the past.")
        if self.nights < 1:
            raise ValueError("Check-out must be after check-in.")
        if self.nights > MAX_NIGHTS:
            raise ValueError(f"Stays are limited to {MAX_NIGHTS} nights.")
        if self.currency not in CURRENCIES:
            raise ValueError("Choose a supported currency.")


@dataclass(frozen=True)
class Accommodation:
    name: str
    rating: float | None
    price_per_night: float
    total_price: float
    url: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def build_search_url(query: SearchQuery) -> str:
    params = {
        "ss": query.location.strip(),
        "checkin": query.check_in.isoformat(),
        "checkout": query.check_out.isoformat(),
        "group_adults": query.adults,
        "group_children": 0,
        "no_rooms": query.rooms,
        "selected_currency": query.currency,
        "lang": "en-us",
    }
    return "https://www.booking.com/searchresults.html?" + urlencode(params)


def parse_price(text: str) -> float | None:
    """Return the last number in a price label, e.g. 'US$1,234' -> 1234.0.

    Discounted cards show the old price first, so the last number is the price
    the guest actually pays.
    """
    matches = re.findall(r"\d[\d,]*(?:\.\d+)?", text.replace("\u00a0", " "))
    if not matches:
        return None
    return float(matches[-1].replace(",", ""))


def parse_rating(text: str) -> float | None:
    """Return the review score out of 10, e.g. 'Scored 8.4 Very good' -> 8.4."""
    for match in re.findall(r"\d+(?:[.,]\d+)?", text):
        value = float(match.replace(",", "."))
        if 0 <= value <= 10:
            return value
    return None


def _create_driver(headless: bool):
    from selenium import webdriver

    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1366,900")
    options.add_argument("--disable-notifications")
    options.add_argument("--lang=en-US")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)


def _dismiss_cookie_banner(driver) -> None:
    from selenium.webdriver.common.by import By

    for button in driver.find_elements(By.ID, "onetrust-accept-btn-handler"):
        try:
            button.click()
        except Exception:
            pass


def _check_for_verification(driver) -> None:
    page = driver.page_source.lower()
    if any(marker in page for marker in VERIFICATION_MARKERS):
        raise ScrapeError(
            "Booking.com asked for human verification. Open booking.com in a normal "
            "browser, complete the check, then try again."
        )


def _load_more_cards(driver, max_results: int) -> None:
    """Scroll so lazy-loaded cards render, clicking 'Load more' when it appears."""
    from selenium.webdriver.common.by import By

    for _ in range(6):
        if len(driver.find_elements(By.CSS_SELECTOR, CARD_SELECTOR)) >= max_results:
            return
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.2)
        for button in driver.find_elements(By.XPATH, "//button[.//span[contains(., 'Load more results')]]"):
            try:
                button.click()
                time.sleep(1.5)
            except Exception:
                pass


def _parse_card(card, nights: int) -> Accommodation | None:
    from selenium.webdriver.common.by import By

    def text(selector: str) -> str:
        found = card.find_elements(By.CSS_SELECTOR, selector)
        return found[0].text.strip() if found else ""

    name = text('[data-testid="title"]')
    total = parse_price(text('[data-testid="price-and-discounted-price"]'))
    if not name or total is None:
        return None

    links = card.find_elements(By.CSS_SELECTOR, 'a[data-testid="title-link"]')
    url = links[0].get_attribute("href") if links else None

    return Accommodation(
        name=name,
        rating=parse_rating(text('[data-testid="review-score"]')),
        price_per_night=round(total / nights, 2),
        total_price=round(total, 2),
        url=url,
    )


def scrape_booking(
    query: SearchQuery,
    *,
    headless: bool = True,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> list[Accommodation]:
    """Open Booking.com in Chrome and return the accommodations it lists."""
    from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    query.validate()
    driver = _create_driver(headless)
    try:
        driver.set_page_load_timeout(40)
        driver.get(build_search_url(query))
        _dismiss_cookie_banner(driver)
        _check_for_verification(driver)

        try:
            WebDriverWait(driver, 25).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, CARD_SELECTOR))
            )
        except TimeoutException as error:
            _check_for_verification(driver)
            raise ScrapeError(
                "No results loaded from Booking.com. Check the location and dates, then try again."
            ) from error

        _load_more_cards(driver, max_results)

        for _ in range(3):
            try:
                cards = driver.find_elements(By.CSS_SELECTOR, CARD_SELECTOR)[:max_results]
                results = [_parse_card(card, query.nights) for card in cards]
                return [item for item in results if item is not None]
            except StaleElementReferenceException:
                time.sleep(1)
        raise ScrapeError("Results kept changing while being read. Please try again.")
    finally:
        driver.quit()


def _print_table(results: list[Accommodation], currency: str) -> None:
    if not results:
        print("No accommodations found.")
        return
    width = min(max(len(r.name) for r in results), 50)
    header = f"{'Accommodation':<{width}}  {'Rating':>6}  {'Per night':>12}  {'Total stay':>12}"
    print(header)
    print("-" * len(header))
    for r in results:
        rating = f"{r.rating:.1f}" if r.rating is not None else "-"
        print(
            f"{r.name[:width]:<{width}}  {rating:>6}  "
            f"{r.price_per_night:>12,.2f}  {r.total_price:>12,.2f}"
        )
    print(f"\n{len(results)} results, prices in {currency}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Booking.com accommodation listings.")
    parser.add_argument("--location", required=True)
    parser.add_argument("--adults", type=int, default=2, help="Number of people staying")
    parser.add_argument("--check-in", type=date.fromisoformat, required=True, help="YYYY-MM-DD")
    parser.add_argument("--check-out", type=date.fromisoformat, required=True, help="YYYY-MM-DD")
    parser.add_argument("--rooms", type=int, default=1)
    parser.add_argument("--currency", default="USD", choices=sorted(CURRENCIES))
    parser.add_argument("--max-results", type=int, default=DEFAULT_MAX_RESULTS)
    parser.add_argument("--show-browser", action="store_true", help="Run Chrome visibly")
    args = parser.parse_args()

    query = SearchQuery(
        location=args.location,
        adults=args.adults,
        check_in=args.check_in,
        check_out=args.check_out,
        rooms=args.rooms,
        currency=args.currency,
    )
    try:
        query.validate()
        results = scrape_booking(query, headless=not args.show_browser, max_results=args.max_results)
    except (ValueError, ScrapeError) as error:
        parser.exit(1, f"Error: {error}\n")
    _print_table(results, query.currency)


if __name__ == "__main__":
    main()
