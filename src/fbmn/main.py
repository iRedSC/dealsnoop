import discord
from fbmn.bot import Client
from dotenv import load_dotenv
import os

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

intents = discord.Intents.default()
intents.message_content = True

bot = Client(command_prefix=">>", intents=intents,)


bot.run(token=BOT_TOKEN) # type: ignore