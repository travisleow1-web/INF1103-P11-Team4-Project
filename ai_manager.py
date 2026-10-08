"""ai_manager: API interaction only, no domain logic.

For now this module only fetches weather from Open-Meteo, which needs no API key.
"""

import logging
import time

import requests

log = logging.getLogger("ai_manager")

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

HTTP_TIMEOUT = 20
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds before the first retry, doubled after each failure


def fetch_weather():
    """Fetch the daily precipitation forecast for Singapore (hardcoded coordinates).

    Retries on failure. If every attempt fails the failure is logged and a dict
    with an "error" message is returned instead of raising.
    """
    params = {
        "latitude": 1.266667,
        "longitude": 103.833333,
        "daily": "precipitation_sum",
    }
    delay = RETRY_DELAY

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(WEATHER_URL, params=params, timeout=HTTP_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            log.warning("weather fetch failed, attempt %d/%d: %s", attempt, MAX_RETRIES, exc)
            if attempt == MAX_RETRIES:
                return {"error": str(exc)}
            time.sleep(delay)
            delay *= 2
