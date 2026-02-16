"""Structured log objects for listing decisions, output to console and Discord feed."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from dealsnoop.logger import logger


class Outcome(str, Enum):
    KEPT = "KEPT"
    SKIPPED = "SKIPPED"


@dataclass
class ListingLog:
    """Structured log entry for a single listing decision."""

    search_id: str
    title: str
    outcome: Outcome
    reason: str
    url: str | None = None
    price: float | None = None


class SearchLogCollector:
    """Accumulates ListingLog entries for one search run; flushes to logger and Discord feed."""

    def __init__(self, search_id: str) -> None:
        self.search_id = search_id
        self._entries: list[ListingLog] = []

    def add_kept(
        self,
        title: str,
        reason: str = "Matched",
        url: str | None = None,
        price: float | None = None,
    ) -> None:
        self._entries.append(
            ListingLog(
                search_id=self.search_id,
                title=title,
                outcome=Outcome.KEPT,
                reason=reason,
                url=url,
                price=price,
            )
        )

    def add_skipped(
        self,
        title: str,
        reason: str,
        url: str | None = None,
        price: float | None = None,
    ) -> None:
        self._entries.append(
            ListingLog(
                search_id=self.search_id,
                title=title,
                outcome=Outcome.SKIPPED,
                reason=reason,
                url=url,
                price=price,
            )
        )

    async def flush(
        self,
        bot: object | None = None,
        feed_channel_id: int | None = None,
    ) -> None:
        """Output entries to logger and optionally to Discord feed channel."""
        if not self._entries:
            return

        # Emit to console via logger
        for entry in self._entries:
            price_str = f" ${entry.price}" if entry.price is not None else ""
            logger.info(
                f"$G${entry.search_id}$W$ | {entry.outcome.value} | {entry.title}{price_str} | {entry.reason}"
            )

        # Send to Discord feed if configured
        if feed_channel_id and bot is not None:
            await self._send_to_feed(bot, feed_channel_id)

        self._entries.clear()

    async def _send_to_feed(self, bot: object, feed_channel_id: int) -> None:
        """Send embeds to the feed channel. No-op if bot lacks send capability."""
        from dealsnoop.bot.embeds import listing_feed_embeds

        embeds = listing_feed_embeds(self.search_id, self._entries)
        if not embeds:
            return

        channel = getattr(bot, "get_channel", lambda _: None)(feed_channel_id)
        if channel is None or not hasattr(channel, "send"):
            return

        for embed in embeds:
            try:
                await channel.send(embed=embed)
            except Exception:
                pass
