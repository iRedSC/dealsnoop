from __future__ import annotations
import asyncio
from discord.ext import commands
import discord
from dealsnoop.logger import logger
import os


FILE_PATH = os.getenv('FILE_PATH')
if not FILE_PATH:
    FILE_PATH = ""

GUILD_ID = discord.Object(1411757356894650381)



intents = discord.Intents.default()
intents.message_content = True

class Client(commands.Bot):
    _unregistered_cogs: list[commands.Cog]

    def __init__(self):
        super().__init__(command_prefix="!@#", intents=intents)
        self._unregistered_cogs = []
    

    def register_cog(self, cog: commands.Cog):
        self._unregistered_cogs.append(cog)


    async def _register_cog(self, cog: commands.Cog):
        logger.info("Registering Commands")
        await self.add_cog(cog)
        for command in cog.get_app_commands():
            self.tree.add_command(command, guild=GUILD_ID)
            logger.info(f"Added command '{command.name}'")



    async def setup_hook(self) -> None:
        for cog in self._unregistered_cogs:
            await self._register_cog(cog)
        await self.tree.sync(guild=GUILD_ID)
        logger.info("$G$Command tree synced")

    async def on_ready(self):
        ...

    async def send_embed(self, embed: discord.Embed, channel_id: int) -> None:
        channel = self.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        await channel.send(embed=embed) 







