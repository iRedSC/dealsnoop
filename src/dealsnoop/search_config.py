"""Search configuration for marketplace watches."""

from dataclasses import dataclass


def build_watch_command(config: SearchConfig, channel_id: int) -> str:
    """Build the full /watch command string from a SearchConfig."""
    terms_escaped = [t.replace('"', '\\"') for t in config.terms]
    terms_str = ", ".join(terms_escaped)
    ctx_escaped = (config.context or "").replace('"', '\\"')
    parts = [
        f'terms:"{terms_str}"',
        f"channel_id:{channel_id}",
    ]
    if config.target_price:
        parts.append(f"target_price:{config.target_price}")
    if config.context:
        parts.append(f'context:"{ctx_escaped}"')
    parts.extend([
        f"city_code:{config.city_code}",
        f"days_listed:{config.days_listed}",
        f"radius:{config.radius}",
    ])
    return "/watch " + " ".join(parts)


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