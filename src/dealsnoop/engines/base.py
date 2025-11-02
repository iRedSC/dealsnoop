from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import chromedriver_autoinstaller
import os
import sys
import subprocess
import tempfile
from dealsnoop.listing_cache import Cache
from openai import OpenAI
from dotenv import load_dotenv


options = Options()
options.add_argument("--headless=new")
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

load_dotenv()
API_KEY = os.getenv('OPENAI_KEY')
FILE_PATH = os.getenv('FILE_PATH')
if not FILE_PATH:
    FILE_PATH = ""



chatgpt = OpenAI(api_key=API_KEY)

def get_browser():
    return webdriver.Chrome(
        options=options,
        )

def get_cache(name: str):
    return Cache(f"{FILE_PATH}{name}_cache.txt")

def get_chatgpt():
    return chatgpt