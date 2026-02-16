"""Browser, cache, and OpenAI client setup."""

import os
import subprocess
import sys
import tempfile

import chromedriver_autoinstaller
from openai import OpenAI
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from dealsnoop.config import FILE_PATH
from dealsnoop.listing_cache import Cache

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument(f"--user-data-dir={tempfile.mkdtemp()}")


def install_chromedriver():
    driver_url = os.getenv("CHROMEDRIVER_URL")

    if driver_url:
        # Manual install using the Chrome for Testing endpoints
        print(f"Installing ChromeDriver manually from {driver_url}")
        subprocess.run([sys.executable, "-m", "chromedriver_autoinstaller", "--download", driver_url], check=False)
    else:
        chromedriver_autoinstaller.install()

install_chromedriver()

API_KEY = os.getenv("OPENAI_KEY")
_chatgpt: OpenAI | None = None


def get_browser() -> webdriver.Chrome:
    return webdriver.Chrome(options=options)


def get_cache(name: str) -> Cache:
    return Cache(f"{FILE_PATH}{name}_cache.txt")


def get_chatgpt() -> OpenAI:
    global _chatgpt
    if _chatgpt is None:
        if not API_KEY:
            raise ValueError("OPENAI_KEY environment variable is required.")
        _chatgpt = OpenAI(api_key=API_KEY)
    return _chatgpt