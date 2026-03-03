"""Discord bot client with slash command support."""

from __future__ import annotations

import asyncio

import discord  # type: ignore[import-untyped]
from discord.ext import commands  # type: ignore[import-untyped]

from dealsnoop.config import GUILD_ID
from dealsnoop.logger import logger
from dealsnoop.store import SearchStore

GUILD = discord.Object(GUILD_ID)

intents = discord.Intents.default()
intents.message_content = True


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
            meta = await asyncio.to_thread(
                self._searches.get_listing_metadata, message.id
            )
            if meta is None:
                await interaction.followup.send(
                    "No metadata for this message.",
                    ephemeral=True,
                )
                return
            thought_trace = meta.get("thought_trace")
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
            terms_escaped = [t.replace('"', '\\"') for t in config.terms]
            terms_str = ", ".join(terms_escaped)
            ctx_escaped = (config.context or "").replace('"', '\\"')
            parts = [
                f'terms:"{terms_str}"',
                f'channel_id:{message.channel_id}',
            ]
            if config.target_price:
                parts.append(f'target_price:{config.target_price}')
            if config.context:
                parts.append(f'context:"{ctx_escaped}"')
            parts.extend([
                f"city_code:{config.city_code}",
                f"days_listed:{config.days_listed}",
                f"radius:{config.radius}",
            ])
            cmd = "/watch " + " ".join(parts)
            await interaction.followup.send(
                f"```\n{cmd}\n```",
                ephemeral=True,
            )

        @self.tree.context_menu(name="Remove watch")
        async def remove_watch(
            interaction: discord.Interaction, message: discord.Message
        ) -> None:
            await interaction.response.defer(ephemeral=True)
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

        self.tree.add_command(show_ai_reasoning, guild=GUILD)
        self.tree.add_command(get_watch_command, guild=GUILD)
        self.tree.add_command(remove_watch, guild=GUILD)
        logger.info("Added commands 'Show AI reasoning', 'Get watch command', 'Remove watch'")
        for cog in self._unregistered_cogs:
            await self._register_cog(cog)
        await self.tree.sync(guild=GUILD)
        logger.info("$G$Command tree synced")

    async def on_ready(self) -> None:
        ...

    async def send_embed(
        self,
        embed: discord.Embed,
        channel_id: int,
        thought_trace: str | None = None,
        search_id: str | None = None,
    ) -> None:
        channel = self.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        msg = await channel.send(embed=embed)
        if search_id:
            trace = (thought_trace or "").strip() or None
            self.record_listing_metadata(msg.id, channel_id, search_id, trace)



