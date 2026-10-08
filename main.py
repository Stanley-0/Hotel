from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from selenium.common.exceptions import WebDriverException
from urllib3.exceptions import HTTPError

from app.config import Config
from app.engines.filter_engine import filter_offers
from app.engines.search_engine import HotelSearchEngine
from app.logging_config import configure_logging
from app.models import SearchRequest
from app.services.excel_exporter import export_offers_to_excel
from app.services.provider_factory import create_provider
from search_parameters import SEARCH_PARAMETERS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search hotel offers through an authorized provider.")
    parser.add_argument("--config", default="config.yaml", help="Path to a YAML configuration file.")
    parser.add_argument("--destination", help="Override the configured destination.")
    parser.add_argument("--min-price", type=float, help="Show only offers at or above this nightly price.")
    parser.add_argument("--max-price", type=float, help="Show only offers at or below this nightly price.")
    parser.add_argument("--min-rating", type=float, help="Show only offers with at least this guest rating.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Excel report path (default: hotel_results.xlsx).",
    )
    parser.add_argument(
        "--no-open-results",
        action="store_true",
        help="Save the Excel report without opening it.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = Config(Path(args.config))
    configure_logging()
    logger = logging.getLogger(__name__)

    search_settings = {**(config.get("search") or {}), **SEARCH_PARAMETERS}
    request = SearchRequest.from_mapping(search_settings, destination=args.destination)
    config.data["booking_parameters"] = search_settings
    provider = create_provider(config)
    engine = HotelSearchEngine(provider)

    logger.info("Searching hotels in %s using %s", request.destination, provider.name)
    search_error = None
    try:
        offers = engine.search(request)
    except (RuntimeError, WebDriverException, HTTPError) as error:
        logger.error("%s", error)
        search_error = str(error)
        offers = []
    if search_error:
        print(f"Search failed; no Excel report was changed. {search_error}")
        return 2

    offers = filter_offers(
        offers,
        min_nightly_price=args.min_price if args.min_price is not None else search_settings.get("min_price"),
        max_nightly_price=args.max_price if args.max_price is not None else search_settings.get("max_price"),
        min_guest_rating=args.min_rating if args.min_rating is not None else search_settings.get("min_rating"),
    )

    output_path = args.output or Path(
        str(search_settings.get("output_excel") or "hotel_results.xlsx")
    )
    try:
        export_offers_to_excel(
            offers,
            request,
            output_path,
        )
    except (OSError, ValueError) as error:
        logger.error("Could not write Excel report to %s: %s", output_path, error)
        return 3

    output_path = output_path.resolve()
    if not args.no_open_results:
        try:
            os.startfile(str(output_path))
        except OSError as error:
            logger.warning("Excel report was saved but could not be opened: %s", error)

    if not offers:
        if search_error:
            print(f"Search failed. Details saved to {output_path}.")
            return 2
        print(f"No matching offers found. Search report saved to {output_path}.")
        return 0

    print(f"Found {len(offers)} offer(s) for {request.destination}:")
    for offer in offers:
        print(
            f"- {offer.hotel_name}: {offer.currency} {offer.nightly_price:.2f}/night "
            f"| rating {offer.guest_rating:.1f} | {offer.room_name}"
        )
        if offer.deep_link:
            print(f"  Details: {offer.deep_link}")
    print(f"Excel report saved to {output_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
