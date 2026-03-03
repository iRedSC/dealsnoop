"""Per-user marketplace location settings."""

from dataclasses import dataclass


@dataclass(frozen=True)
class UserLocation:
    user_id: int
    city_code: str
