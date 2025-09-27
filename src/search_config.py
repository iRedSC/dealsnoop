

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchConfig:
    id: int
    terms: tuple[str, ...]
    channel: int
    city_code: str = '107976589222439'
    city: str = "Harrisburg, PA"
    target_price: str | None = None
    days_listed: int = 1
    radius: int = 30
    context: str | None = None