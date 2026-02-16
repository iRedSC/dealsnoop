"""Structured log objects for listing decisions, output to console and Discord feed."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
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

    def __init__(
        self,
        search_id: str,
        bot: object | None = None,
        feed_channel_id: int | None = None,
    ) -> None:
        self.search_id = search_id
        self._bot = bot
        self._feed_channel_id = feed_channel_id
        self._grouped_entries: list[ListingLog] = []
        self._running = False
        self._flush_task: asyncio.Task[None] | None = None

    def add_grouped(self, title: str, reason: str) -> None:
        """Add a grouped entry (cache hit, outside radius, malformed). Buffered, sent every 1s."""
        self._grouped_entries.append(
            ListingLog(
                search_id=self.search_id,
                title=title,
                outcome=Outcome.SKIPPED,
                reason=reason,
                url=None,
                price=None,
            )
        )

    def add_individual_kept(
        self,
        title: str,
        reason: str = "Matched",
        url: str | None = None,
        price: float | None = None,
    ) -> None:
        """Log and send immediately to Discord feed."""
        entry = ListingLog(
            search_id=self.search_id,
            title=title,
            outcome=Outcome.KEPT,
            reason=reason,
            url=url,
            price=price,
        )
        self._log_entry(entry)
        asyncio.create_task(self._send_individual(entry))

    def add_individual_skipped(
        self,
        title: str,
        reason: str,
        url: str | None = None,
        price: float | None = None,
    ) -> None:
        """Log and send immediately to Discord feed."""
        entry = ListingLog(
            search_id=self.search_id,
            title=title,
            outcome=Outcome.SKIPPED,
            reason=reason,
            url=url,
            price=price,
        )
        self._log_entry(entry)
        asyncio.create_task(self._send_individual(entry))

    def _log_entry(self, entry: ListingLog) -> None:
        price_str = f" ${entry.price}" if entry.price is not None else ""
        logger.info(
            f"$G${entry.search_id}$W$ | {entry.outcome.value} | {entry.title}{price_str} | {entry.reason}"
        )

    async def _send_individual(self, entry: ListingLog) -> None:
        """Send a single individual embed to the feed channel."""
        if not self._feed_channel_id or self._bot is None:
            return
        from dealsnoop.bot.embeds import individual_listing_feed_embed

        embed = individual_listing_feed_embed(entry)
        channel = getattr(self._bot, "get_channel", lambda _: None)(self._feed_channel_id)
        if channel is None or not hasattr(channel, "send"):
            return
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    def start(self) -> None:
        """Start the periodic flush task for grouped entries."""
        if self._flush_task is not None:
            return
        self._running = True
        self._flush_task = asyncio.create_task(self._periodic_flush())

    async def _periodic_flush(self) -> None:
        """Every 1 second, flush grouped entries to Discord."""
        while self._running:
            await asyncio.sleep(1)
            if self._grouped_entries:
                await self._flush_grouped()

    async def _flush_grouped(self) -> None:
        """Send current grouped entries as one message and clear buffer."""
        if not self._grouped_entries:
            return
        entries = self._grouped_entries[:]
        self._grouped_entries.clear()

        for entry in entries:
            self._log_entry(entry)

        if self._feed_channel_id and self._bot is not None:
            from dealsnoop.bot.embeds import grouped_listing_feed_embed

            embed = grouped_listing_feed_embed(self.search_id, entries)
            channel = getattr(self._bot, "get_channel", lambda _: None)(self._feed_channel_id)
            if channel is not None and hasattr(channel, "send"):
                try:
                    await channel.send(embed=embed)
                except Exception:
                    pass

    async def flush(self) -> None:
        """Stop periodic task, flush remaining grouped entries, clear state."""
        self._running = False
        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None

        await self._flush_grouped()
