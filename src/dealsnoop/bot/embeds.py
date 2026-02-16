"""Discord embed builders for products and search configs."""

from datetime import datetime
from typing import Sequence

import discord  # pyright: ignore[reportMissingImports]

from dealsnoop.listing_log import ListingLog
from dealsnoop.product import Product
from dealsnoop.search_config import SearchConfig

def product_embed(product: Product, distance: float | None, duration: str | None) -> discord.Embed:
    embed = discord.Embed(
        title=product.title,
        url=product.url,
        description=f"**${product.price}**\n\n{product.description}",
        color=0x03B2F8,
    )
    embed.set_author(name=f"{product.date}", url=product.url, icon_url="https://cdn-1.webcatalog.io/catalog/facebook-marketplace/facebook-marketplace-icon-filled-256.png?v=1714774315353")

    embed.set_thumbnail(url=product.img)
    if distance and duration:
        embed.set_footer(text=f"{product.location} — {round(distance)} mi ({duration})", icon_url="https://cdn-icons-png.flaticon.com/512/1076/1076983.png")
    return embed

def search_config_embed(config: SearchConfig) -> discord.Embed:
    embed = discord.Embed(title=f"Successfully added search: {config.id}", color=0x03B2F8)
    embed.add_field(name="Terms", value="\n".join([f"`{term}`" for term in config.terms]))
    embed.add_field(name="Channel", value=f"<#{config.channel}>")
    embed.add_field(name="City", value=config.city)
    embed.add_field(name="Target Price", value=f"${config.target_price}" if config.target_price else "—")
    embed.add_field(name="Radius", value=f"{config.radius} mi")
    embed.add_field(name="Context", value=config.context or "—")

    return embed


def _listing_accessory(entry: ListingLog) -> discord.ui.Button | discord.ui.Thumbnail:
    """Button (View listing) when url exists, else Thumbnail as placeholder."""
    if entry.url:
        return discord.ui.Button(
            label="View listing",
            url=entry.url,
            style=discord.ButtonStyle.link,
        )
    img = entry.img or "https://cdn-1.webcatalog.io/catalog/facebook-marketplace/facebook-marketplace-icon-filled-256.png?v=1714774315353"
    return discord.ui.Thumbnail(img)


def grouped_listing_feed_layout(
    search_id: str,
    entries: Sequence[ListingLog],
) -> discord.ui.LayoutView | None:
    """Build Components V2 LayoutView for grouped feed: cache hits summary, then sections with View listing button inside each."""
    if not entries:
        return None

    cache_hits = [e for e in entries if e.reason == "Cache hit"]
    others = [e for e in entries if e.reason != "Cache hit"]

    view = discord.ui.LayoutView()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    if cache_hits:
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"**Search: {search_id} — Skipped**\n[{timestamp}] Skipped {len(cache_hits)} cache hits"
                ),
                accent_color=0xFFA500,
            )
        )

    for entry in others:
        title = entry.title[:256] if len(entry.title) <= 256 else entry.title[:253] + "..."
        reason = entry.reason[:4096] if len(entry.reason) <= 4096 else entry.reason[:4093] + "..."
        content = f"**{title}**\n{reason}"
        view.add_item(
            discord.ui.Container(
                discord.ui.Section(
                    discord.ui.TextDisplay(content),
                    accessory=_listing_accessory(entry),
                ),
                accent_color=0xFFA500,
            )
        )

    return view


def individual_listing_feed_layout(entry: ListingLog) -> discord.ui.LayoutView:
    """Build Components V2 LayoutView for a single KEPT or SKIPPED entry with View listing button inside the section."""
    FIELD_NAME_LIMIT = 256
    FIELD_VALUE_LIMIT = 1024
    price_str = f" ${entry.price}" if entry.price is not None else ""
    name = f"{entry.outcome.value} | {entry.title}{price_str}"
    if len(name) > FIELD_NAME_LIMIT:
        name = name[: FIELD_NAME_LIMIT - 3] + "..."
    value = entry.reason
    if len(value) > FIELD_VALUE_LIMIT:
        value = value[: FIELD_VALUE_LIMIT - 3] + "..."
    content = f"**Search: {entry.search_id}**\n**{name}**\n{value}"
    accent_color = 0x00FF00 if entry.outcome.value == "KEPT" else 0xFFA500

    view = discord.ui.LayoutView()
    view.add_item(
        discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(content),
                accessory=_listing_accessory(entry),
            ),
            accent_color=accent_color,
        )
    )
    return view


def listing_feed_embeds(
    search_id: str,
    entries: Sequence[ListingLog],
) -> list[discord.Embed]:
    """Build embeds for the listing feed. Splits into multiple embeds if > 25 entries."""
    if not entries:
        return []

    embeds: list[discord.Embed] = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    FIELDS_PER_EMBED = 25
    FIELD_NAME_LIMIT = 256
    FIELD_VALUE_LIMIT = 1024

    for i in range(0, len(entries), FIELDS_PER_EMBED):
        batch = entries[i : i + FIELDS_PER_EMBED]
        kept_count = sum(1 for e in batch if e.outcome.value == "KEPT")
        skipped_count = len(batch) - kept_count
        color = 0x00FF00 if kept_count > 0 else 0xFFA500  # Green if any kept, else amber

        title = f"Search: {search_id}"
        if i > 0:
            title += f" (part {i // FIELDS_PER_EMBED + 1})"
        embed = discord.Embed(
            title=title,
            description=f"[{timestamp}] {kept_count} kept, {skipped_count} skipped",
            color=color,
        )

        for entry in batch:
            price_str = f" ${entry.price}" if entry.price is not None else ""
            name = f"{entry.outcome.value} | {entry.title}{price_str}"

            if len(name) > FIELD_NAME_LIMIT:
                name = name[: FIELD_NAME_LIMIT - 3] + "..."

            value = entry.reason
            if len(value) > FIELD_VALUE_LIMIT:
                value = value[: FIELD_VALUE_LIMIT - 3] + "..."

            embed.add_field(name=name, value=value, inline=False)

        embeds.append(embed)

    return embeds
