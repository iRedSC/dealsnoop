"""Search configuration for marketplace watches."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchConfig:
    id: str
    terms: tuple[str, ...]
    channel: int
    city_code: str = '107976589222439'
    location_name: str | None = None
    target_price: str | None = None
    days_listed: int = 1
    radius: int = 30
    context: str | None = None