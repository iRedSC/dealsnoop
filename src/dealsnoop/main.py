"""Entry point for the Facebook Marketplace Discord notifier bot."""

import os

from dealsnoop.bot.client import Client
from dealsnoop.bot.commands import Commands
from dealsnoop.config import FILE_PATH
from dealsnoop.engines import FacebookEngine
from dealsnoop.pickler import ObjectStore
from dealsnoop.snoop import Snoop

BOT_TOKEN = os.getenv("BOT_TOKEN")
searches = ObjectStore(f"{FILE_PATH}searches.pkl")

bot = Client()
snoop = Snoop(bot, searches)


bot.register_cog(Commands(snoop))
snoop.register_engine(FacebookEngine(snoop))

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN environment variable is required.")
bot.run(token=BOT_TOKEN)