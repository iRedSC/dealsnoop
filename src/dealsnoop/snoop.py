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

    async def on_ready(self):
        for engine in self.engines:
            engine.event_loop.start()
        logger.info("$G$Bot started successfully.")