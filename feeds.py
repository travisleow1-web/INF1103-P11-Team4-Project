import time
import logging
import requests
import validator
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from config import HTTP_TIMEOUT, HISTORY_DAYS

log = logging.getLogger("ai_manager")
http_session = requests.Session()

def history_window(shipment: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """(start, end) ISO dates if the shipment departed within the last HISTORY_DAYS days, else None."""
    try:
        start, end = (datetime.strptime(str(shipment[k]).strip(), "%d/%m/%Y").date()
                      for k in ("departure_time", "arrival_time"))
    except (KeyError, ValueError):
        return None
    today = date.today()
    if today - timedelta(days=HISTORY_DAYS) <= start < today:
        return start.isoformat(), min(end, today).isoformat()
    return None

def fetch_weather(lat: float, lon: float, window: Optional[Tuple[str, str]] = None) -> Dict[str, Any]:
    """Hourly wind/pressure/visibility and waves. Raises on failure.

    Without a window: the next 16 days. With a (start, end) window: the historical forecast API plus
    waves for those dates, and the historical weather (reanalysis) API under "historical_weather"."""
    common = {"latitude": lat, "longitude": lon, "timezone": "auto"}
    if window:
        common.update(start_date=window[0], end_date=window[1])
    else:
        common["forecast_days"] = 16
    weather_params = {**common, "hourly": "wind_speed_10m,wind_gusts_10m,pressure_msl,visibility",
                      "cell_selection": "sea"}
    forecast_url = ("https://historical-forecast-api.open-meteo.com/v1/forecast" if window
                    else "https://api.open-meteo.com/v1/forecast")
    weather = http_session.get(forecast_url, params=weather_params, timeout=HTTP_TIMEOUT)
    marine = http_session.get("https://marine-api.open-meteo.com/v1/marine", timeout=HTTP_TIMEOUT,
                              params={**common, "hourly": "wave_height,swell_wave_height,wave_period"})
    result = {**weather.json()["hourly"], **marine.json()["hourly"]}
    if window:
        result["historical_weather"] = http_session.get(
            "https://archive-api.open-meteo.com/v1/archive", params=weather_params, timeout=HTTP_TIMEOUT
        ).json()["hourly"]
    return result

def get_shipment_weather(shipment: Dict[str, Any]) -> Dict[str, Any]:
    weather = {}
    for end in ("origin", "destination"):
        try:
            weather[end] = fetch_weather(shipment[f"{end}_lat"], shipment[f"{end}_lon"], history_window(shipment))
        except Exception as exc:
            log.warning("weather feed failed for %s %s: %s", shipment.get("shipment_id"), end, exc)
            weather[end] = None
    return weather

def fetch_news(shipment: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    time.sleep(5)
    try:
        return [
            {"title": a["title"], "seen": a["seendate"]}
            for a in http_session.get(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params={
                    "query": (
                        f'("{validator.PORTS_BY_CODE[shipment["origin_port"]]["name"]}"'
                        f' OR "{validator.PORTS_BY_CODE[shipment["destination_port"]]["name"]}")'
                        ' (piracy OR "armed robbery" OR "port congestion" OR strike OR protest OR unrest)'
                        ' sourcelang:english'
                    ),
                    "mode": "ArtList",
                    "maxrecords": 8,
                    "format": "json",
                    "timespan": "3d",
                },
                timeout=HTTP_TIMEOUT,
            ).json().get("articles", [])
        ]
    except Exception as exc:
        log.warning("news feed failed for %s: %s", shipment.get("shipment_id"), exc)
        return None