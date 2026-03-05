"""Discord embed builders for products and search configs."""

from datetime import datetime
from typing import Sequence

import discord  # pyright: ignore[reportMissingImports]

from dealsnoop.listing_log import ListingLog
from dealsnoop.product import Product
from dealsnoop.search_config import SearchConfig

DESCRIPTION_TRUNCATE_LINES = 3
DESCRIPTION_TRUNCATE_CHARS = 300

# Components V2 accent colors (Container border)
ACCENT_PRODUCT = 0x03B2F8
ACCENT_KEPT = 0x00FF00
ACCENT_SKIPPED = 0xFFA500

# Discord limits
TEXT_DISPLAY_LIMIT = 4000
FIELD_NAME_LIMIT = 256
FIELD_VALUE_LIMIT = 1024
FIELD_REASON_LIMIT = 4096


def truncate_description(
    description: str,
    max_lines: int = DESCRIPTION_TRUNCATE_LINES,
    max_chars: int = DESCRIPTION_TRUNCATE_CHARS,
) -> str:
    """Truncate to max_lines and/or max_chars, append '...' if truncated."""
    text = description.strip()
    lines = text.splitlines()
    truncated = False

    if len(lines) > max_lines:
        truncated = True
        text = "\n".join(lines[:max_lines]).rstrip()

    if len(text) > max_chars:
        truncated = True
        text = text[: max_chars - 3].rstrip() + "..."

    if truncated and not text.endswith("..."):
        text = text.rstrip() + "\n..."
    return text


def product_embed(
    product: Product,
    distance: float | None,
    duration: str | None,
    description: str | None = None,
) -> discord.Embed:
    """Build product embed. Pass description to override (e.g. truncated)."""
    desc = description if description is not None else product.description
    embed = discord.Embed(
        title=product.title,
        url=product.url,
        description=f"**${product.price}**\n\n{desc}",
        color=ACCENT_PRODUCT,
    )
    embed.set_author(name=f"{product.date}", url=product.url, icon_url="https://cdn-1.webcatalog.io/catalog/facebook-marketplace/facebook-marketplace-icon-filled-256.png?v=1714774315353")

    embed.set_thumbnail(url=product.img)
    if distance and duration:
        embed.set_footer(text=f"{product.location} — {round(distance)} mi ({duration})", icon_url="https://cdn-icons-png.flaticon.com/512/1076/1076983.png")
    return embed


LISTING_DESC_PREFIX = "listing_desc:"
THUMBSDOWN_PREFIX = "thumbsdown:"


def _truncate_content(content: str, limit: int = TEXT_DISPLAY_LIMIT) -> str:
    """Truncate content to Discord TextDisplay limit."""
    if len(content) <= limit:
        return content
    return content[: limit - 3] + "..."


def _format_highlights(highlights: str | None) -> str:
    """Normalize highlights for display (single line)."""
    if not highlights:
        return ""
    text = highlights.strip()
    if not text:
        return ""
    # Keep as single line: collapse newlines to · separators
    return " · ".join(s.strip() for s in text.replace("\n", " · ").split(" · ") if s.strip())


def _product_content(
    product: Product,
    distance: float | None,
    duration: str | None,
    description: str | None,
    strengths_summary: str | None = None,
) -> tuple[str, str]:
    """Build markdown content for product display. Returns (main_content, footer_content)."""
    desc = description if description is not None else product.description
    formatted = _format_highlights(strengths_summary)
    strengths_block = f"-# {formatted}\n\n" if formatted else ""
    main = f"### [{product.title}]({product.url})\n\n**${product.price}**\n\n{strengths_block}{desc}"
    parts = [product.date]
    if product.location:
        parts.append(product.location)
    if distance is not None and duration:
        parts.append(f"{round(distance)} mi ({duration})")
    footer = f"-# {' · '.join(parts)}"
    return (main, footer)


def product_layout_view(
    product: Product,
    distance: float | None,
    duration: str | None,
    description: str | None,
    listing_id: str,
    expanded: bool,
    strengths_summary: str | None = None,
) -> discord.ui.LayoutView:
    """Build Components V2 LayoutView for a product. Thumbnail image, Show more button below description, then date/location."""
    main, footer = _product_content(
        product, distance, duration, description, strengths_summary=strengths_summary
    )
    main_content = _truncate_content(main)
    footer_content = _truncate_content(footer)

    expanded_int = 1 if expanded else 0
    custom_id = f"{LISTING_DESC_PREFIX}{listing_id}:{expanded_int}"
    label = "Show less" if expanded else "Show more"
    show_more_button = discord.ui.Button(label=label, custom_id=custom_id)

    thumbs_down_button = discord.ui.Button(
        label="",
        emoji="\N{THUMBS DOWN SIGN}",
        custom_id=f"{THUMBSDOWN_PREFIX}{listing_id}",
    )

    thumbnail = discord.ui.Thumbnail(product.img or _PLACEHOLDER_IMG)
    section = discord.ui.Section(
        discord.ui.TextDisplay(main_content),
        accessory=thumbnail,
    )

    container = discord.ui.Container(section, accent_color=ACCENT_PRODUCT)
    container.add_item(discord.ui.ActionRow(show_more_button, thumbs_down_button))
    container.add_item(discord.ui.TextDisplay(footer_content))
    view = discord.ui.LayoutView()
    view.add_item(container)
    return view


