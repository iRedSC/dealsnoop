from typing import Optional
from dealsnoop.product import Product
import discord

def product_embed(product: Product, distance: Optional[float], duration: Optional[str]):
    embed = discord.Embed(title=product.title, url=product.url, description=f"$**{product.price}**\n\n{product.description}", color=0x03b2f8)
    embed.set_author(name=f"{product.date}", url=product.url, icon_url="https://cdn-1.webcatalog.io/catalog/facebook-marketplace/facebook-marketplace-icon-filled-256.png?v=1714774315353")

    embed.set_thumbnail(url=product.img)
    if distance and duration:
        embed.set_footer(text=f"{product.location} — {round(distance)} mi ({duration})", icon_url="https://cdn-icons-png.flaticon.com/512/1076/1076983.png")
    return embed