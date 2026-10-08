"""Construct the configured provider."""

from app.config import Config
from app.providers.booking_com_provider import BookingComProvider
from app.providers.booking_com_selenium_provider import BookingComSeleniumProvider
from app.providers.mock_provider import MockHotelProvider


def create_provider(config: Config):
    provider_name = config.get("provider", "name", "mock")
    if provider_name == "mock":
        return MockHotelProvider()
    if provider_name == "booking_com":
        details = config.get("provider", "booking_com", {})
        parameters = config.get("booking_parameters", default={})
        return BookingComProvider(
            integration_base_url=details.get("integration_base_url"),
            api_key_env=details.get("api_key_env", "BOOKING_COM_API_KEY"),
            affiliate_id_env=details.get("affiliate_id_env", "BOOKING_COM_AFFILIATE_ID"),
            booker_country=parameters.get("booker_country", "gh"),
            children_ages=parameters.get("children_ages", []),
            min_price=parameters.get("min_price"),
            max_price=parameters.get("max_price"),
            min_rating=parameters.get("min_rating"),
            max_results=parameters.get("max_results", 10),
        )
    if provider_name == "booking_com_selenium":
        parameters = config.get("booking_parameters", default={})
        return BookingComSeleniumProvider(
            children_ages=parameters.get("children_ages", []),
            headless=parameters.get("headless", False),
        )
    raise ValueError(f"Unsupported provider: {provider_name}")
