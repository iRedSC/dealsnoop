"""Discord bot client with slash command support."""

from __future__ import annotations

import asyncio
import re
import uuid
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


async def _get_thumbsdown_suggestion(
    listing: dict, config: SearchConfig
) -> tuple[str, str]:
    """Call AI to suggest two different 1-2 sentence context additions based on disliked listing."""
    terms = config.terms
    target_price = config.target_price or "(no max price)"
    context = config.context or "(none)"
    prompt = f"""The user thumbs-downed this Facebook Marketplace listing. Given the listing and the watch criteria (terms, target price, context), infer why they likely disliked it. Suggest TWO different possible 1-2 sentence additions to the watch's context field that would help the AI filter avoid similar listings in the future. The two options should offer different angles or emphases.

Is the listing WAY too expensive? (If price is close to the target, that's likely not the issue). Is it a variant not specified in the terms or context?

Respond with ONLY these two options in this exact format:
Option 1: [your first suggestion]
Option 2: [your second suggestion]

Watch criteria:
- Terms: {terms}
- Comfortable price: ${target_price}
- Current context: {context}

Listing:
- Title: {listing.get('title', '')}
- Description: {listing.get('description', '')}
- Price: ${listing.get('price', '')}
- Location: {listing.get('location', '')}
"""

    from dealsnoop.engines.base import get_chatgpt

    chatgpt = get_chatgpt()
    response = await asyncio.to_thread(
        chatgpt.responses.create,
        model="gpt-4o-mini",
        input=prompt,
    )
    text = (response.output_text or "").strip()

    # Parse "Option 1: ..." and "Option 2: ..."
    opt1_match = re.search(r"Option\s*1\s*:\s*(.+?)(?=Option\s*2\s*:|$)", text, re.DOTALL | re.IGNORECASE)
    opt2_match = re.search(r"Option\s*2\s*:\s*(.+?)$", text, re.DOTALL | re.IGNORECASE)

    opt1 = opt1_match.group(1).strip() if opt1_match else ""
    opt2 = opt2_match.group(1).strip() if opt2_match else ""

    # Fallback: split by "Option 2" or numbered list
    if not opt1 or not opt2:
        parts = re.split(r"\n\s*Option\s*2\s*:\s*", text, flags=re.IGNORECASE, maxsplit=1)
        if len(parts) >= 2:
            opt1 = re.sub(r"^Option\s*1\s*:\s*", "", parts[0], flags=re.IGNORECASE).strip()
            opt2 = parts[1].strip()
        elif "\n" in text:
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            opt1 = lines[0] if len(lines) > 0 else text
            opt2 = lines[1] if len(lines) > 1 else ""

    return (opt1 or text, opt2 or text)


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


THUMBSDOWN_OPTION1_PREFIX = "thumbsdown_1:"
THUMBSDOWN_OPTION2_PREFIX = "thumbsdown_2:"
THUMBSDOWN_CANCEL_PREFIX = "thumbsdown_cancel:"
THUMBSDOWN_EDIT_PREFIX = "thumbsdown_edit:"


class ThumbsDownFeedbackView(discord.ui.View):
    """View with 1, 2, Cancel, Edit buttons for thumbs-down AI suggestion."""

    def __init__(
        self,
        pending_id: str,
        searches: SearchStore,
    ) -> None:
        super().__init__(timeout=900)  # 15 min
        self._pending_id = pending_id
        self._searches = searches

        self.add_item(
            discord.ui.Button(
                label="1",
                style=discord.ButtonStyle.success,
                custom_id=f"{THUMBSDOWN_OPTION1_PREFIX}{pending_id}",
            )
        )
        self.add_item(
            discord.ui.Button(
                label="2",
                style=discord.ButtonStyle.success,
                custom_id=f"{THUMBSDOWN_OPTION2_PREFIX}{pending_id}",
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Cancel",
                style=discord.ButtonStyle.secondary,
                custom_id=f"{THUMBSDOWN_CANCEL_PREFIX}{pending_id}",
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Edit",
                style=discord.ButtonStyle.primary,
                custom_id=f"{THUMBSDOWN_EDIT_PREFIX}{pending_id}",
            )
        )


