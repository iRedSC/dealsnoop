from __future__ import annotations
from typing import Optional, Protocol
from discord.ext import commands
from discord.ext.tasks import Loop
import discord
from dealsnoop.bot.commands import Commands
from dealsnoop.pickler import ObjectStore
from dealsnoop.logger import logger
import os


FILE_PATH = os.getenv('FILE_PATH')
if not FILE_PATH:
    FILE_PATH = ""

GUILD_ID = discord.Object(1411757356894650381)

class Engine(Protocol):
    bot: Optional[Client]
    event_loop: Loop

intents = discord.Intents.default()
intents.message_content = True

class Client(commands.Bot):
    engines: set[Engine]

    def __init__(self, searches: ObjectStore):
        super().__init__(command_prefix="!@#", intents=intents)
        self.searches = searches
        self.engines = set()
    
    def register_engine(self, engine: Engine):
        self.engines.add(engine)
        engine.bot = self

    async def register_cog(self, cog: Commands):
        logger.info("Registering Commands")
        await self.add_cog(Commands(self))
        for command in cog.commands:
            self.tree.add_command(command, guild=GUILD_ID)
            logger.info(f"Added command {command.name}")

    async def setup_hook(self) -> None:
        
        logger.info("$G$Command Cog added")
        await self.tree.sync(guild=GUILD_ID)
        logger.info("$G$Command tree synced")

    async def on_ready(self):
        for engine in self.engines:
            engine.event_loop.start()
        logger.info("$G$Bot started successfully.")

    async def send_embed(self, embed: discord.Embed, channel_id: int) -> None:
        channel = self.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        await channel.send(embed=embed) 







