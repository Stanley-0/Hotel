"""Search orchestration."""

from app.models import HotelOffer, SearchRequest
from app.providers.base import HotelProvider


class HotelSearchEngine:
    def __init__(self, provider: HotelProvider) -> None:
        self.provider = provider

    def search(self, request: SearchRequest) -> list[HotelOffer]:
        return self.provider.search_hotels(request)