class Client(commands.Bot):
    _unregistered_cogs: list[commands.Cog]
    _thumbsdown_pending: dict[str, dict]

    def __init__(self, searches: SearchStore):
        super().__init__(command_prefix="!@#", intents=intents)
        self._unregistered_cogs = []
        self._searches = searches
        self._thumbsdown_pending = {}
    

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
        if custom_id.startswith(THUMBSDOWN_OPTION1_PREFIX):
            await self._handle_thumbsdown_feedback(
                interaction, custom_id[len(THUMBSDOWN_OPTION1_PREFIX) :], "1"
            )
            return
        if custom_id.startswith(THUMBSDOWN_OPTION2_PREFIX):
            await self._handle_thumbsdown_feedback(
                interaction, custom_id[len(THUMBSDOWN_OPTION2_PREFIX) :], "2"
            )
            return
        if custom_id.startswith(THUMBSDOWN_CANCEL_PREFIX):
            await self._handle_thumbsdown_feedback(
                interaction, custom_id[len(THUMBSDOWN_CANCEL_PREFIX) :], "cancel"
            )
            return
        if custom_id.startswith(THUMBSDOWN_EDIT_PREFIX):
            await self._handle_thumbsdown_feedback(
                interaction, custom_id[len(THUMBSDOWN_EDIT_PREFIX) :], "edit"
            )
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
        """Handle thumbs-down button: call AI, show suggestion with Approve/Cancel/Edit."""
        await interaction.response.defer(ephemeral=True)

        listing = await asyncio.to_thread(
            self._searches.get_listing, listing_id
        )
        if not listing:
            await interaction.followup.send(
                "Listing or watch no longer available.",
                ephemeral=True,
            )
            return

        config = await asyncio.to_thread(
            self._searches.get_config_by_id, listing["search_id"]
        )
        if not config:
            await interaction.followup.send(
                "Listing or watch no longer available.",
                ephemeral=True,
            )
            return

        try:
            suggested_1, suggested_2 = await _get_thumbsdown_suggestion(
                listing, config
            )
        except Exception as e:
            logger.exception("Thumbs-down AI suggestion failed: %s", e)
            await interaction.followup.send(
                "Could not generate suggestion. Try updating context manually.",
                ephemeral=True,
            )
            return

        if not (suggested_1 or "").strip() and not (suggested_2 or "").strip():
            await interaction.followup.send(
                "Could not generate suggestion. Try updating context manually.",
                ephemeral=True,
            )
            return

        pending_id = uuid.uuid4().hex[:12]
        self._thumbsdown_pending[pending_id] = {
            "suggested_context_1": (suggested_1 or "").strip(),
            "suggested_context_2": (suggested_2 or "").strip(),
            "search_id": config.id,
            "listing_id": listing_id,
        }

        content_parts = []
        if suggested_1:
            content_parts.append(f"**Option 1:**\n{suggested_1.strip()}")
        if suggested_2:
            content_parts.append(f"**Option 2:**\n{suggested_2.strip()}")
        content = "\n\n".join(content_parts)
        view = ThumbsDownFeedbackView(pending_id, self._searches)
        await interaction.followup.send(
            content,
            ephemeral=True,
            view=view,
        )

    async def _handle_thumbsdown_feedback(
        self,
        interaction: discord.Interaction,
        pending_id: str,
        action: str,
    ) -> None:
        """Handle Approve, Cancel, or Edit for thumbs-down suggestion."""
        pending = self._thumbsdown_pending.pop(pending_id, None)
        if not pending:
            await interaction.response.send_message(
                "This suggestion has expired.",
                ephemeral=True,
            )
            return

        config = await asyncio.to_thread(
            self._searches.get_config_by_id, pending["search_id"]
        )
        if not config:
            await interaction.response.send_message(
                "Watch already removed.",
                ephemeral=True,
            )
            return

        if action == "1":
            suggested = pending.get("suggested_context_1", "")
        elif action == "2":
            suggested = pending.get("suggested_context_2", "")
        else:
            suggested = None

        if suggested is not None:
            existing = config.context or ""
            new_context = (
                f"{existing}\n\n{suggested}"
                if existing
                else suggested
            )
            updated = SearchConfig(
                id=config.id,
                terms=config.terms,
                channel=config.channel,
                city_code=config.city_code,
                location_name=config.location_name,
                target_price=config.target_price,
                days_listed=config.days_listed,
                radius=config.radius,
                context=new_context.strip() or None,
            )
            await asyncio.to_thread(self._searches.add_object, updated)
            await interaction.response.edit_message(
                content="Context updated.",
                view=None,
            )
        elif action == "cancel":
            await interaction.response.edit_message(
                content="Cancelled.",
                view=None,
            )
        else:  # edit
            opt1 = pending.get("suggested_context_1", "")
            opt2 = pending.get("suggested_context_2", "")
            parts = [config.context or ""]
            if opt1:
                parts.append(f"Option 1: {opt1}")
            if opt2:
                parts.append(f"Option 2: {opt2}")
            initial = "\n\n".join(p for p in parts if p)
            modal = UpdateContextModal(
                self._searches, config, initial_context=initial
            )
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



