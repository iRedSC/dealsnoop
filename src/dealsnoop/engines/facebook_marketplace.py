import asyncio
import discord
from discord.ext import tasks
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

from bs4 import BeautifulSoup
import re
import random

from dataclasses import dataclass
from typing import Optional, Protocol

from dealsnoop.bot import Client
from dealsnoop.engines.base import get_browser, get_cache, get_chatgpt
from dealsnoop.maps import get_distance_and_duration
from dealsnoop.search_config import SearchConfig
from dealsnoop.logger import logger
class Bot(Protocol):
    async def send_embed(self, embed: discord.Embed, channel_id: int) -> None:
        ...
@dataclass
class Product:
    price: float
    title: str
    description: str
    location: str
    date: str
    url: str
    img: str


class FacebookEngine:
    bot: Optional[Client]

    def __init__(self):
        self.browser = get_browser()
        self.cache = get_cache("facebook")
        self.chatgpt = get_chatgpt()


    async def get_product_info(self, url: str) -> tuple[str, str]:
        await asyncio.to_thread(self.browser.get, url)

        await asyncio.sleep(1)
        try:
            close_button = await asyncio.to_thread(self.browser.find_element, By.XPATH, '//div[@aria-label="Close" and @role="button"]')
            await asyncio.to_thread(close_button.click)
            logger.info("Close button clicked")
        
        except:
            logger.warning("Could not find or click the close button")
            pass

        try:
            await asyncio.sleep(2)
            see_more = await asyncio.to_thread(self.browser.find_element, By.CSS_SELECTOR, "div[role='button'].x1i10hfl.xjbqb8w.x1ejq31n.x18oe1m7.x1sy0etr")
            await asyncio.to_thread(see_more.click)
        except NoSuchElementException:
            logger.warning("No 'See More' button found, skipping..")

        html = self.browser.page_source

        soup = await asyncio.to_thread(BeautifulSoup, html, "html.parser")

        date = soup.find("abbr")
        if date:
            date = date.text
        else:
            date = "Last 24h"
        logger.info(f"Date set to '{date}'")

        
        await asyncio.sleep(2)
        try:
            description = soup.find('div', class_='xz9dl7a xyri2b xsag5q8 x1c1uobl x126k92a').find('span', attrs={"dir": "auto"}).text # type: ignore
        except AttributeError as e:
            description = "No Description."
            logger.warning("No description found.")
            logger.error(e)


        return (date, description)
    
    async def gather_listings(self, search: SearchConfig, sort: str):
        listings = []
        for term in search.terms:
            url = f'https://www.facebook.com/marketplace/{search.city_code}/search?query={term}&sortBy={sort}&daysSinceListed={search.days_listed}&exact=false&radius_in_km={search.radius}'
            await asyncio.to_thread(self.browser.get, url)
            html = await asyncio.to_thread(lambda: self.browser.page_source)
            soup = await asyncio.to_thread(BeautifulSoup, html, "html.parser")
            listings += soup.find_all('a')
            await asyncio.sleep(1)
        return listings
    

    async def perform_search(self, search: SearchConfig, sort: str) -> list[Product]:
        products = []
        # &minPrice={search.min_price}&maxPrice={search.max_price}
        links = await self.gather_listings(search, sort)
        for link in links:
            if not self.validate_listing(link):
                continue

            



            text = '\n'.join(link.stripped_strings)
            lines = text.split('\n')

            # Extract location
            location = lines[-1]

            distance, duration = await get_distance_and_duration("Harrisburg, PA", location)
            if distance > search.radius:
                logger.info(f"Skipping listing because it is outside of radius ({location} - {round(distance)} mi)")
                continue

            # Regular expression to find numeric values
            numeric_pattern = re.compile(r'\d[\d,.]*')
            
            
            # Extracting prices
            # Iterate through lines to find the first line with numbers
            price = 0
            for line in lines:
                match = numeric_pattern.search(line)
                if match:    
                    # Extract the first numeric value found
                    price_str = match.group()
                    # Convert price to float (handle commas)
                    price = float(price_str.replace(',',''))
                    break

            # Extract title
            title = lines[-2]




            url = f"https://facebook.com{link.get('href')}"
            img = link.find('img')['src']
            date, description = await self.get_product_info(url)
            logger.info("Got date and description")

            
            if not await self.validate_quality(title, search.terms, search.target_price, price, description, search.context):
                continue
            logger.info("Quality validated")


            product=Product(price, title, description, location, date, re.sub(r'\?.*', '', url), img)
            products.append(product)

            embed = discord.Embed(title=product.title, url=product.url, description=f"$**{product.price}**\n\n{product.description}", color=0x03b2f8)
            embed.set_author(name=f"{product.date}", url=product.url, icon_url="https://cdn-1.webcatalog.io/catalog/facebook-marketplace/facebook-marketplace-icon-filled-256.png?v=1714774315353")

            embed.set_thumbnail(url=product.img)
            embed.set_footer(text=f"{product.location} — {round(distance)} mi ({duration})", icon_url="https://cdn-icons-png.flaticon.com/512/1076/1076983.png")

            if self.bot:
                await self.bot.send_embed(embed, search.channel)
            else:
                logger.error("No bot attached to engine, cannot send embed.")

            self.cache.save_cache()
            await asyncio.sleep(random.randint(1, 4))
        return products
    
    @tasks.loop(minutes=5.0)
    async def event_loop(self):
        logger.info("$G$Checking sites")

        if not self.bot:
            return

        for search in self.bot.searches.get_all_objects():
            await self.perform_search(search, "creation_time_descend")
            await asyncio.sleep(5)
            await self.perform_search(search, "best_match")
            await asyncio.sleep(5)
        if len(self.cache.urls) >= 2000:
            self.cache.flush(1000)

    def validate_listing(self, link):
        img_tag = link.find('img')
        if (img_tag == None) or (img_tag and 'alt' not in img_tag.attrs):
            return False
        
        id = re.sub(r"/marketplace/item/(\d+)", r"\1", link.get('href'))
        id = re.sub(r'/.*', '', id)
        if self.cache.contains(id):
            logger.info("Hit listing in cache, skipping")
            return False
        self.cache.add_url(id)
        return True

    async def validate_quality(self, title, product, target_price, price, description, context):
        logger.info("Validating listing quality")
        if not target_price:
            target_price = "(no max price)"
        response = await asyncio.to_thread(self.chatgpt.responses.create,
        model="gpt-4.1-mini",
        input=f"""
    Think it through shortly, then answer with || and 'True' or 'False'. If and once you determine false, stop the thought process and return false.

    Example: "<your thoughts> || True"

    I am searching for '{product}', for a rough max price of {target_price} (can be slightly higher).
    Additional Context: '{context}'.

    Here is the listing:
    ```
    {title}
    {description}
    ```
    Is the listing what I'm looking for, and is {price} a good price for it?
    If the listing is above the max price but is a very good deal anyway, respond True; only do this if the listing is actually what is being looked for.
    """)
        logger.info(f"{response.output_text.split("|| ")[0]}")
        
        if response.output_text.split("|| ")[-1].lower() != 'true':
            return
        
        return True

