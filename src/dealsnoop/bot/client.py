"""Discord bot client with slash command support."""

from __future__ import annotations

import discord  # type: ignore[import-untyped]
from discord.ext import commands  # type: ignore[import-untyped]

from dealsnoop.config import GUILD_ID
from dealsnoop.logger import logger

GUILD = discord.Object(GUILD_ID)

intents = discord.Intents.default()
intents.message_content = True

class Client(commands.Bot):
    _unregistered_cogs: list[commands.Cog]
    _thought_trace_cache: dict[int, str]

    def __init__(self):
        super().__init__(command_prefix="!@#", intents=intents)
        self._unregistered_cogs = []
        self._thought_trace_cache = {}
    

    def register_cog(self, cog: commands.Cog) -> None:
        self._unregistered_cogs.append(cog)

    async def _register_cog(self, cog: commands.Cog) -> None:
        logger.info("Registering Commands")
        await self.add_cog(cog)
        for command in cog.get_app_commands():
            self.tree.add_command(command, guild=GUILD)
            logger.info(f"Added command '{command.name}'")

    async def setup_hook(self) -> None:
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
    ) -> None:
        channel = self.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        msg = await channel.send(embed=embed)
        if thought_trace:
            self._thought_trace_cache[msg.id] = thought_trace.strip() or "(No thought trace available)"



