"""Discord bot client with slash command support."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord  # type: ignore[import-untyped]
from discord.ext import commands  # type: ignore[import-untyped]

from dealsnoop.bot.embeds import (
    LISTING_DESC_PREFIX,
    THUMBSDOWN_PREFIX,
    product_layout_view,
    search_config_embed,
    truncate_description,
)
from dealsnoop.config import GUILD_ID
from dealsnoop.logger import logger
from dealsnoop.product import Product
from dealsnoop.search_config import SearchConfig
from dealsnoop.store import SearchStore

if TYPE_CHECKING:
    from dealsnoop.snoop import Snoop

GUILD = discord.Object(GUILD_ID)


def _parse_city_code(value: str) -> str:
    """Parse and validate a Marketplace city/location code."""
    city_code = value.strip()
    if not city_code.isdigit():
        raise ValueError("City code must be numeric (example: 107976589222439).")
    return city_code

intents = discord.Intents.default()
intents.message_content = True


class UpdateWatchModal(discord.ui.Modal, title="Update watch"):
    """Modal for editing watch values. Submitting updates the watch in the store."""

    def __init__(
        self,
        searches: SearchStore,
        config: SearchConfig,
        snoop: Snoop | None,
    ) -> None:
        super().__init__()
        self._searches = searches
        self._config = config
        self._snoop = snoop

        self.terms_input = discord.ui.TextInput(
            label="Terms (comma-separated)",
            default=", ".join(config.terms),
            required=True,
            max_length=500,
        )
        self.target_price_input = discord.ui.TextInput(
            label="Target price",
            default=config.target_price or "",
            required=False,
            max_length=50,
        )
        self.context_input = discord.ui.TextInput(
            label="Context",
            default=config.context or "",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=500,
        )
        self.city_code_input = discord.ui.TextInput(
            label="City code",
            default=config.city_code,
            required=True,
            max_length=50,
        )
        self.radius_input = discord.ui.TextInput(
            label="Radius (miles)",
            default=str(config.radius),
            required=True,
            max_length=10,
        )

        self.add_item(self.terms_input)
        self.add_item(self.target_price_input)
        self.add_item(self.context_input)
        self.add_item(self.city_code_input)
        self.add_item(self.radius_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        terms_raw = self.terms_input.value.strip()
        terms = tuple(t.strip() for t in terms_raw.split(",") if t.strip())
        if not terms:
            await interaction.response.send_message(
                "Terms cannot be empty.",
                ephemeral=True,
            )
            return

        try:
            city_code = _parse_city_code(self.city_code_input.value)
        except ValueError as e:
            await interaction.response.send_message(
                f"ERROR: {e}",
                ephemeral=True,
            )
            return

        try:
            radius = int(self.radius_input.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "ERROR: Radius must be a whole number.",
                ephemeral=True,
            )
            return

        target_price = self.target_price_input.value.strip() or None
        context = self.context_input.value.strip() or None

        location_name = self._config.location_name
        if self._snoop is not None:
            location_name = await self._snoop.get_location_for_city_code(city_code)

        updated = SearchConfig(
            id=self._config.id,
            terms=terms,
            channel=self._config.channel,
            city_code=city_code,
            location_name=location_name,
            target_price=target_price,
            days_listed=self._config.days_listed,
            radius=radius,
            context=context,
        )
        await asyncio.to_thread(self._searches.add_object, updated)
        embed = search_config_embed(updated)
        await interaction.response.send_message(
            "Watch updated.",
            embed=embed,
            ephemeral=True,
        )


class UpdateContextModal(discord.ui.Modal, title="Update context"):
    """Modal for editing only the context field of a watch."""

    def __init__(
        self,
        searches: SearchStore,
        config: SearchConfig,
        *,
        initial_context: str | None = None,
    ) -> None:
        super().__init__()
        self._searches = searches
        self._config = config

        default = initial_context if initial_context is not None else (config.context or "")
        self.context_input = discord.ui.TextInput(
            label="Context",
            default=default,
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=500,
        )
        self.add_item(self.context_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        context = self.context_input.value.strip() or None
        updated = SearchConfig(
            id=self._config.id,
            terms=self._config.terms,
            channel=self._config.channel,
            city_code=self._config.city_code,
            location_name=self._config.location_name,
            target_price=self._config.target_price,
            days_listed=self._config.days_listed,
            radius=self._config.radius,
            context=context,
        )
        await asyncio.to_thread(self._searches.add_object, updated)
        await interaction.response.send_message(
            "Context updated.",
            ephemeral=True,
        )


class ThumbsDownModal(discord.ui.Modal, title="What don't you like about this listing?"):
    """Modal for thumbs-down feedback. User's text is appended to watch context."""

    def __init__(self, searches: SearchStore, config: SearchConfig) -> None:
        super().__init__()
        self._searches = searches
        self._config = config

        self.feedback_input = discord.ui.TextInput(
            label="What don't you like about this listing?",
            placeholder="I only want blue and red...",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=500,
        )
        self.add_item(self.feedback_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        feedback = self.feedback_input.value.strip()
        existing = self._config.context or ""
        new_context = (
            f"{existing}\n\n{feedback}"
            if existing
            else feedback
        )
        updated = SearchConfig(
            id=self._config.id,
            terms=self._config.terms,
            channel=self._config.channel,
            city_code=self._config.city_code,
            location_name=self._config.location_name,
            target_price=self._config.target_price,
            days_listed=self._config.days_listed,
            radius=self._config.radius,
            context=new_context.strip() or None,
        )
        await asyncio.to_thread(self._searches.add_object, updated)
        await interaction.response.send_message(
            "Context updated.",
            ephemeral=True,
        )


class Client(commands.Bot):
    _unregistered_cogs: list[commands.Cog]

    def __init__(self, searches: SearchStore):
        super().__init__(command_prefix="!@#", intents=intents)
        self._unregistered_cogs = []
        self._searches = searches
    

    def register_cog(self, cog: commands.Cog) -> None:
        self._unregistered_cogs.append(cog)

    def record_listing_metadata(
        self,
        message_id: int,
        channel_id: int,
        search_id: str,
        thought_trace: str | None = None,
    ) -> None:
        """Store listing metadata for a Discord message."""
        self._searches.record_listing_metadata(
            message_id, channel_id, search_id, thought_trace
        )

    async def _register_cog(self, cog: commands.Cog) -> None:
        logger.info("Registering Commands")
        await self.add_cog(cog)
        for command in cog.get_app_commands():
            self.tree.add_command(command, guild=GUILD)
            logger.info(f"Added command '{command.name}'")

    async def setup_hook(self) -> None:
        @self.tree.context_menu(name="Show AI reasoning")
        async def show_ai_reasoning(
            interaction: discord.Interaction, message: discord.Message
        ) -> None:
            await interaction.response.defer(ephemeral=True)
            listing = await asyncio.to_thread(
                self._searches.get_listing_by_message_id, message.id
            )
            if listing:
                thought_trace = listing.get("thought_trace")
            else:
                meta = await asyncio.to_thread(
                    self._searches.get_listing_metadata, message.id
                )
                thought_trace = meta.get("thought_trace") if meta else None
            if not thought_trace:
                await interaction.followup.send(
                    "No AI reasoning for this message (e.g. feed-only listing).",
                    ephemeral=True,
                )
                return
            max_desc = 4096
            text = thought_trace[:max_desc]
            if len(thought_trace) > max_desc:
                text = text[: max_desc - 3] + "..."
            embed = discord.Embed(
                title="AI thought trace",
                description=text,
                color=0x5865F2,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        @self.tree.context_menu(name="Get watch command")
        async def get_watch_command(
            interaction: discord.Interaction, message: discord.Message
        ) -> None:
            await interaction.response.defer(ephemeral=True)
            listing = await asyncio.to_thread(
                self._searches.get_listing_by_message_id, message.id
            )
            if listing and listing.get("watch_command"):
                cmd = listing["watch_command"]
                await interaction.followup.send(
                    f"```\n{cmd}\n```",
                    ephemeral=True,
                )
                return
            meta = await asyncio.to_thread(
                self._searches.get_listing_metadata, message.id
            )
            if meta is None:
                await interaction.followup.send(
                    "No watch found for this message.",
                    ephemeral=True,
                )
                return
            search_id = meta["search_id"]
            config = await asyncio.to_thread(
                self._searches.get_config_by_id, search_id
            )
            if config is None:
                await interaction.followup.send(
                    "Watch already removed.",
                    ephemeral=True,
                )
                return
            from dealsnoop.search_config import build_watch_command

            cmd = build_watch_command(config, message.channel_id)
            await interaction.followup.send(
                f"```\n{cmd}\n```",
                ephemeral=True,
            )

        def _can_modify_watch(interaction: discord.Interaction, config) -> bool:
            """Return True if user is admin or owner of the watch."""
            if interaction.guild and interaction.user.guild_permissions.administrator:
                return True
            return config.owner_id == interaction.user.id if config.owner_id else False

        @self.tree.context_menu(name="Remove watch")
        async def remove_watch(
            interaction: discord.Interaction, message: discord.Message
        ) -> None:
            await interaction.response.defer(ephemeral=True)
            listing = await asyncio.to_thread(
                self._searches.get_listing_by_message_id, message.id
            )
            if listing:
                search_id = listing["search_id"]
            else:
                meta = await asyncio.to_thread(
                    self._searches.get_listing_metadata, message.id
                )
                if meta is None:
                    await interaction.followup.send(
                        "No watch found for this message.",
                        ephemeral=True,
                    )
                    return
                search_id = meta["search_id"]
            config = await asyncio.to_thread(
                self._searches.get_config_by_id, search_id
            )
            if config is None:
                await interaction.followup.send(
                    "Watch already removed.",
                    ephemeral=True,
                )
                return
            if not _can_modify_watch(interaction, config):
                await interaction.followup.send(
                    "You can only remove watches you own.",
                    ephemeral=True,
                )
                return
            removed = await asyncio.to_thread(
                self._searches.remove_by_id, search_id
            )
            if not removed:
                await interaction.followup.send(
                    "Watch could not be removed (may have been deleted already).",
                    ephemeral=True,
                )
                return
            await interaction.followup.send(
                f"Removed watch {search_id}.",
                ephemeral=True,
            )

        @self.tree.context_menu(name="Update watch")
        async def update_watch(
            interaction: discord.Interaction, message: discord.Message
        ) -> None:
            listing = await asyncio.to_thread(
                self._searches.get_listing_by_message_id, message.id
            )
            if listing:
                search_id = listing["search_id"]
            else:
                meta = await asyncio.to_thread(
                    self._searches.get_listing_metadata, message.id
                )
                if meta is None:
                    await interaction.response.send_message(
                        "No watch found for this message.",
                        ephemeral=True,
                    )
                    return
                search_id = meta["search_id"]
            config = await asyncio.to_thread(
                self._searches.get_config_by_id, search_id
            )
            if config is None:
                await interaction.response.send_message(
                    "Watch already removed.",
                    ephemeral=True,
                )
                return
            if not _can_modify_watch(interaction, config):
                await interaction.response.send_message(
                    "Only admins and the watch owner can update watches.",
                    ephemeral=True,
                )
                return
            snoop = getattr(self, "_snoop", None)
            modal = UpdateWatchModal(self._searches, config, snoop)
            await interaction.response.send_modal(modal)

        @self.tree.context_menu(name="Update context")
        async def update_context(
            interaction: discord.Interaction, message: discord.Message
        ) -> None:
            listing = await asyncio.to_thread(
                self._searches.get_listing_by_message_id, message.id
            )
            if listing:
                search_id = listing["search_id"]
            else:
                meta = await asyncio.to_thread(
                    self._searches.get_listing_metadata, message.id
                )
                if meta is None:
                    await interaction.response.send_message(
                        "No watch found for this message.",
                        ephemeral=True,
                    )
                    return
                search_id = meta["search_id"]
            config = await asyncio.to_thread(
                self._searches.get_config_by_id, search_id
            )
            if config is None:
                await interaction.response.send_message(
                    "Watch already removed.",
                    ephemeral=True,
                )
                return
            if not _can_modify_watch(interaction, config):
                await interaction.response.send_message(
                    "Only admins and the watch owner can update context.",
                    ephemeral=True,
                )
                return
            modal = UpdateContextModal(self._searches, config)
            await interaction.response.send_modal(modal)

        self.tree.add_command(show_ai_reasoning, guild=GUILD)
        self.tree.add_command(get_watch_command, guild=GUILD)
        self.tree.add_command(remove_watch, guild=GUILD)
        self.tree.add_command(update_watch, guild=GUILD)
        self.tree.add_command(update_context, guild=GUILD)
        logger.info("Added commands 'Show AI reasoning', 'Get watch command', 'Remove watch', 'Update watch', 'Update context'")
        for cog in self._unregistered_cogs:
            await self._register_cog(cog)
        await self.tree.sync(guild=GUILD)
        logger.info("$G$Command tree synced")

    async def on_ready(self) -> None:
        ...

    async def on_interaction(self, interaction: discord.Interaction) -> None:
        custom_id = (
            interaction.data.get("custom_id", "")
            if interaction.data
            else ""
        )
        if custom_id.startswith(LISTING_DESC_PREFIX):
            await self._handle_listing_desc_toggle(interaction, custom_id)
            return
        if custom_id.startswith(THUMBSDOWN_PREFIX):
            listing_id = custom_id[len(THUMBSDOWN_PREFIX) :]
            await self._handle_thumbsdown(interaction, listing_id)
            return
        await super().on_interaction(interaction)

    async def _handle_listing_desc_toggle(
        self, interaction: discord.Interaction, custom_id: str
    ) -> None:
        """Handle Show more/Show less button for listing description."""
        await interaction.response.defer()
        parts = custom_id[len(LISTING_DESC_PREFIX) :].rsplit(":", 1)
        if len(parts) != 2:
            await interaction.followup.send(
                "Invalid button.",
                ephemeral=True,
            )
            return
        listing_id_str, expanded_str = parts
        try:
            expanded = bool(int(expanded_str))
        except ValueError:
            await interaction.followup.send(
                "Invalid button.",
                ephemeral=True,
            )
            return
        listing = await asyncio.to_thread(
            self._searches.get_listing, listing_id_str
        )
        if not listing:
            await interaction.followup.send(
                "Listing no longer available.",
                ephemeral=True,
            )
            return
        new_expanded = not expanded
        desc_display = (
            listing["description"]
            if new_expanded
            else truncate_description(listing["description"])
        )
        product = Product(
            price=listing["price"],
            title=listing["title"],
            description=desc_display,
            location=listing["location"],
            date=listing["date"],
            url=listing["url"],
            img=listing["img"],
        )
        view = product_layout_view(
            product, None, None, desc_display, listing_id_str, new_expanded
        )
        await interaction.edit_original_response(embed=None, view=view)

    async def _handle_thumbsdown(
        self, interaction: discord.Interaction, listing_id: str
    ) -> None:
        """Handle thumbs-down button: open modal for user feedback."""
        listing = await asyncio.to_thread(
            self._searches.get_listing, listing_id
        )
        if not listing:
            await interaction.response.send_message(
                "Listing or watch no longer available.",
                ephemeral=True,
            )
            return

        config = await asyncio.to_thread(
            self._searches.get_config_by_id, listing["search_id"]
        )
        if not config:
            await interaction.response.send_message(
                "Listing or watch no longer available.",
                ephemeral=True,
            )
            return

        is_admin = (
            interaction.guild is not None
            and interaction.user.guild_permissions.administrator
        )
        is_owner = config.owner_id == interaction.user.id if config.owner_id else False
        if not is_admin and not is_owner:
            await interaction.response.send_message(
                "Only admins and the watch owner can use thumbs down.",
                ephemeral=True,
            )
            return

        modal = ThumbsDownModal(self._searches, config)
        await interaction.response.send_modal(modal)

    async def send_embed(
        self,
        embed: discord.Embed,
        channel_id: int,
        thought_trace: str | None = None,
        search_id: str | None = None,
        listing_id: str | None = None,
        view: discord.ui.View | None = None,
    ) -> None:
        channel = self.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        msg = await channel.send(embed=embed, view=view)
        if listing_id:
            self._searches.record_listing_message(msg.id, listing_id, channel_id)
        elif search_id:
            trace = (thought_trace or "").strip() or None
            self.record_listing_metadata(msg.id, channel_id, search_id, trace)

    async def send_layout(
        self,
        view: discord.ui.LayoutView,
        channel_id: int,
        listing_id: str | None = None,
        search_id: str | None = None,
        thought_trace: str | None = None,
    ) -> None:
        """Send a Components V2 LayoutView (no embeds)."""
        channel = self.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        msg = await channel.send(view=view)
        if listing_id:
            self._searches.record_listing_message(msg.id, listing_id, channel_id)
        elif search_id:
            trace = (thought_trace or "").strip() or None
            self.record_listing_metadata(msg.id, channel_id, search_id, trace)



