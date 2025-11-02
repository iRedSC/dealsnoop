
from __future__ import annotations
from asyncio.log import logger
from typing import Protocol
from dealsnoop.bot.client import Client
from dealsnoop.pickler import ObjectStore
from discord.ext.tasks import Loop


class Engine(Protocol):
    snoop: Snoop
    event_loop: Loop



class Snoop:
    bot: Client
    searches: ObjectStore
    engines: set[Engine]

    def __init__(self, bot: Client, searches: ObjectStore):
        self.bot = bot
        self.bot.on_ready = self.on_ready

        self.searches = searches
        self.engines = set()

    def register_engine(self, engine: Engine):
        self.engines.add(engine)
        engine.snoop = self

    async def on_ready(self):
        for engine in self.engines:
            engine.event_loop.start()
        logger.info("$G$Bot started successfully.")