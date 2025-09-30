import aiohttp
from dotenv import load_dotenv
import os

load_dotenv()
MAPS_KEY = os.getenv('GOOGLE_MAPS_KEY')

async def get_distance_and_duration(origin: str, destination: str) -> tuple[float, str]:
    base_url = "https://maps.googleapis.com/maps/api/distancematrix/json"

    params = {
        "origins": origin,
        "destinations": destination,
        "units": "imperial",  # "imperial" for miles
        "key": MAPS_KEY,
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(base_url, params=params) as response:
            data = await response.json()

            if response.status != 200 or data.get("status") != "OK":
                raise Exception("Error fetching data from Google Maps API:", data)

            try:
                element = data["rows"][0]["elements"][0]
                distance_meters = element["distance"]["value"]  # e.g., "245 mi"
                duration_text = element["duration"]["text"]  # e.g., "4 hours 12 mins"

                distance_miles = distance_meters / 1609.34
                return distance_miles, duration_text
            except (KeyError, IndexError):
                raise Exception("Invalid response structure:", data)