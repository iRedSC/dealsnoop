

from dataclasses import dataclass


@dataclass
class SearchConfig:
    terms: list[str]
    city_code: str = '107976589222439'
    city: str = "Harrisburg, PA"
    target_price: str | None = None
    days_listed: int = 1
    radius: int = 30
    context: str | None = None
    webhook: str = "GOLF_CLUBS"