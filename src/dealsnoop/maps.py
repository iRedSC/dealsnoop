"""Google Maps Distance Matrix API integration."""

import os

import aiohttp

from dealsnoop.logger import logger

# load_dotenv is called by config.py, which is imported before this module
MAPS_KEY = os.getenv("GOOGLE_MAPS_KEY")


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
                raise ValueError(f"Google Maps API error: {data}")

            try:
                rows = data.get("rows") or []
                if not rows:
                    logger.warning(
                        "Maps API returned no rows for origin=%r destination=%r. Response: %s",
                        origin, destination, data,
                    )
                    return 0.0, "Unknown"
                elements = rows[0].get("elements") or []
                if not elements:
                    logger.warning(
                        "Maps API returned empty elements for origin=%r destination=%r. Response: %s",
                        origin, destination, data,
                    )
                    return 0.0, "Unknown"
                element = elements[0]
                status = element.get("status")
                if status != "OK":
                    # ZERO_RESULTS, NOT_FOUND, MAX_ROUTE_LENGTH_EXCEEDED, etc.
                    logger.debug(
                        "Maps element status %s for origin=%r destination=%r",
                        status, origin, destination,
                    )
                    return 0.0, "Unknown"
                distance_meters = element["distance"]["value"]
                duration_text = element["duration"]["text"]
                distance_miles = distance_meters / 1609.34
                return distance_miles, duration_text
            except (KeyError, IndexError) as e:
                logger.error(
                    "Maps API returned unexpected structure (missing distance/duration): %s. "
                    "Origin=%r destination=%r. Response: %s",
                    e, origin, destination, data,
                )
                return 0.0, "Unknown"