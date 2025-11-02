from typing import Optional
from dealsnoop.product import Product
import discord

from dealsnoop.search_config import SearchConfig

def product_embed(product: Product, distance: Optional[float], duration: Optional[str]):
    embed = discord.Embed(title=product.title, url=product.url, description=f"$**{product.price}**\n\n{product.description}", color=0x03b2f8)
    embed.set_author(name=f"{product.date}", url=product.url, icon_url="https://cdn-1.webcatalog.io/catalog/facebook-marketplace/facebook-marketplace-icon-filled-256.png?v=1714774315353")

    embed.set_thumbnail(url=product.img)
    if distance and duration:
        embed.set_footer(text=f"{product.location} — {round(distance)} mi ({duration})", icon_url="https://cdn-icons-png.flaticon.com/512/1076/1076983.png")
    return embed

def search_config_embed(config: SearchConfig):
    embed = discord.Embed(title=f"Successfully added search: {config.id}", color=0x03b2f8)
    # embed.set_author(name=f"{product.date}",)
    embed.add_field(name="Terms", value="\n".join([f"`{term}`" for term in config.terms]))
    embed.add_field(name="Channel", value=f"<#{config.channel}>")
    embed.add_field(name="City", value=config.city)
    embed.add_field(name="Target Price", value=f"${config.target_price}")
    embed.add_field(name="Radius", value=f"{config.radius} mi")
    embed.add_field(name="Context", value=config.context)

    return embed