def search_config_embed(config: SearchConfig) -> discord.Embed:
    embed = discord.Embed(title=f"Successfully added search: {config.id}", color=ACCENT_PRODUCT)
    embed.add_field(name="Terms", value="\n".join([f"`{term}`" for term in config.terms]))
    embed.add_field(name="Channel", value=f"<#{config.channel}>")
    embed.add_field(name="Marketplace Location ID", value=config.city_code)
    embed.add_field(name="Marketplace Location", value=config.location_name or "—")
    embed.add_field(name="Target Price", value=f"${config.target_price}" if config.target_price else "—")
    embed.add_field(name="Radius", value=f"{config.radius} mi")
    embed.add_field(name="Context", value=config.context or "—")

    return embed


def _format_owner(owner_id: int | None, guild: discord.Guild | None) -> str:
    """Format owner for display: member name if in guild, else ID or 'Unknown'."""
    if owner_id is None:
        return "Unknown"
    if guild:
        member = guild.get_member(owner_id)
        if member:
            return member.display_name or member.name or str(owner_id)
    return f"<@{owner_id}>"


def list_searches_embed(
    searches: list[SearchConfig],
    guild: discord.Guild | None = None,
) -> discord.Embed:
    """Build embed for `/list` command showing watched searches."""
    embed = discord.Embed(title="Watched Searches", color=ACCENT_PRODUCT)
    if not searches:
        embed.description = "No watched searches."
        return embed

    for search in searches[:25]:
        terms = ", ".join(search.terms) if search.terms else "—"
        location = search.location_name or search.city_code or "—"
        owner_str = _format_owner(search.owner_id, guild)
        value = (
            f"Terms: {terms}\n"
            f"Location: {location}\n"
            f"Channel: <#{search.channel}>\n"
            f"Owner: {owner_str}"
        )
        embed.add_field(name=search.id, value=value, inline=False)

    if len(searches) > 25:
        embed.set_footer(text=f"Showing first 25 of {len(searches)} watches.")
    return embed


_PLACEHOLDER_IMG = "https://cdn-1.webcatalog.io/catalog/facebook-marketplace/facebook-marketplace-icon-filled-256.png?v=1714774315353"


def _listing_accessory(entry: ListingLog) -> discord.ui.Thumbnail:
    """Thumbnail from entry.img, or placeholder when missing."""
    return discord.ui.Thumbnail(entry.img or _PLACEHOLDER_IMG)


def _listing_content(content: str, entry: ListingLog) -> str:
    """Append [View listing](url) link when url exists."""
    if entry.url:
        return f"{content}\n\n[View listing]({entry.url})"
    return content


def _listing_container(
    content: str,
    accessory: discord.ui.Thumbnail,
    accent_color: int,
) -> discord.ui.Container:
    """Build a standard Container with Section (text + thumbnail) for listing feed entries."""
    return discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(_truncate_content(content)),
            accessory=accessory,
        ),
        accent_color=accent_color,
    )


def grouped_listing_feed_layout(
    search_id: str,
    entries: Sequence[ListingLog],
) -> discord.ui.LayoutView | None:
    """Build Components V2 LayoutView for grouped feed: cache hits summary, then entries with thumbnail."""
    if not entries:
        return None

    cache_hits = [e for e in entries if e.reason == "Cache hit"]
    others = [e for e in entries if e.reason != "Cache hit"]

    view = discord.ui.LayoutView()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    if cache_hits:
        content = f"**Search: {search_id} — Skipped**\n[{timestamp}] Skipped {len(cache_hits)} cache hits"
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(_truncate_content(content)),
                accent_color=ACCENT_SKIPPED,
            )
        )

    for entry in others:
        title = entry.title[:FIELD_NAME_LIMIT] if len(entry.title) <= FIELD_NAME_LIMIT else entry.title[: FIELD_NAME_LIMIT - 3] + "..."
        reason = entry.reason[:FIELD_REASON_LIMIT] if len(entry.reason) <= FIELD_REASON_LIMIT else entry.reason[: FIELD_REASON_LIMIT - 3] + "..."
        content = _listing_content(f"**{title}**\n{reason}", entry)
        view.add_item(
            _listing_container(content, _listing_accessory(entry), ACCENT_SKIPPED)
        )

    return view


def individual_listing_feed_layout(entry: ListingLog) -> discord.ui.LayoutView:
    """Build Components V2 LayoutView for a single KEPT or SKIPPED entry with thumbnail."""
    price_str = f" ${entry.price}" if entry.price is not None else ""
    name = f"{entry.outcome.value} | {entry.title}{price_str}"
    if len(name) > FIELD_NAME_LIMIT:
        name = name[: FIELD_NAME_LIMIT - 3] + "..."
    value = entry.reason
    if len(value) > FIELD_VALUE_LIMIT:
        value = value[: FIELD_VALUE_LIMIT - 3] + "..."
    content = _listing_content(f"**Search: {entry.search_id}**\n**{name}**\n{value}", entry)
    accent_color = ACCENT_KEPT if entry.outcome.value == "KEPT" else ACCENT_SKIPPED

    view = discord.ui.LayoutView()
    view.add_item(_listing_container(content, _listing_accessory(entry), accent_color))
    return view


