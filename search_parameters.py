"""Hotel-search settings you can adjust before running ``py main.py``.

All prices are per night and use the currency set below. Leave ``children_ages``
empty when no children are travelling.
"""

SEARCH_PARAMETERS = {
    "destination": "accra",
    "check_in": "2026-12-10",  # YYYY-MM-DD
    "check_out": "2026-12-15",  # YYYY-MM-DD
    "adults": 2,
    # Add each child's age, for example [4, 9]. Leave [] when no children travel.
    "children_ages": [],
    "rooms": 1,
    "currency": "GHS",
    "min_price": None,  # e.g. 500; use None for no minimum
    "max_price": None,  # e.g. 1500; use None for no maximum
    "min_rating": None,  # e.g. 8.0; use None for no minimum
    "booker_country": "gh",  # ISO 3166-1 alpha-2 country code
    "output_excel": "hotel_results.xlsx",
    # Keep False for the recommended visible local browser mode.
    "headless": False,
}
