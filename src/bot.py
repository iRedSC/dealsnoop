from discord.ext import commands
import discord
from pickler import ObjectStore
from search_config import SearchConfig
from site_check import SearchEngine
from dotenv import load_dotenv
import os

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

class Client(commands.Bot):
    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents)
        self.db = ObjectStore("searches.pkl")

    async def on_ready(self):
        engine.check_sites.start()
        await self.tree.sync(guild=GUILD_ID)
        print("Bot started successfully.")

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



GUILD_ID = discord.Object(1411757356894650381)


intents = discord.Intents.default()
intents.message_content = True

bot = Client(command_prefix=">>", intents=intents)

engine = SearchEngine(bot, bot.db.get_all_objects())

@bot.tree.command(name="watch", description="Watch for a specific item on various marketplaces.", guild=GUILD_ID)
async def watch(interaction: discord.Interaction, terms: str, target_price: str = "", context: str = "", city_code: str = '107976589222439', days_listed: int = 1, radius: int = 30, channel_id: str | None = None):
    try:

        config = SearchConfig(bot.db.get_all_objects().__len__() + 1, tuple([term.strip() for term in terms.split(",")]), int(channel_id) if channel_id else 1412121636815241397, target_price=target_price, context=context, city_code=city_code, days_listed=days_listed, radius=radius)
        bot.db.add_object(config)
        engine.searches = bot.db.get_all_objects()
        await interaction.response.send_message(f"Added search: {repr(config)}")
    except ValueError:
        await interaction.response.send_message(f"ERRROR: Channel ID not a number.")

@bot.tree.command(name="list", description="List searches currently being watched.", guild=GUILD_ID)
async def list(interaction: discord.Interaction):
    _list = ""
    for search in bot.db.get_all_objects():
        _list += f"\n{search.id}. {search.terms}"

    if len(_list) >= 1:
        await interaction.response.send_message(_list)
        return
    await interaction.response.send_message("No watches searches")

@bot.tree.command(name="unwatch", description="Remove watched listing.", guild=GUILD_ID)
async def unwatch(interaction: discord.Interaction, id: int):
    for search in bot.db.get_all_objects():
        print(repr(search))

        if search.id == id:
            print("ID MATCH")
            bot.db.remove_object(search)
            engine.searches = bot.db.get_all_objects()
            await interaction.response.send_message(f"Removed {search.terms} from watchlist")
            return

    await interaction.response.send_message(f"ID not found.")



bot.run(token=BOT_TOKEN) # type: ignore





