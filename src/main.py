from typing import Literal
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
import os
from bs4 import BeautifulSoup
import time
import re
import random
from openai import OpenAI
from dotenv import load_dotenv
from discord_webhook import DiscordWebhook, DiscordEmbed
from listing_cache import Cache
from dataclasses import dataclass

from search_config import SearchConfig

chrome_options = Options()
# chrome_options.add_argument("--headless=new")

load_dotenv()
API_KEY = os.getenv('OPENAI_KEY')

WEBHOOKS = {
    'GOLF_CLUBS': os.getenv('WEBHOOK_GOLF_CLUBS'),
    'JET_SKI': os.getenv('WEBHOOK_JET_SKI'),
    'COMPUTERS': os.getenv('WEBHOOK_COMPUTERS')
}




@dataclass
class Product:
    price: float
    title: str
    description: str
    location: str
    date: str
    url: str
    img: str



def send_webhook(webhook: str, title: str, description: str, img: str, url: str, location: str, date: str, distance: str) -> None:
    webhook = DiscordWebhook(url=WEBHOOKS.get(webhook))

    # create embed object for webhook
    embed = DiscordEmbed(title=title, url=url, description=description, color="03b2f8")

    # # set author
    embed.set_author(name=f"{date}", url=url, icon_url="https://cdn-1.webcatalog.io/catalog/facebook-marketplace/facebook-marketplace-icon-filled-256.png?v=1714774315353")

    # set image
    # embed.set_image(url=img)

    # # set thumbnail
    embed.set_thumbnail(url=img)

    # # set footer
    embed.set_footer(text=f"{location} — {distance}", icon_url="https://cdn-icons-png.flaticon.com/512/1076/1076983.png")

    # # set timestamp (default is now) accepted types are int, float and datetime
    # embed.set_timestamp()

    # # add fields to embed
    # embed.add_embed_field(name="Field 1", value="Lorem ipsum")
    # embed.add_embed_field(name="Field 2", value="dolor sit")

    # add embed object to webhook
    webhook.add_embed(embed)

    webhook.execute()

def get_product_info(browser: webdriver.Chrome, url: str) -> list[str, str]:
    browser.get(url)

    time.sleep(1)
    try:
        close_button = browser.find_element(By.XPATH, '//div[@aria-label="Close" and @role="button"]')
        close_button.click()
        print("Close button clicked!")
    
    except:
        print("Could not find or click the close button!")
        pass

    html = browser.page_source

    soup = BeautifulSoup(html, 'html.parser')

    date = soup.find("abbr")
    if date:
        date = date.text
    else:
        date = "Last 24h"

    try:
        time.sleep(2)
        see_more = browser.find_element(By.CSS_SELECTOR, "div[role='button'].x1i10hfl.xjbqb8w.x1ejq31n.x18oe1m7.x1sy0etr")
        see_more.click()
    except NoSuchElementException:
        print("No 'See More' button found, skipping..")
        
    try:
        description = soup.find('div', class_='xz9dl7a xyri2b xsag5q8 x1c1uobl x126k92a').find('div').find('span', class_='x193iq5w xeuugli x13faqbe x1vvkbs x1xmvt09 x1lliihq x1s928wv xhkezso x1gmr53x x1cpjm7i x1fgarty x1943h6x xudqn12 x3x7a5m x6prxxf xvq8zen xo1l8bm xzsf02u', dir="auto").text
    except AttributeError:
        description = "No Description."
        print("No description found.")


    return [date, description]

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

def validate_quality(title, product, target_price, price, description, context):
    if not target_price:
        target_price = "(no max price)"
    response = client.responses.create(
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


def gather_listings(browser: webdriver.Chrome, search: SearchConfig, sort: str):
    listings = []
    for term in search.terms:
        url = f'https://www.facebook.com/marketplace/{search.city_code}/search?query={term}&sortBy={sort}&daysSinceListed={search.days_listed}&exact=false&radius_in_km={search.radius}'
        browser.get(url)
        html = browser.page_source
        soup = BeautifulSoup(html, 'html.parser')
        listings += soup.find_all('a')
        time.sleep(1)
    return listings
    

def perform_search(browser: webdriver.Chrome, search: SearchConfig, sort: str) -> list[Product]:
    products = []
    # &minPrice={search.min_price}&maxPrice={search.max_price}
    links = gather_listings(browser, search, sort)
    for link in links:
        if not validate_listing(link):
            continue



        text = '\n'.join(link.stripped_strings)
        lines = text.split('\n')

        # Regular expression to find numeric values
        numeric_pattern = re.compile('\d[\d,.]*')
        
        
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
        date, description = get_product_info(browser, url)

        
        if not validate_quality(title, search.terms, search.target_price, price, description, search.context):
            continue

        response = client.responses.create(
        model="gpt-4.1-mini",
        input=f"Roughly how far is {search.city} from {location}? Format as `X mins (Y miles)`, no other words or text.")
        distance = response.output_text

        product=Product(price, title, description, location, date, re.sub(r'\?.*', '', url), img)
        products.append(product)
        send_webhook(search.webhook, product.title, f"$**{product.price}**\n\n{product.description}", product.img, product.url, product.location, product.date, distance)
        time.sleep(random.randint(1, 4))
    cache.save_cache()
    return products


cache = Cache("cache.txt")

client = OpenAI(api_key=API_KEY)

chrome_install = ChromeDriverManager().install()

folder = os.path.dirname(chrome_install)
chromedriver_path = os.path.join(folder, "chromedriver.exe")



def search(term, webhook:str ,target_price=None, context: str | None = None):
    perform_search(browser, SearchConfig(term, target_price=target_price, context=context, webhook=webhook), "creation_time_descend")
    time.sleep(5)
    perform_search(browser, SearchConfig(term, target_price=target_price, context=context, webhook=webhook), "best_match")
    time.sleep(5)


while True:
    browser = webdriver.Chrome(
    service = Service(chromedriver_path), options=chrome_options,
    )
    # search("subaru crosstrek", "", target_price=2500, context="Only looking for the car, other good subaru deals are okay as well. It shouldn't have more than 150k miles on it.")
    search(["gaming monitor", "pc monitor", "computer monitor"], "COMPUTERS", target_price=100, context="I want a good monitor, at least 27 inch, 144hz")
    search(["jet ski", "seadoo ski", "personal watercraft"], "JET_SKI", target_price=1200, context="Something fixable is fine. A pair of jet skis for around 1500 or less is preferrable.")
    search(["set of golf clubs"], "GOLF_CLUBS", target_price=50, context="A nice starter set for an adult")
    # search("sit on top kayak", target_price=50, context="An adult sit on top kayak")
    # search("makita electric tool", context="Avoid Old tools, anything not Makita brand. I want good usable makita tools.")

    browser.close()
    print("Waiting for 5 minutes")
    time.sleep(60*5)


# info panel
# .html-div.x78zum5.xdj266r.x1xegmmw.xat24cr.x13fj5qh.x1y1aw1k.xf159sx.xwib8y2.xmzvs34