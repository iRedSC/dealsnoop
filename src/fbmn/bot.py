from __future__ import annotations
from typing import Optional, Protocol
from discord.ext import commands
from discord.ext.tasks import Loop
import discord
from fbmn.pickler import ObjectStore
from fbmn.search_config import SearchConfig
from fbmn.logger import logger
import os
import random
import string

def randchar():
    return random.choice(string.ascii_lowercase)


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

    async def setup_hook(self) -> None:
        await self.add_cog(Commands(self))
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


class Commands(commands.Cog):
    def __init__(self, bot: Client):
        self.bot = bot

    async def cog_load(self):
        self.bot.tree.add_command(self.watch, guild=GUILD_ID)
        self.bot.tree.add_command(self.list, guild=GUILD_ID)
        self.bot.tree.add_command(self.unwatch, guild=GUILD_ID)

    @discord.app_commands.command(name="watch", description="Watch for a specific item on various marketplaces.")
    async def watch(self, interaction: discord.Interaction, terms: str, target_price: str = "", context: str = "", city_code: str = '107976589222439', days_listed: int = 1, radius: int = 30, channel_id: str | None = None):
        try:
            formatted_terms = tuple([term.strip() for term in terms.split(",")])
            id = formatted_terms[0].replace(" ", "_")

            for object in self.bot.searches.get_all_objects():
                if object.id == id:
                    id = id + "_"

            config = SearchConfig(id, formatted_terms, int(channel_id) if channel_id else 1412121636815241397, target_price=target_price, context=context, city_code=city_code, days_listed=days_listed, radius=radius)
            self.bot.searches.add_object(config)
            await interaction.response.send_message(f"Added search: {repr(config)}")
        except ValueError:
            await interaction.response.send_message(f"ERRROR: Channel ID not a number.")

    @discord.app_commands.command(name="list", description="List searches currently being watched.")
    async def list(self, interaction: discord.Interaction):
        _list = ""
        for search in self.bot.searches.get_all_objects():
            _list += f"\n`{search.id}` {search.terms}"

        if len(_list) >= 1:
            await interaction.response.send_message(_list)
            return
        await interaction.response.send_message("No watches searches")

    @discord.app_commands.command(name="unwatch", description="Remove watched listing.")
    async def unwatch(self, interaction: discord.Interaction, id: str):
        for search in self.bot.searches.get_all_objects():
            logger.debug(f"Found SearchConfig: $M${print(repr(search))}")

            if search.id == id:
                print("SearchConfig ID $G$matches")
                self.bot.searches.remove_object(search)
                await interaction.response.send_message(f"Removed {search.terms} from watchlist")
                return

        await interaction.response.send_message(f"ID not found.")





