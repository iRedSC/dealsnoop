"""Facebook Marketplace search engine using Selenium and BeautifulSoup."""

import asyncio
import random
import re

from bs4 import BeautifulSoup, Tag  # type: ignore[import-untyped]
from discord.ext import tasks  # type: ignore[import-untyped]
from selenium.common.exceptions import NoSuchElementException  # type: ignore[import-untyped]
from selenium.webdriver.common.by import By  # type: ignore[import-untyped]

from dealsnoop.bot.embeds import product_embed
from dealsnoop.engines.base import get_browser, get_cache, get_chatgpt
from dealsnoop.logger import logger
from dealsnoop.maps import get_distance_and_duration
from dealsnoop.product import Product
from dealsnoop.search_config import SearchConfig
from dealsnoop.snoop import Snoop


class FacebookEngine:
    snoop: Snoop

    def __init__(self, snoop):
        self.snoop = snoop
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
        
        except Exception:
            logger.warning("Could not find or click the close button")

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
            lines = [ln.strip() for ln in text.split('\n') if ln.strip()]
            if len(lines) < 2:
                continue

            # Vehicle listings have extra line: [price, title, location, mileage]
            # Regular listings: [price, title, location]
            mileage_pattern = re.compile(
                r'\d[\d,.]*[Kk]?\s*(?:miles?|mi)\b', re.IGNORECASE
            )
            if len(lines) >= 4 and mileage_pattern.search(lines[-1]):
                title = lines[-3]
                location = lines[-2]
            else:
                title = lines[-2] if len(lines) >= 2 else (lines[-1] if lines else "")
                location = lines[-1] if lines else ""

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

            url = f"https://facebook.com{link.get('href')}"
            img = link.find('img')['src']
            date, description = await self.get_product_info(url)
            logger.info("Got date and description")

            
            passed, thought_trace = await self.validate_quality(title, search.terms, search.target_price, price, description, search.context)
            if not passed:
                continue
            logger.info("Quality validated")


            product=Product(price, title, description, location, date, re.sub(r'\?.*', '', url), img)
            products.append(product)

            embed = product_embed(product, distance, duration)

            await self.snoop.bot.send_embed(embed, search.channel, thought_trace=thought_trace)

            self.cache.save_cache()
            await asyncio.sleep(random.randint(1, 4))
        return products
    
    async def run_search_now(self) -> None:
        """Run search immediately for all watched searches, bypassing the timer."""
        await self._run_searches()

    @tasks.loop(minutes=5.0)
    async def event_loop(self):
        await self._run_searches()

    async def _run_searches(self) -> None:
        logger.info("$G$Checking sites")
        for search in self.snoop.searches.get_all_objects():
            await self.perform_search(search, "creation_time_descend")
            await asyncio.sleep(5)
            await self.perform_search(search, "best_match")
            await asyncio.sleep(5)
        if len(self.cache.urls) >= 2000:
            self.cache.flush(1000)

    def validate_listing(self, link: Tag) -> bool:
        img_tag = link.find("img")
        if img_tag is None:
            return False
        attrs = getattr(img_tag, "attrs", {})
        if "alt" not in attrs:
            return False

        href = link.get("href")
        if not isinstance(href, str):
            return False
        listing_id = re.sub(r"/marketplace/item/(\d+)", r"\1", href)
        listing_id = re.sub(r"/.*", "", listing_id)
        if self.cache.contains(listing_id):
            logger.info("Hit listing in cache, skipping")
            return False
        self.cache.add_url(listing_id)
        return True

    async def validate_quality(
        self,
        title: str,
        terms: tuple[str, ...],
        target_price: str | None,
        price: float,
        description: str,
        context: str | None,
    ) -> tuple[bool, str]:
        """Returns (passed, thought_trace)."""
        logger.info("Validating listing quality")
        if not target_price:
            target_price = "(no max price)"
        response = await asyncio.to_thread(self.chatgpt.responses.create,
        model="gpt-4.1-mini",
        input=f"""
    Think it through shortly, then answer with || and 'True' or 'False'. If and once you determine false, stop the thought process and return false.

    Example: "<your thoughts> || True"

    I am searching for '{terms}', for a rough max price of {target_price} (can be slightly higher).
    Additional Context: '{context}'.

    Here is the listing:
    ```
    {title}
    {description}
    ```
    Is the listing what I'm looking for, and is {price} a good price for it?
    If the listing is above the max price but is a very good deal anyway, respond True; only do this if the listing is actually what is being looked for.
    """)
        parts = response.output_text.split("|| ")
        thought_trace = parts[0].strip() if parts else ""
        passed = len(parts) > 1 and parts[-1].lower() == "true"
        logger.info(thought_trace)
        return (passed, thought_trace)

