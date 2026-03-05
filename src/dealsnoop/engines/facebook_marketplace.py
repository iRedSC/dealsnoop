"""Facebook Marketplace search engine using Selenium and BeautifulSoup."""

import asyncio
from dataclasses import replace
import os
import random
import re
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup, Tag  # type: ignore[import-untyped]
from discord.ext import tasks  # type: ignore[import-untyped]
from selenium.common.exceptions import NoSuchElementException  # type: ignore[import-untyped]
from selenium.webdriver.common.by import By  # type: ignore[import-untyped]

from dealsnoop.bot.embeds import product_embed, _format_highlights
from dealsnoop.engines.base import get_browser, get_cache, get_chatgpt
from dealsnoop.exceptions import LocationResolutionError
from dealsnoop.search_config import build_watch_command
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

    def _is_plausible_location(self, text: str) -> bool:
        """Reject product titles etc. Real locations have short city part (e.g. City, ST)."""
        if "," not in text:
            return False
        city_part = text.split(",", 1)[0].strip()
        return len(city_part) <= 45 and len(city_part.split()) <= 6

    def _collect_location_candidate_strings(self, soup: BeautifulSoup) -> list[str]:
        """Find spans matching <text><span>...<span>·</span></span> <text> (location + Within N mi)."""
        within_variants = re.compile(
            r"Within|miles of|km of|radius|rayon|dans un rayon|\d+\s*mi\b|\d+\s*km\b",
            re.IGNORECASE,
        )
        candidates: list[str] = []
        for span in soup.find_all("span", attrs={"dir": "auto"}):
            full_text = span.get_text(" ", strip=True)
            if not within_variants.search(full_text):
                continue
            candidates.append(full_text)
        return candidates

    async def _parse_location_with_ai(self, candidate_strings: list[str]) -> str | None:
        """Use AI to extract only the location from candidate strings. No reasoning model."""
        if not candidate_strings:
            return None
        prompt = """Extract and return ONLY the geographic location (city, state/country) from each text.
Ignore "Within X mi" / "Within X km" / distance phrases. Return just "City, State" or "City, Country".

Examples:
Input: "Carlisle, Pennsylvania · Within 40 mi"
Output: Carlisle, Pennsylvania

Input: "Harrisburg, PA    Within 25 mi"
Output: Harrisburg, PA

Input: "Tokyo, Japan Within 50 km"
Output: Tokyo, Japan

Input: "New York, New York · Within 30 mi"
Output: New York, New York

Now extract the location from this text (return only the location, nothing else):

"""
        for s in candidate_strings[:5]:
            response = await asyncio.to_thread(
                self.chatgpt.chat.completions.create,
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": prompt + s},
                ],
                max_tokens=50,
            )
            text = (response.choices[0].message.content or "").strip()
            if text and self._is_plausible_location(text):
                return text
        return None

    async def _extract_page_location(
        self,
        soup: BeautifulSoup,
        city_code: str = "",
        fallback: str | None = None,
        page_html: str | None = None,
    ) -> str:
        """Extract the marketplace search origin location from the loaded page."""
        city_state_pattern = re.compile(r"^[A-Za-z][A-Za-z .'-]+,\s*[A-Za-z][A-Za-z .'-]+$")
        within_variants = re.compile(
            r"Within|miles of|km of|radius|rayon|dans un rayon",
            re.IGNORECASE,
        )

        for span in soup.find_all("span", attrs={"dir": "auto"}):
            text = span.get_text(" ", strip=True)
            if not within_variants.search(text):
                continue
            city_state_part = (
                re.split(r"\b(?:Within|miles of|km of)\b", text, flags=re.IGNORECASE)[0]
                .strip()
                .rstrip("· ")
            )
            if city_state_pattern.match(city_state_part) and self._is_plausible_location(city_state_part):
                logger.info(
                    "Resolved location %r for city code %s (parsed from span with Within)",
                    city_state_part,
                    city_code or "(unknown)",
                )
                return city_state_part

        candidates = self._collect_location_candidate_strings(soup)
        if candidates:
            ai_location = await self._parse_location_with_ai(candidates)
            if ai_location:
                logger.info(
                    "Resolved location %r for city code %s (via AI extraction)",
                    ai_location,
                    city_code or "(unknown)",
                )
                return ai_location

        if (
            fallback
            and city_state_pattern.match(fallback.strip())
            and self._is_plausible_location(fallback.strip())
        ):
            logger.warning(
                "Location extraction failed; using cached/fallback location %r for city code %s",
                fallback,
                city_code or "(unknown)",
            )
            return fallback.strip()

        spans = soup.find_all("span", attrs={"dir": "auto"})
        matches = [
            s.get_text(" ", strip=True)
            for s in spans
            if city_state_pattern.match(s.get_text(" ", strip=True))
        ]
        with_within = [
            (
                s.get_text(" ", strip=True),
                (s.parent.get_text(" ", strip=True) if s.parent else "")[:100],
            )
            for s in spans
            if within_variants.search(
                s.parent.get_text(" ", strip=True) if s.parent else ""
            )
        ][:5]
        logger.warning(
            "Location extraction failed for city code %s: span[dir=auto] count=%d, "
            "city_state matches=%s, within_parent_samples=%s, page_has_marketplace=%s",
            city_code or "(unknown)",
            len(spans),
            matches[:5] if matches else [],
            with_within,
            "marketplace" in (soup.get_text() if soup else "").lower(),
        )
        if os.environ.get("DEALSNOOP_DEBUG_SAVE_HTML_ON_LOCATION_FAIL") and page_html:
            out_dir = Path("debug_output")
            out_dir.mkdir(exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = out_dir / f"location_fail_{city_code or 'unknown'}_{stamp}.html"
            out_path.write_text(page_html, encoding="utf-8")
            logger.info("Saved page HTML to %s for debugging", out_path)
        raise LocationResolutionError(
            f"Could not resolve location from Marketplace page for city code {city_code or '(unknown)'}"
        )

    async def gather_listings(self, search: SearchConfig, sort: str) -> tuple[list[Tag], str]:
        listings = []
        origin: str | None = None
        for term in search.terms:
            url = f'https://www.facebook.com/marketplace/{search.city_code}/search?query={term}&sortBy={sort}&daysSinceListed={search.days_listed}&exact=false&radius_in_km={search.radius}'
            await asyncio.to_thread(self.browser.get, url)
            await asyncio.sleep(3)  # Allow JS to render (marketplace listings load dynamically)
            html = await asyncio.to_thread(lambda: self.browser.page_source)
            soup = await asyncio.to_thread(BeautifulSoup, html, "html.parser")
            if origin is None:
                fallback = search.location_name or self.snoop.searches.get_location_name(
                    search.city_code
                )
                origin = await self._extract_page_location(
                    soup, search.city_code, fallback=fallback, page_html=html
                )
            listings += soup.find_all('a')
            await asyncio.sleep(1)
        if origin is None:
            raise LocationResolutionError(
                f"Could not resolve location from Marketplace page for city code {search.city_code}"
            )
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
        fallback = self.snoop.searches.get_location_name(city_code)
        return await self._extract_page_location(
            soup, city_code, fallback=fallback, page_html=html
        )
    

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

    def _parse_quality_output(self, raw_output: str) -> tuple[str, str, bool, str | None]:
        """Parse `reasoning || strengths/weaknesses || true/false` output."""
        text = (raw_output or "").strip()
        warnings: list[str] = []
        if not text:
            return ("No reasoning provided.", "No highlights provided.", True, "AI output was empty.")

        parts = [part.strip() for part in text.split("||")]
        if len(parts) != 3:
            warnings.append("Expected 3 sections separated by '||'.")

        has_reasoning_section = len(parts) >= 1 and bool(parts[0])
        has_strengths_section = len(parts) >= 2 and bool(parts[1])
        has_verdict_section = len(parts) >= 3 and bool(parts[2])

        reasoning = parts[0] if has_reasoning_section else "No reasoning provided."
        strengths = parts[1] if has_strengths_section else "No highlights provided."
        verdict_section = parts[2] if len(parts) >= 3 else text

        verdict_match = re.search(r"\b(true|false)\b", verdict_section, re.IGNORECASE)
        if verdict_match:
            passed = verdict_match.group(1).lower() == "true"
        else:
            fallback_match = re.search(r"\b(true|false)\b", text, re.IGNORECASE)
            passed = fallback_match.group(1).lower() == "true" if fallback_match else True
            warnings.append("Missing valid True/False verdict section.")

        if not has_reasoning_section:
            warnings.append("Missing reasoning section.")
        if not has_strengths_section:
            warnings.append("Missing highlights section.")
        if not has_verdict_section:
            warnings.append("Missing verdict section.")

        warning_text = "; ".join(warnings) if warnings else None
        return (reasoning, strengths, passed, warning_text)

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

            passed, thought_trace, strengths_summary, format_warning = await self.validate_quality(
                title, search.terms, search.target_price, price, description, search.context
            )
            if not passed:
                thought_excerpt = f"{thought_trace[:200]}{'...' if len(thought_trace) > 200 else ''}"
                reason_parts = [
                    f"**Highlights:**\n{_format_highlights(strengths_summary)}",
                    f"**Reasoning:** {thought_excerpt}",
                ]
                if format_warning:
                    reason_parts.insert(1, f"WARNING: {format_warning}")
                collector.add_individual_skipped(
                    title,
                    "\n".join(reason_parts),
                    url=re.sub(r'\?.*', '', url),
                    price=price,
                    img=img,
                )
                continue

            product = Product(price, title, description, location, date, re.sub(r'\?.*', '', url), img)
            products.append(product)
            kept_reason_parts = [
                f"**Highlights:**\n{_format_highlights(strengths_summary)}",
                f"**Reasoning:** {thought_trace}",
            ]
            if format_warning:
                kept_reason_parts.insert(1, f"WARNING: {format_warning}")
            kept_reason_parts.append("Matched")
            collector.add_individual_kept(
                title, "\n".join(kept_reason_parts), url=product.url, price=price, img=img
            )

            listing_id = re.search(r"/marketplace/item/(\d+)", product.url)
            listing_id = listing_id.group(1) if listing_id else None
            if listing_id:
                from dealsnoop.bot.embeds import truncate_description, product_layout_view

                watch_cmd = build_watch_command(search, search.channel)
                trace = (thought_trace or "").strip() or None
                self.snoop.searches.insert_listing(
                    listing_id=listing_id,
                    search_id=search.id,
                    title=title,
                    description=description,
                    price=price,
                    location=location,
                    date=product.date,
                    url=product.url,
                    img=img,
                    thought_trace=trace,
                    ai_strengths=strengths_summary,
                    watch_command=watch_cmd,
                )
                truncated_desc = truncate_description(description)
                view = product_layout_view(
                    product,
                    distance,
                    duration,
                    truncated_desc,
                    listing_id,
                    expanded=False,
                    strengths_summary=strengths_summary,
                )
                await self.snoop.bot.send_layout(
                    view, search.channel, listing_id=listing_id
                )
            else:
                embed = product_embed(product, distance, duration)
                await self.snoop.bot.send_embed(
                    embed, search.channel, thought_trace=thought_trace, search_id=search.id
                )

            self.cache.save_cache()
            await asyncio.sleep(random.randint(1, 4))

        await collector.flush()
        return products
    
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
    ) -> tuple[bool, str, str, str | None]:
        """Returns (passed, thought_trace, strengths_summary, format_warning)."""
        logger.info("Validating listing quality")
        if not target_price:
            target_price = "(no max price)"
        response = await asyncio.to_thread(self.chatgpt.responses.create,
        model="gpt-5.1",
        input=f"""
The user searched Facebook Marketplace for '{terms}' and reveived this result. Evaluate it and decide whether it is what the user is looking for, and if it should be shown to them.

Criteria:
- The listing must actually be selling '{terms}', not an ISO/WTB post, parts-only, or unrelated item.
- The listing must appear to be a real, usable item — not a scam or broken/for-parts (unless '{context}' says otherwise).
- Price must be at or below ${target_price}. Only allow higher if the item is a genuinely strong deal. 

The user defined this context, please use it in your evaluation: '{context}'

Listing:
Title: `{title}`
Description: ```{description}```
Price: `${price}`

Respond in exactly this format (single line):
<Short reasoning> || <3 bullet points of listing, i.e. "Oak · Small chip in corner · Just repainted" (Don't include the price or title)> || <True or False>
    """)
        text = (response.output_text or "").strip()
        thought_trace, strengths_summary, passed, format_warning = self._parse_quality_output(text)
        return (passed, thought_trace, strengths_summary, format_warning)

