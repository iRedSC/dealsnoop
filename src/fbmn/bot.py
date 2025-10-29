from discord.ext import commands
import discord
from fbmn.pickler import ObjectStore
from fbmn.search_config import SearchConfig
from fbmn.site_check import SearchEngine
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


class Client(commands.Bot):
    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents)
        self.db = ObjectStore(f"{FILE_PATH}searches.pkl")
        self.engine = SearchEngine(self, self.db.get_all_objects())

    async def setup_hook(self) -> None:
        await self.add_cog(Commands(self, self.engine))
        logger.info("$G$Command Cog added")
        await self.tree.sync(guild=GUILD_ID)
        logger.info("$G$Command tree synced")

    async def on_ready(self):
        self.engine.check_sites.start()
        logger.info("$G$Bot started successfully.")

    async def send_embed(self, channel_id: int, title: str, description: str, img: str, url: str, location: str, date: str, distance: str) -> None:
        channel = self.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        embed = discord.Embed(title=title, url=url, description=description, color=0x03b2f8)
        embed.set_author(name=f"{date}", url=url, icon_url="https://cdn-1.webcatalog.io/catalog/facebook-marketplace/facebook-marketplace-icon-filled-256.png?v=1714774315353")
        # embed.set_image(url=img)
        embed.set_thumbnail(url=img)
        embed.set_footer(text=f"{location} — {distance}", icon_url="https://cdn-icons-png.flaticon.com/512/1076/1076983.png")
        # embed.set_timestamp()
        # embed.add_embed_field(name="Field 1", value="Lorem ipsum")
        await channel.send(embed=embed) 


class Commands(commands.Cog):
    def __init__(self, bot: Client, engine: SearchEngine):
        self.bot = bot
        self.engine = engine

    async def cog_load(self):
        self.bot.tree.add_command(self.watch, guild=GUILD_ID)
        self.bot.tree.add_command(self.list, guild=GUILD_ID)
        self.bot.tree.add_command(self.unwatch, guild=GUILD_ID)

    @discord.app_commands.command(name="watch", description="Watch for a specific item on various marketplaces.")
    async def watch(self, interaction: discord.Interaction, terms: str, target_price: str = "", context: str = "", city_code: str = '107976589222439', days_listed: int = 1, radius: int = 30, channel_id: str | None = None):
        try:
            formatted_terms = tuple([term.strip() for term in terms.split(",")])
            id = formatted_terms[0].replace(" ", "_")

            for object in self.bot.db.get_all_objects():
                if object.id == id:
                    id = id + "_"

            config = SearchConfig(id, formatted_terms, int(channel_id) if channel_id else 1412121636815241397, target_price=target_price, context=context, city_code=city_code, days_listed=days_listed, radius=radius)
            self.bot.db.add_object(config)
            self.engine.searches = self.bot.db.get_all_objects()
            await interaction.response.send_message(f"Added search: {repr(config)}")
        except ValueError:
            await interaction.response.send_message(f"ERRROR: Channel ID not a number.")

    @discord.app_commands.command(name="list", description="List searches currently being watched.")
    async def list(self, interaction: discord.Interaction):
        _list = ""
        for search in self.bot.db.get_all_objects():
            _list += f"\n`{search.id}.` {search.terms}"

        if len(_list) >= 1:
            await interaction.response.send_message(_list)
            return
        await interaction.response.send_message("No watches searches")

    @discord.app_commands.command(name="unwatch", description="Remove watched listing.")
    async def unwatch(self, interaction: discord.Interaction, id: str):
        for search in self.bot.db.get_all_objects():
            logger.debug(f"Found SearchConfig: $M${print(repr(search))}")

            if search.id == id:
                print("SearchConfig ID $G$matches")
                self.bot.db.remove_object(search)
                self.engine.searches = self.bot.db.get_all_objects()
                await interaction.response.send_message(f"Removed {search.terms} from watchlist")
                return

        await interaction.response.send_message(f"ID not found.")





