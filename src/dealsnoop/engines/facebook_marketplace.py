"""Facebook Marketplace search engine using Selenium and BeautifulSoup."""

import asyncio
from dataclasses import replace
import random
import re

from bs4 import BeautifulSoup, Tag  # type: ignore[import-untyped]
from discord.ext import tasks  # type: ignore[import-untyped]
from selenium.common.exceptions import NoSuchElementException  # type: ignore[import-untyped]
from selenium.webdriver.common.by import By  # type: ignore[import-untyped]

from dealsnoop.bot.embeds import product_embed
from dealsnoop.engines.base import get_browser, get_cache, get_chatgpt
from dealsnoop.listing_log import SearchLogCollector
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

    def _extract_page_location(self, soup: BeautifulSoup) -> str:
        """Extract the marketplace search origin location from the loaded page."""
        strict_selector = (
            "span.x193iq5w.xeuugli.x13faqbe.x1vvkbs.x1xmvt09.x1lliihq.x1s928wv"
            ".xhkezso.x1gmr53x.x1cpjm7i.x1fgarty.x1943h6x.xudqn12.x3x7a5m.x6prxxf"
            ".xvq8zen.x1s688f.x1fey0fg[dir='auto']"
        )
        city_state_pattern = re.compile(r"^[A-Za-z][A-Za-z .'-]+,\s*[A-Za-z][A-Za-z .'-]+$")

        for span in soup.select(strict_selector):
            text = span.get_text(" ", strip=True)
            if city_state_pattern.match(text):
                return text

        for span in soup.select("span[dir='auto']"):
            text = span.get_text(" ", strip=True)
            if not city_state_pattern.match(text):
                continue
            parent_text = span.parent.get_text(" ", strip=True) if span.parent else ""
            if "Within" in parent_text:
                return text

        return "Harrisburg, PA"

    async def gather_listings(self, search: SearchConfig, sort: str) -> tuple[list[Tag], str]:
        listings = []
        origin = "Harrisburg, PA"
        for term in search.terms:
            url = f'https://www.facebook.com/marketplace/{search.city_code}/search?query={term}&sortBy={sort}&daysSinceListed={search.days_listed}&exact=false&radius_in_km={search.radius}'
            await asyncio.to_thread(self.browser.get, url)
            await asyncio.sleep(3)  # Allow JS to render (marketplace listings load dynamically)
            html = await asyncio.to_thread(lambda: self.browser.page_source)
            soup = await asyncio.to_thread(BeautifulSoup, html, "html.parser")
            if origin == "Harrisburg, PA":
                origin = self._extract_page_location(soup)
            listings += soup.find_all('a')
            await asyncio.sleep(1)
        return (listings, origin)

    async def get_location_for_city_code(self, city_code: str) -> str:
        """Resolve a human-readable location name from a Marketplace city code."""
        url = (
            f"https://www.facebook.com/marketplace/{city_code}/search"
            "?query=a&sortBy=creation_time_descend&daysSinceListed=1&exact=false&radius_in_km=30"
        )
        await asyncio.to_thread(self.browser.get, url)
        await asyncio.sleep(3)  # Allow JS to render before reading page source.
        html = await asyncio.to_thread(lambda: self.browser.page_source)
        soup = await asyncio.to_thread(BeautifulSoup, html, "html.parser")
        return self._extract_page_location(soup)
    

    def _title_from_link(self, link: Tag) -> str:
        """Extract a minimal title from a link for logging."""
        text = next(iter(link.stripped_strings), None)
        if text:
            return text[:80] + ("..." if len(text) > 80 else "")
        href = link.get("href") or ""
        return href[:80] + ("..." if len(href) > 80 else "") or "Unknown listing"

    def _url_and_img_from_link(self, link: Tag) -> tuple[str | None, str | None]:
        """Extract listing URL and thumbnail img from a link."""
        href = link.get("href")
        url = f"https://facebook.com{href}" if isinstance(href, str) and href else None
        img_tag = link.find("img")
        img = None
        if img_tag and getattr(img_tag, "attrs", {}).get("src"):
            img = img_tag["src"]
        return (url, img)

    async def perform_search(self, search: SearchConfig, sort: str) -> list[Product]:
        products = []
        feed_channel_id = self.snoop.searches.get_feed_channel_id()
        collector = SearchLogCollector(
            search.id,
            bot=self.snoop.bot,
            feed_channel_id=feed_channel_id,
        )
        collector.start()

        links, origin = await self.gather_listings(search, sort)
        self.snoop.searches.set_location_name(search.city_code, origin)
        if search.location_name != origin:
            self.snoop.searches.add_object(replace(search, location_name=origin))
        logger.info(f"$G${search.id}$W$: found {len(links)} links on page")
        for link in links:
            passed, skip_reason = self.validate_listing(link)
            if not passed:
                # Only log "Cache hit" - real listings we've seen. Skip logging "Invalid listing"
                # (no img/alt/href) since those are page chrome (Terms, Help, Settings, etc.).
                if skip_reason == "Cache hit":
                    collector.add_grouped(self._title_from_link(link), skip_reason)
                continue

            text = '\n'.join(link.stripped_strings)
            lines = [ln.strip() for ln in text.split('\n') if ln.strip()]
            if len(lines) < 2:
                url, img = self._url_and_img_from_link(link)
                collector.add_grouped(
                    self._title_from_link(link), "Malformed listing", url=url, img=img
                )
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

            distance, duration = await get_distance_and_duration(origin, location)
            if distance > search.radius:
                url, img = self._url_and_img_from_link(link)
                collector.add_grouped(
                    title,
                    f"Outside radius ({location} - {round(distance)} mi)",
                    url=url,
                    img=img,
                )
                continue

            numeric_pattern = re.compile(r'\d[\d,.]*')
            price = 0
            for line in lines:
                match = numeric_pattern.search(line)
                if match:
                    price_str = match.group()
                    price = float(price_str.replace(',',''))
                    break

            url = f"https://facebook.com{link.get('href')}"
            img = link.find('img')['src']
            date, description = await self.get_product_info(url)

            passed, thought_trace = await self.validate_quality(
                title, search.terms, search.target_price, price, description, search.context
            )
            if not passed:
                collector.add_individual_skipped(
                    title,
                    f"Quality check failed: {thought_trace[:200]}{'...' if len(thought_trace) > 200 else ''}",
                    url=re.sub(r'\?.*', '', url),
                    price=price,
                    img=img,
                )
                continue

            product = Product(price, title, description, location, date, re.sub(r'\?.*', '', url), img)
            products.append(product)
            collector.add_individual_kept(
                title, "Matched", url=product.url, price=price, img=img
            )

            embed = product_embed(product, distance, duration)
            await self.snoop.bot.send_embed(
                embed, search.channel, thought_trace=thought_trace, search_id=search.id
            )

            self.cache.save_cache()
            await asyncio.sleep(random.randint(1, 4))

        await collector.flush()
        return products
    
    async def run_search_now(self) -> None:
        """Run search immediately for all watched searches, bypassing the timer."""
        await self._run_searches()

    @tasks.loop(minutes=5.0)
    async def event_loop(self):
        await self._run_searches()

    async def _run_searches(self) -> None:
        searches = self.snoop.searches.get_all_objects()
        logger.info(f"$G$Checking sites ({len(searches)} search(es))")
        for search in searches:
            await self.perform_search(search, "creation_time_descend")
            await asyncio.sleep(5)
            await self.perform_search(search, "best_match")
            await asyncio.sleep(5)
        if len(self.cache.urls) >= 2000:
            self.cache.flush(1000)

    def validate_listing(self, link: Tag) -> tuple[bool, str | None]:
        """Returns (passed, skip_reason). skip_reason is None when passed."""
        img_tag = link.find("img")
        if img_tag is None:
            return (False, "Invalid listing (no img)")
        attrs = getattr(img_tag, "attrs", {})
        if "alt" not in attrs:
            return (False, "Invalid listing (no alt)")
        href = link.get("href")
        if not isinstance(href, str):
            return (False, "Invalid listing (no href)")
        listing_id = re.sub(r"/marketplace/item/(\d+)", r"\1", href)
        listing_id = re.sub(r"/.*", "", listing_id)
        if not listing_id or not listing_id.isdigit():
            return (False, "Invalid listing (not marketplace item)")
        if self.cache.contains(listing_id):
            return (False, "Cache hit")
        self.cache.add_url(listing_id)
        return (True, None)

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
        model="gpt-5-mini",
        reasoning={"effort": "medium", "summary": "auto"},
        input=f"""
Evaluate this Facebook Marketplace listing and return True or False.

Criteria:
- The listing must actually be selling '{terms}', not an ISO/WTB post, parts-only, or unrelated item.
- The listing must appear to be a real, usable item — not a scam or broken/for-parts (unless '{context}' says otherwise).
- Price must be at or below ${target_price}. Only allow higher if the item is a genuinely strong deal. Context: '{context}'

Listing:
Title: {title}
Description: {description}
Price: ${price}

Respond with only True or False.
    """)
        text = (response.output_text or "").strip().lower()
        match = re.search(r"\b(true|false)\b", text)
        passed = match.group(1) == "true" if match else True
        thought_trace = ""
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) == "reasoning" and getattr(item, "summary", None):
                parts = [s.text for s in item.summary if getattr(s, "text", None)]
                if parts:
                    thought_trace = "\n".join(parts)
                    break
        return (passed, thought_trace)

