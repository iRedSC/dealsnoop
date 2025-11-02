from __future__ import annotations
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
    

    def __init__(self):
        super().__init__(command_prefix="!@#", intents=intents)
        
    


    def register_cog(self, cog: commands.Cog):
        logger.info("Registering Commands (sync)")

        async def _register():
            await self.add_cog(cog)
            for command in cog.get_app_commands():
                self.tree.add_command(command, guild=GUILD_ID)
                logger.info(f"Added command '{command.name}'")

        self.loop.create_task(_register())



    async def setup_hook(self) -> None:
        await self.tree.sync(guild=GUILD_ID)
        logger.info("$G$Command tree synced")

    async def on_ready(self):
        ...

    async def send_embed(self, embed: discord.Embed, channel_id: int) -> None:
        channel = self.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        await channel.send(embed=embed) 







