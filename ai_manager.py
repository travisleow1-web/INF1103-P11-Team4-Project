"""ai_manager: API interaction only, no domain logic.

For now this module only fetches weather from Open-Meteo, which needs no API key.
"""

import logging
import time

import requests

log = logging.getLogger("ai_manager")

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# Edit WEATHER_CONFIG to change what is requested from Open-Meteo. Each list
# holds Open-Meteo variable names (https://open-meteo.com/en/docs). Add a name
# to request it, delete one to drop it. An empty list leaves that group out.
WEATHER_CONFIG = {
    "daily": ["precipitation_sum", "wind_gusts_10m_max", "weather_code"],
    "hourly": [],  # e.g. ["wind_speed_10m", "visibility"]
    "current": [],  # e.g. ["temperature_2m", "wind_speed_10m"]
    "forecast_days": 7,
    "timezone": "auto",
}

# Response blocks copied through to the result when Open-Meteo returns them.
WEATHER_BLOCKS = ("current", "hourly", "daily")

HTTP_TIMEOUT = 20
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds before the first retry, doubled after each failure


def build_weather_params(lat, lon, config=WEATHER_CONFIG):
    """Turn a coordinate pair and a weather config into Open-Meteo query params.

    List values are joined with commas and empty lists are left out, so only
    the variables named in the config are requested.
    """
    params = {"latitude": lat, "longitude": lon}
    for key, value in config.items():
        if isinstance(value, list):
            if value:
                params[key] = ",".join(value)
        else:
            params[key] = value
    return params


def fetch_weather(config=WEATHER_CONFIG):
    """Fetch weather for Singapore (hardcoded coordinates) from Open-Meteo.

    Returns a dict with the source, the coordinates, and each block the config
    asked for (current, hourly, daily) plus its units. If every attempt fails
    the failure is logged and the dict carries an "error" message instead, so
    callers never see an exception.
    """
    lat, lon = 1.266667, 103.833333
    result = {"source": "open-meteo.com", "lat": lat, "lon": lon}
    params = build_weather_params(lat, lon, config)
    delay = RETRY_DELAY

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(WEATHER_URL, params=params, timeout=HTTP_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            break
        except (requests.RequestException, ValueError) as exc:
            log.warning("weather fetch failed, attempt %d/%d: %s", attempt, MAX_RETRIES, exc)
            if attempt == MAX_RETRIES:
                result["error"] = str(exc)
                return result
            time.sleep(delay)
            delay *= 2

    for block in WEATHER_BLOCKS:
        if block in data:
            result[block] = data[block]
            result[block + "_units"] = data.get(block + "_units", {})
    return result
