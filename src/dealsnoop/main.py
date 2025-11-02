from dealsnoop.bot.client import Client
from dotenv import load_dotenv
import os

from dealsnoop.bot.commands import Commands
from dealsnoop.pickler import ObjectStore
from dealsnoop.engines import FacebookEngine
from dealsnoop.snoop import Snoop


load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
FILE_PATH = os.getenv('FILE_PATH')
if not FILE_PATH:
    FILE_PATH = ""


searches = ObjectStore(f"{FILE_PATH}searches.pkl")

bot = Client()
snoop = Snoop(bot, searches)


bot.register_cog(Commands(snoop))
snoop.register_engine(FacebookEngine(snoop))

bot.run(token=BOT_TOKEN) # type: ignore