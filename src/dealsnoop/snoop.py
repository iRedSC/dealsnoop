"""Orchestrates search engines and coordinates with the Discord bot."""

from __future__ import annotations

from typing import Protocol

from dealsnoop.logger import logger
from dealsnoop.bot.client import Client
from dealsnoop.store import SearchStore
from discord.ext.tasks import Loop  # type: ignore[import-untyped]


class Engine(Protocol):
    snoop: Snoop
    event_loop: Loop

    async def run_search_now(self) -> None: ...


class Snoop:
    bot: Client
    searches: SearchStore
    engines: set[Engine]

    def __init__(self, bot: Client, searches: SearchStore):
        self.bot = bot
        self.bot.on_ready = self.on_ready

        self.searches = searches
        self.engines = set()

    def register_engine(self, engine: Engine):
        self.engines.add(engine)
        engine.snoop = self

    async def run_search_now(self) -> None:
        """Run all engine searches immediately, bypassing the timer."""
        for engine in self.engines:
            await engine.run_search_now()

    async def get_location_for_city_code(self, city_code: str) -> str:
        """Resolve and cache human-readable location name for a city code."""
        cached = self.searches.get_location_name(city_code)
        if cached:
            return cached

        for engine in self.engines:
            resolver = getattr(engine, "get_location_for_city_code", None)
            if resolver is None:
                continue
            location_name = await resolver(city_code)
            self.searches.set_location_name(city_code, location_name)
            return location_name

        logger.warning("No engine available to resolve city code %s; using city code as fallback.", city_code)
        self.searches.set_location_name(city_code, city_code)
        return city_code

    async def on_ready(self):
        for engine in self.engines:
            engine.event_loop.start()
        logger.info("$G$Bot started successfully.")

        feed_channel_id = self.searches.get_feed_channel_id()
        if feed_channel_id:
            channel = self.bot.get_channel(feed_channel_id)
            if channel is not None:
                try:
                    await channel.send("Bot started successfully.")
                except Exception:
                    pass