import asyncio
from typing import Literal
from discord.ext import tasks
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
import os
from bs4 import BeautifulSoup
import re
import random
from openai import OpenAI
from dotenv import load_dotenv
# from discord_webhook import DiscordWebhook, DiscordEmbed
from listing_cache import Cache
from dataclasses import dataclass

from search_config import SearchConfig

from typing import Protocol

chrome_options = Options()
# chrome_options.add_argument("--headless=new")

load_dotenv()
API_KEY = os.getenv('OPENAI_KEY')
BOT_TOKEN = os.getenv('BOT_TOKEN')

cache = Cache("cache.txt")

chatgpt = OpenAI(api_key=API_KEY)

chrome_install = ChromeDriverManager().install()

folder = os.path.dirname(chrome_install)
chromedriver_path = os.path.join(folder, "chromedriver.exe")




class Bot(Protocol):
    async def send_embed(self, channel_id: int, title: str, description: str, img: str, url: str, location: str, date: str, distance: str) -> None:
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


class SearchEngine:
    def __init__(self, bot: Bot, searches: set[SearchConfig]):
        self.browser = webdriver.Chrome(
        service = Service(chromedriver_path), options=chrome_options,
        )
        self.bot = bot
        self.searches = searches

    async def get_product_info(self, url: str) -> tuple[str, str]:
        await asyncio.to_thread(self.browser.get, url)

        await asyncio.sleep(1)
        try:
            close_button = await asyncio.to_thread(self.browser.find_element, By.XPATH, '//div[@aria-label="Close" and @role="button"]')
            await asyncio.to_thread(close_button.click)
            print("Close button clicked!")
        
        except:
            print("Could not find or click the close button!")
            pass

        html = self.browser.page_source

        soup = BeautifulSoup(html, 'html.parser')

        date = soup.find("abbr")
        if date:
            date = date.text
        else:
            date = "Last 24h"

        try:
            await asyncio.sleep(2)
            see_more = await asyncio.to_thread(self.browser.find_element, By.CSS_SELECTOR, "div[role='button'].x1i10hfl.xjbqb8w.x1ejq31n.x18oe1m7.x1sy0etr")
            await asyncio.to_thread(see_more.click)
        except NoSuchElementException:
            print("No 'See More' button found, skipping..")
            
        try:
            description = soup.find('div', class_='xz9dl7a xyri2b xsag5q8 x1c1uobl x126k92a').find('div').find('span', class_='x193iq5w xeuugli x13faqbe x1vvkbs x1xmvt09 x1lliihq x1s928wv xhkezso x1gmr53x x1cpjm7i x1fgarty x1943h6x xudqn12 x3x7a5m x6prxxf xvq8zen xo1l8bm xzsf02u', dir="auto").text # type: ignore
        except AttributeError:
            description = "No Description."
            print("No description found.")


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
            if not validate_listing(link):
                continue



            text = '\n'.join(link.stripped_strings)
            lines = text.split('\n')

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

            # Extract location
            location = lines[-1]


            url = f"https://facebook.com{link.get('href')}"
            img = link.find('img')['src']
            date, description = await self.get_product_info(url)

            
            if not await validate_quality(title, search.terms, search.target_price, price, description, search.context):
                continue

            response = await asyncio.to_thread(chatgpt.responses.create, 
            model="gpt-4.1-mini",
            input=f"Roughly how far is {search.city} from {location}? Format as `X mins (Y miles)`, no other words or text.")
            distance = response.output_text

            product=Product(price, title, description, location, date, re.sub(r'\?.*', '', url), img)
            products.append(product)
            await self.bot.send_embed(search.channel, product.title, f"$**{product.price}**\n\n{product.description}", product.img, product.url, product.location, product.date, distance)
            await asyncio.sleep(random.randint(1, 4))
        cache.save_cache()
        return products
    
    @tasks.loop(minutes=5.0)
    async def check_sites(self):
        print("checking sites")

        for search in self.searches:
            await self.perform_search(search, "creation_time_descend")
            await asyncio.sleep(5)
            await self.perform_search(search, "best_match")
            await asyncio.sleep(5)

def validate_listing(link):
    img_tag = link.find('img')
    if (img_tag == None) or (img_tag and 'alt' not in img_tag.attrs):
        return False
    
    id = re.sub(r"/marketplace/item/(\d+)", r"\1", link.get('href'))
    id = re.sub(r'/.*', '', id)
    if cache.contains(id):
        print("Hit listing in cache, skipping..")
        return False
    cache.add_url(id)
    return True

async def validate_quality(title, product, target_price, price, description, context):
    if not target_price:
        target_price = "(no max price)"
    response = await asyncio.to_thread(chatgpt.responses.create,
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
    print(f"Is {price} in ballpark of {target_price}:\n{response.output_text}")
    print(f"RESPONSE: {response.output_text.split("|| ")[-1].lower()}")
    
    if response.output_text.split("|| ")[-1].lower() != 'true':
        return
    
    return True










# info panel
# .html-div.x78zum5.xdj266r.x1xegmmw.xat24cr.x13fj5qh.x1y1aw1k.xf159sx.xwib8y2.xmzvs34