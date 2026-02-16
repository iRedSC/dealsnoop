"""Discord slash commands for managing marketplace watches."""

from __future__ import annotations

import re

import discord  # type: ignore[import-untyped]
from discord.ext import commands  # type: ignore[import-untyped]

from dealsnoop.bot.embeds import search_config_embed
from dealsnoop.logger import logger
from dealsnoop.search_config import SearchConfig
from dealsnoop.snoop import Snoop


def _parse_channel_id(value: str) -> int:
    """Parse channel ID from raw number or mention format (<#123> or <@123>)."""
    value = value.strip()
    if value.isdigit():
        return int(value)
    m = re.match(r"<[#@!]*(\d+)>", value)
    if m:
        return int(m.group(1))
    raise ValueError("Channel ID must be a number or channel mention (e.g. <#123456789>)")


class Commands(commands.Cog):
    def __init__(self, snoop: Snoop):
        self.snoop = snoop

    @discord.app_commands.command(name="watch", description="Watch for a specific item on various marketplaces.")
    async def watch(
        self,
        interaction: discord.Interaction,
        terms: str,
        target_price: str = "",
        context: str = "",
        city_code: str = "107976589222439",
        days_listed: int = 1,
        radius: int = 30,
        channel_id: str | None = None,
    ) -> None:
        try:
            formatted_terms = tuple(term.strip() for term in terms.split(","))
            search_id = formatted_terms[0].replace(" ", "_")

            for stored in self.snoop.searches.get_all_objects():
                if stored.id == search_id:
                    search_id = search_id + "_"

            if channel_id:
                channel = _parse_channel_id(channel_id)
            elif interaction.channel_id is not None:
                channel = interaction.channel_id
            else:
                await interaction.response.send_message(
                    "ERROR: Could not determine channel. Use this command in a channel or specify a channel ID."
                )
                return
            config = SearchConfig(
                search_id,
                formatted_terms,
                channel,
                target_price=target_price or None,
                context=context or None,
                city_code=city_code,
                days_listed=days_listed,
                radius=radius,
            )
            self.snoop.searches.add_object(config)
            embed = search_config_embed(config)
            await interaction.response.send_message(embed=embed)
        except ValueError as e:
            await interaction.response.send_message(f"ERROR: {e}")

    @discord.app_commands.command(name="list", description="List searches currently being watched.")
    async def list_searches(self, interaction: discord.Interaction) -> None:
        lines = [f"`{s.id}` {s.terms}" for s in self.snoop.searches.get_all_objects()]
        msg = "\n".join(lines) if lines else "No watched searches"
        await interaction.response.send_message(msg)

    @discord.app_commands.command(name="unwatch", description="Remove watched listing.")
    async def unwatch(self, interaction: discord.Interaction, id: str) -> None:
        for search in self.snoop.searches.get_all_objects():
            if search.id == id:
                self.snoop.searches.remove_object(search)
                await interaction.response.send_message(f"Removed {search.terms} from watchlist")
                return
        await interaction.response.send_message("ID not found.")

    @discord.app_commands.command(name="clearcache", description="Clear the listing cache so previously seen listings can be notified again.")
    async def clearcache(self, interaction: discord.Interaction) -> None:
        cleared = 0
        for engine in self.snoop.engines:
            if hasattr(engine, "cache"):
                engine.cache.clear()
                cleared += 1
        if cleared:
            await interaction.response.send_message(f"Cleared cache for {cleared} engine(s).")
        else:
            await interaction.response.send_message("No caches to clear.")

    @discord.app_commands.command(name="forcesearch", description="Run all watched searches immediately, bypassing the timer.")
    async def forcesearch(self, interaction: discord.Interaction) -> None:
        if not self.snoop.searches.get_all_objects():
            await interaction.response.send_message("No watched searches. Add one with `/watch` first.")
            return
        await interaction.response.defer()
        try:
            await self.snoop.run_search_now()
            await interaction.followup.send("Search complete.")
        except Exception as e:
            logger.exception("Forcesearch failed")
            await interaction.followup.send(f"Search failed: {e}")

    searchfeed = discord.app_commands.Group(name="searchfeed", description="Configure the listing feed channel.")

    @searchfeed.command(name="setchannel", description="Set or clear the channel where listing feed (kept/skipped) is posted.")
    async def searchfeed_setchannel(
        self,
        interaction: discord.Interaction,
        channel: str,
    ) -> None:
        try:
            if channel.strip().lower() == "none":
                self.snoop.searches.set_feed_channel_id(None)
                await interaction.response.send_message("Feed channel cleared.")
                return
            channel_id = _parse_channel_id(channel)
            self.snoop.searches.set_feed_channel_id(channel_id)
            await interaction.response.send_message(f"Feed channel set to <#{channel_id}>.")
        except ValueError as e:
            await interaction.response.send_message(f"ERROR: {e}")