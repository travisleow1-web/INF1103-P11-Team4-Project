"""ai_manager: API interaction only, no domain logic.

For now this module only fetches weather from Open-Meteo, which needs no API key.
"""

import requests

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_weather():
    """Fetch the daily precipitation forecast for Singapore (hardcoded coordinates)."""
    params = {
        "latitude": 1.266667,
        "longitude": 103.833333,
        "daily": "precipitation_sum",
    }
    response = requests.get(WEATHER_URL, params=params)
    return response.json()
