"""Orchestrates search engines and coordinates with the Discord bot."""

from __future__ import annotations

from typing import Protocol

import discord  # type: ignore[import-untyped]
from dealsnoop.logger import logger
from dealsnoop.bot.client import Client
from dealsnoop.store import SearchStore
from discord.ext.tasks import Loop  # type: ignore[import-untyped]


class Engine(Protocol):
    snoop: Snoop
    event_loop: Loop


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

    def trigger_search_and_reset_timer(self) -> None:
        """Trigger a search now and reset the 5-minute loop timer for each engine."""
        for engine in self.engines:
            engine.event_loop.restart()

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

    async def run_cleanup_async(
        self, guild: discord.Guild
    ) -> tuple[int, int, list[str]]:
        """Delete bot-owned channels with no active watches and empty categories. Returns (deleted_channels, deleted_categories, errors)."""
        bot_owned = self.searches.get_bot_owned_channels()
        with_watches = self.searches.get_channels_with_active_watches()
        to_delete = bot_owned - with_watches

        deleted_channels = 0
        deleted_categories = 0
        errors: list[str] = []

        for channel_id in to_delete:
            channel = guild.get_channel(channel_id)
            if channel is None:
                self.searches.remove_bot_owned_channel(channel_id)
                continue
            if not isinstance(channel, discord.TextChannel):
                continue
            try:
                await channel.delete()
                self.searches.remove_bot_owned_channel(channel_id)
                deleted_channels += 1
            except discord.Forbidden:
                errors.append(f"Cannot delete <#{channel_id}>: missing permissions")
            except discord.HTTPException as e:
                errors.append(f"Cannot delete <#{channel_id}>: {e}")

        bot_owned_cats = self.searches.get_bot_owned_categories()
        for category_id in bot_owned_cats:
            category = guild.get_channel(category_id)
            if category is None:
                self.searches.remove_bot_owned_category(category_id)
                continue
            if not isinstance(category, discord.CategoryChannel):
                continue
            if len(category.channels) == 0:
                try:
                    await category.delete()
                    self.searches.remove_bot_owned_category(category_id)
                    deleted_categories += 1
                except discord.Forbidden:
                    errors.append(f"Cannot delete category {category.name}: missing permissions")
                except discord.HTTPException as e:
                    errors.append(f"Cannot delete category {category.name}: {e}")

        return deleted_channels, deleted_categories, errors

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