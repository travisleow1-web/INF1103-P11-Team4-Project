import time
import logging
import requests
import validator
from typing import Optional, Dict, Any, List
from config import HTTP_TIMEOUT

log = logging.getLogger("ai_manager")
http_session = requests.Session()

def fetch_weather(lat: float, lon: float) -> Dict[str, Any]:
    return {
        **http_session.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon, "timezone": "auto",
                "forecast_days": 16,
                "hourly": "wind_speed_10m,wind_gusts_10m,pressure_msl,visibility",
                "cell_selection": "sea",
            },
            timeout=HTTP_TIMEOUT,
        ).json()["hourly"],
        **http_session.get(
            "https://marine-api.open-meteo.com/v1/marine",
            params={
                "latitude": lat, "longitude": lon, "timezone": "auto",
                "forecast_days": 16,
                "hourly": "wave_height,swell_wave_height,wave_period",
            },
            timeout=HTTP_TIMEOUT,
        ).json()["hourly"],
    }

def get_shipment_weather(shipment: Dict[str, Any]) -> Dict[str, Any]:
    weather = {}
    for end in ("origin", "destination"):
        try:
            weather[end] = fetch_weather(shipment[f"{end}_lat"], shipment[f"{end}_lon"])
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