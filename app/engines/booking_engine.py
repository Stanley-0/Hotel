"""Booking boundary: real booking is intentionally not automated by this project."""

from app.models import HotelOffer


class BookingNotAvailableError(RuntimeError):
    pass


class BookingEngine:
    def create_booking(self, offer: HotelOffer) -> None:
        raise BookingNotAvailableError(
            "This starter does not automate bookings. Complete bookings only through an explicitly authorized provider flow."
        )
