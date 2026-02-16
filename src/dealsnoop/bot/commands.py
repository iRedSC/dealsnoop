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