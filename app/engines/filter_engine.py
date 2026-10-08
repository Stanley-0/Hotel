"""Provider-independent offer filtering."""

from app.models import HotelOffer


def filter_offers(
    offers: list[HotelOffer], *, min_nightly_price: float | None = None,
    max_nightly_price: float | None = None, min_guest_rating: float | None = None
) -> list[HotelOffer]:
    return [
        offer for offer in offers
        if (min_nightly_price is None or offer.nightly_price >= min_nightly_price)
        and (max_nightly_price is None or offer.nightly_price <= max_nightly_price)
        and (min_guest_rating is None or offer.guest_rating >= min_guest_rating)
    ]
