"""Discord slash commands for managing marketplace watches."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

import discord  # type: ignore[import-untyped]
from discord.ext import commands  # type: ignore[import-untyped]

from dealsnoop.bot.embeds import list_searches_embed, search_config_embed
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


def _parse_id(value: str) -> int:
    """Parse channel or category ID from raw number or mention format."""
    value = value.strip()
    if value.isdigit():
        return int(value)
    m = re.match(r"<[#@!]*(\d+)>", value)
    if m:
        return int(m.group(1))
    raise ValueError("ID must be a number or channel mention (e.g. <#123456789>)")


def _parse_city_code(value: str) -> str:
    """Parse and validate a Marketplace city/location code."""
    city_code = value.strip()
    if not city_code.isdigit():
        raise ValueError("City code must be numeric (example: 107976589222439).")
    return city_code


def _slugify_discord_name(value: str, fallback: str) -> str:
    """Build a Discord-safe lowercase name using letters, numbers, and hyphens."""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    text = normalized.lower().replace("_", "-")
    text = re.sub(r"[^a-z0-9-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    text = text[:100]
    return text if text else fallback


def _is_admin(interaction: discord.Interaction) -> bool:
    """Return True if the user has administrator permission in the guild."""
    if interaction.guild is None:
        return False
    return interaction.user.guild_permissions.administrator


def _get_base_id(search_id: str) -> str:
    """Return base id by stripping a trailing numeric suffix (_N)."""
    parts = search_id.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return search_id


def _make_search_id(terms: tuple[str, ...], existing_ids: set[str]) -> str:
    """Create a normalized and collision-safe watch id from first term."""
    first_term = terms[0] if terms else "watch"
    candidate = first_term.lower().replace(" ", "_")
    candidate = re.sub(r"[^a-z0-9_]+", "", candidate)
    candidate = re.sub(r"_{2,}", "_", candidate).strip("_")
    base_id = candidate or "watch"

    count = sum(1 for existing_id in existing_ids if _get_base_id(existing_id) == base_id)
    return base_id if count == 0 else f"{base_id}_{count + 1}"


class Commands(commands.Cog):
    def __init__(self, snoop: Snoop):
        self.snoop = snoop

    async def _respond(
        self,
        interaction: discord.Interaction,
        *,
        content: str | None = None,
        embed: discord.Embed | None = None,
    ) -> None:
        """Send response to initial interaction or followup after defer."""
        if interaction.response.is_done():
            await interaction.followup.send(content=content, embed=embed)
            return
        await interaction.response.send_message(content=content, embed=embed)

    async def _get_or_create_location_category(
        self,
        guild: discord.Guild,
        location_name: str,
    ) -> discord.CategoryChannel:
        """Find or create category for a location."""
        category_name = _slugify_discord_name(location_name, "marketplace")
        existing = discord.utils.get(guild.categories, name=category_name)
        if existing is not None:
            return existing
        category = await guild.create_category(category_name)
        self.snoop.searches.record_bot_owned_category(category.id)
        return category

    async def _create_watch_channel(
        self,
        interaction: discord.Interaction,
        search_id: str,
        city_code: str,
        *,
        location_name: str | None = None,
    ) -> tuple[int, str]:
        """Create a text channel for a watch under location category."""
        guild = interaction.guild
        if guild is None and interaction.guild_id is not None:
            guild = self.snoop.bot.get_guild(interaction.guild_id)
        if guild is None:
            raise ValueError("Cannot create channel outside a server.")

        if location_name is None:
            location_name = await self.snoop.get_location_for_city_code(city_code)
        category = await self._get_or_create_location_category(guild, location_name)
        channel_name = _slugify_discord_name(search_id, "watch")
        existing = discord.utils.get(category.text_channels, name=channel_name)
        if existing is not None:
            return (existing.id, location_name)
        channel = await guild.create_text_channel(channel_name, category=category)
        self.snoop.searches.record_bot_owned_channel(channel.id)
        return (channel.id, location_name)

    @discord.app_commands.command(name="watch", description="Watch for a specific item on various marketplaces.")
    async def watch(
        self,
        interaction: discord.Interaction,
        terms: str,
        target_price: str = "",
        context: str = "",
        city_code: str = "",
        days_listed: int = 1,
        radius: int = 30,
        channel_id: str | None = None,
    ) -> None:
        try:
            formatted_terms = tuple(term.strip() for term in terms.split(","))
            existing_ids = {search.id for search in self.snoop.searches.get_all_objects()}
            search_id = _make_search_id(formatted_terms, existing_ids)

            user_loc = self.snoop.searches.get_user_location(interaction.user.id)
            resolved_city_code = _parse_city_code(city_code) if city_code else (
                user_loc.city_code if user_loc else "107976589222439"
            )
            if channel_id:
                channel = _parse_channel_id(channel_id)
            else:
                channel = None

            await interaction.response.defer()

            resolved_location_name = self.snoop.searches.get_location_name(resolved_city_code)
            if resolved_location_name is None:
                resolved_location_name = await self.snoop.get_location_for_city_code(resolved_city_code)

            if channel is not None:
                pass
            else:
                channel, resolved_location_name = await self._create_watch_channel(
                    interaction,
                    search_id=search_id,
                    city_code=resolved_city_code,
                    location_name=resolved_location_name,
                )
            config = SearchConfig(
                search_id,
                formatted_terms,
                channel,
                target_price=target_price or None,
                context=context or None,
                city_code=resolved_city_code,
                location_name=resolved_location_name,
                days_listed=days_listed,
                radius=radius,
                owner_id=interaction.user.id,
            )
            self.snoop.searches.add_object(config)
            embed = search_config_embed(config)
            await self._respond(interaction, embed=embed)
        except ValueError as e:
            await self._respond(interaction, content=f"ERROR: {e}")
        except discord.Forbidden:
            await self._respond(
                interaction,
                content="ERROR: I need Manage Channels permission to create category/channel automatically.",
            )
        except discord.HTTPException as e:
            await self._respond(interaction, content=f"ERROR: Failed to create channel/category: {e}")
        except Exception as e:
            await self._respond(interaction, content=f"ERROR: {e}")

    @discord.app_commands.command(name="list", description="List searches currently being watched.")
    async def list_searches(self, interaction: discord.Interaction) -> None:
        searches = sorted(self.snoop.searches.get_all_objects(), key=lambda s: s.id)
        guild: discord.Guild | None = interaction.guild
        if guild is None and interaction.guild_id is not None:
            guild = self.snoop.bot.get_guild(interaction.guild_id)
        await interaction.response.send_message(
            embed=list_searches_embed(searches, guild=guild),
        )

    async def _unwatch_id_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[discord.app_commands.Choice[str]]:
        """Autocomplete search IDs for the unwatch command."""
        searches = self.snoop.searches.get_all_objects()
        current_lower = current.lower()
        choices = [
            discord.app_commands.Choice(name=s.id, value=s.id)
            for s in searches
            if not current_lower or current_lower in s.id.lower() or any(current_lower in t.lower() for t in s.terms)
        ]
        return choices[:25]  # Discord limit

    @discord.app_commands.command(name="unwatch", description="Remove watched listing.")
    @discord.app_commands.autocomplete(id=_unwatch_id_autocomplete)
    async def unwatch(self, interaction: discord.Interaction, id: str) -> None:
        for search in self.snoop.searches.get_all_objects():
            if search.id == id:
                if not _is_admin(interaction) and search.owner_id != interaction.user.id:
                    await interaction.response.send_message(
                        "You can only remove watches you own. Ask an admin to remove this one.",
                        ephemeral=True,
                    )
                    return
                self.snoop.searches.remove_object(search)
                await interaction.response.send_message(f"Removed {search.terms} from watchlist")
                if self.snoop.searches.get_cleanup_auto():
                    guild = interaction.guild or (
                        self.snoop.bot.get_guild(interaction.guild_id) if interaction.guild_id else None
                    )
                    if guild:
                        await self.snoop.run_cleanup_async(guild)
                return
        await interaction.response.send_message("ID not found.")

    admin = discord.app_commands.Group(
        name="admin",
        description="Admin commands.",
        default_permissions=discord.Permissions(administrator=True),
    )

    cleanup = discord.app_commands.Group(
        name="cleanup",
        description="Cleanup bot-owned channels.",
    )

    @cleanup.command(name="now", description="Delete all bot-owned channels that have no active watches.")
    async def admin_cleanup_now(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None and interaction.guild_id is not None:
            guild = self.snoop.bot.get_guild(interaction.guild_id)
        if guild is None:
            await interaction.response.send_message(
                "This command must be run in a server.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        deleted_channels, deleted_categories, errors = await self.snoop.run_cleanup_async(guild)
        parts = [f"Deleted {deleted_channels} channel(s) and {deleted_categories} empty category(ies)."]
        if errors:
            parts.append("\nErrors: " + "; ".join(errors[:5]))
            if len(errors) > 5:
                parts.append(f" ... and {len(errors) - 5} more")
        await interaction.followup.send("\n".join(parts), ephemeral=True)

    @cleanup.command(name="auto", description="Enable or disable auto-cleanup when all watches are removed from a channel.")
    async def admin_cleanup_auto(
        self,
        interaction: discord.Interaction,
        mode: Literal["on", "off"],
    ) -> None:
        enabled = mode == "on"
        self.snoop.searches.set_cleanup_auto(enabled)
        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(f"Auto-cleanup {status}.")

    admin.add_command(cleanup)

    @admin.command(name="set_owned", description="Mark a channel or category as bot-owned for cleanup tracking.")
    async def admin_set_owned(
        self,
        interaction: discord.Interaction,
        type: Literal["category", "channel"],
        id: str,
    ) -> None:
        try:
            target_id = _parse_id(id)
            if type == "channel":
                self.snoop.searches.record_bot_owned_channel(target_id)
                await interaction.response.send_message(f"Marked channel <#{target_id}> as bot-owned.")
            else:
                self.snoop.searches.record_bot_owned_category(target_id)
                guild = interaction.guild or (
                    self.snoop.bot.get_guild(interaction.guild_id) if interaction.guild_id else None
                )
                channel_count = 0
                if guild:
                    category = guild.get_channel(target_id)
                    if isinstance(category, discord.CategoryChannel):
                        for ch in category.channels:
                            self.snoop.searches.record_bot_owned_channel(ch.id)
                            channel_count += 1
                if channel_count:
                    await interaction.response.send_message(
                        f"Marked category `{target_id}` and its {channel_count} channel(s) as bot-owned."
                    )
                else:
                    await interaction.response.send_message(f"Marked category `{target_id}` as bot-owned.")
        except ValueError as e:
            await interaction.response.send_message(f"ERROR: {e}", ephemeral=True)

    @admin.command(name="clearcache", description="Clear the listing cache so previously seen listings can be notified again.")
    async def admin_clearcache(self, interaction: discord.Interaction) -> None:
        cleared = 0
        for engine in self.snoop.engines:
            if hasattr(engine, "cache"):
                engine.cache.clear()
                cleared += 1
        if cleared:
            await interaction.response.send_message(f"Cleared cache for {cleared} engine(s).")
        else:
            await interaction.response.send_message("No caches to clear.")

    @admin.command(name="forcesearch", description="Start a search now and reset the 5-minute loop timer.")
    async def admin_forcesearch(self, interaction: discord.Interaction) -> None:
        if not self.snoop.searches.get_all_objects():
            await interaction.response.send_message("No watched searches. Add one with `/watch` first.")
            return
        self.snoop.trigger_search_and_reset_timer()
        await interaction.response.send_message("Search started.")

    searchfeed = discord.app_commands.Group(
        name="searchfeed",
        description="Configure the listing feed channel.",
    )

    @searchfeed.command(name="setchannel", description="Set or clear the channel where listing feed (kept/skipped) is posted.")
    async def admin_searchfeed_setchannel(
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

    admin.add_command(searchfeed)

    location = discord.app_commands.Group(name="location", description="Manage your default Marketplace location.")

    @location.command(name="set", description="Set your default Marketplace location code.")
    async def location_set(self, interaction: discord.Interaction, city_code: str) -> None:
        try:
            parsed_city_code = _parse_city_code(city_code)
        except ValueError as e:
            await interaction.response.send_message(f"ERROR: {e}")
            return

        await interaction.response.defer()
        try:
            location_name = await self.snoop.get_location_for_city_code(parsed_city_code)
            self.snoop.searches.set_user_location(interaction.user.id, parsed_city_code)
            await interaction.followup.send(
                f"Default Marketplace location set to **{location_name}** (`{parsed_city_code}`)."
            )
        except Exception as e:
            await interaction.followup.send(f"ERROR: {e}")

    @location.command(name="remove", description="Remove your default Marketplace location code.")
    async def location_remove(self, interaction: discord.Interaction) -> None:
        removed = self.snoop.searches.remove_user_location(interaction.user.id)
        if removed:
            await interaction.response.send_message("Location removed.")
        else:
            await interaction.response.send_message("No location set for your account.")