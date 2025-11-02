from __future__ import annotations
from typing import Protocol
from dealsnoop.bot.embeds import search_config_embed
from dealsnoop.pickler import ObjectStore
from dealsnoop.search_config import SearchConfig
from discord.ext import commands
import discord
from dealsnoop.logger import logger

GUILD_ID = discord.Object(1411757356894650381)

class Client(Protocol):
    searches: ObjectStore

    async def register_cog(self, cog: Commands):
        ...


class Commands(commands.Cog):
    def __init__(self, bot: Client):
        self.bot = bot
        self.commands = [
            getattr(self, name)
            for name in dir(self)
            if isinstance(getattr(self, name), discord.app_commands.Command)
        ]

    async def cog_load(self):
        await self.bot.register_cog(self)

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
            embed = search_config_embed(config)
            await interaction.response.send_message(embed=embed)
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