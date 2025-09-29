import discord
from fbmn.bot import Client

intents = discord.Intents.default()
intents.message_content = True

bot = Client(command_prefix=">>", intents=intents,)


bot.run(token=BOT_TOKEN) # type: ignore