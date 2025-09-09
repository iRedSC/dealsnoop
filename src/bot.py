from discord.ext import commands
import discord
import os
from dotenv import load_dotenv

from search_config import SearchConfig


load_dotenv()
API_KEY = os.getenv('BOT_TOKEN')

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=">>", intents=intents)


def parse_search_query(query: str) -> SearchConfig:
    parts = query.strip().split()

    terms_str = []
    keyword_args = {}

    # Separate terms from keyword arguments
    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            keyword_args[key.lower()] = value
        else:
            terms_str.append(part)

    terms_list = []
    arg_start_index = len(parts)
    for i, part in enumerate(parts):
        if "=" in part:
            arg_start_index = i
            break
    
    # All parts before the first keyword arg (or all parts if no keyword args) are terms
    terms_phrase = " ".join(parts[:arg_start_index])
    terms_list = [term.strip() for term in terms_phrase.split(",") if term.strip()]

    config = SearchConfig(terms=terms_list)

    if "r" in keyword_args:
        config.radius = int(keyword_args["r"])
    if "p" in keyword_args:
        config.target_price = keyword_args["p"]
    if "d" in keyword_args:
        config.days_listed = int(keyword_args["d"])
    if "c" in keyword_args:
        config.context = keyword_args["c"]
    if "l" in keyword_args:
        # For location, we'll keep it simple for now, as the example shows just 'harrisburg'
        # without a city_code update. A more robust solution would map 'harrisburg' to its city_code.
        config.city = keyword_args["l"].replace("_", " ").title() # Simple title case and space replacement

    return config

@bot.command()
async def find(ctx, terms, *, arg):
    search = parse_search_query(terms, arg)
    await ctx.send(search.__repr__())

bot.run(token=API_KEY)



