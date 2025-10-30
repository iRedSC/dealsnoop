from dealsnoop.bot import Client
from dotenv import load_dotenv
import os

from dealsnoop.pickler import ObjectStore
from dealsnoop.engines import FacebookEngine


load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
FILE_PATH = os.getenv('FILE_PATH')
if not FILE_PATH:
    FILE_PATH = ""


searches = ObjectStore(f"{FILE_PATH}searches.pkl")


bot = Client(searches)

bot.register_engine(FacebookEngine())

bot.run(token=BOT_TOKEN) # type: ignore