import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
import requests
from model.port import Port
from model.shipment import Shipment
from .ai_settings import FORECAST_DAYS, HISTORY_DAYS
from .context_provider import ContextProvider

log = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HISTORICAL_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"


class WeatherProvider(ContextProvider):
    """Hourly wind, pressure, visibility and waves at the origin and destination ports (Open-Meteo).

    Future shipments get the 16-day forecast. Shipments that departed within the last
    `history_days` days get historical data for their own dates instead.
    A port whose weather cannot be fetched gets None, and the other port keeps its data.
    """

    def __init__(self, http: Optional[requests.Session] = None, history_days: int = HISTORY_DAYS):
        super().__init__("weather", http)
        self.__history_days = history_days

    def _request(self, shipment: Shipment) -> Dict[str, Any]:
        params = {
            "latitude": shipment.origin.lat,
            "longitude": shipment.origin.lon,
            "timezone": "auto",
            "forecast_days": FORECAST_DAYS,
            "daily": "precipitation_sum, windgusts_10m_max, windspeed_10m_max, pressure_msl_min, pressure_msl_max, visibility_min, weathercode_max",
        }
        return self._get_json("https://api.open-meteo.com/v1/forecast", params)

    def __port_weather_or_none(self, shipment: Shipment, port: Port,
                               window: Optional[Tuple[str, str]]) -> Optional[Dict[str, Any]]:
        try:
            return self.__port_weather(port, window)
        except Exception as error:      # deliberate: one port's failure must not drop the other's data
            log.warning("weather feed failed for %s at %s: %s", shipment.shipment_id, port.code, error)
            return None

    def __history_window(self, shipment: Shipment, today: date) -> Optional[Tuple[str, str]]:
        """(start, end) ISO dates when the shipment departed recently, else None."""
        if today - timedelta(days=self.__history_days) <= shipment.departure < today:
            # The archive API's latest allowed end date is yesterday.
            end = min(shipment.arrival, today - timedelta(days=1))
            return shipment.departure.isoformat(), end.isoformat()
        return None

    def __port_weather(self, port: Port, window: Optional[Tuple[str, str]]) -> Dict[str, Any]:
        common: Dict[str, Any] = {"latitude": port.lat, "longitude": port.lon, "timezone": "auto"}
        if window:
            common.update(start_date=window[0], end_date=window[1])
        else:
            common["forecast_days"] = 16
        weather_params = {**common, "hourly": "wind_speed_10m,wind_gusts_10m,pressure_msl,visibility",
                          "cell_selection": "sea"}
        marine_params = {**common, "hourly": "wave_height,swell_wave_height,wave_period"}
        weather = self._get_json(HISTORICAL_FORECAST_URL if window else FORECAST_URL, weather_params)["hourly"]
        marine = self._get_json(MARINE_URL, marine_params)["hourly"]
        result = {**weather, **marine}
        if window:
            result["historical_weather"] = self._get_json(ARCHIVE_URL, weather_params)["hourly"]
        return result
