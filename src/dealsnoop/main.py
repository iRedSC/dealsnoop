"""Entry point for the Facebook Marketplace Discord notifier bot."""

import os

from dealsnoop.bot.client import Client
from dealsnoop.bot.commands import Commands
from dealsnoop.engines import FacebookEngine
from dealsnoop.snoop import Snoop
from dealsnoop.store import SearchStore

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_URL = os.getenv("DB_URL")

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN environment variable is required.")
if not DB_URL:
    raise SystemExit("DB_URL environment variable is required.")

searches = SearchStore()

bot = Client()
snoop = Snoop(bot, searches)


bot.register_cog(Commands(snoop))
snoop.register_engine(FacebookEngine(snoop))

bot.run(token=BOT_TOKEN)