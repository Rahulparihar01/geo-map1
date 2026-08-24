import asyncio
import logging
from typing import Any, Dict, Optional

import httpx

from app.exceptions.open_meteo import (
    OpenMeteoAPIError,
    OpenMeteoRateLimitError,
    OpenMeteoTimeoutError,
)

logger = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
FORECAST_HOURLY_VARIABLES = [
    "temperature_2m",
    "precipitation",
    "windspeed_10m",
    "relativehumidity_2m",
    "weathercode",
]
FORECAST_DAILY_VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "weathercode",
]
AIR_QUALITY_HOURLY_VARIABLES = ["pm10", "pm2_5"]


class OpenMeteoClient:
    def __init__(self, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self._http_client = http_client
        self._timeout = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
        self._retry_attempts = 2
        self._backoff_factor = 0.2

    async def _do_request(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        last_error: Optional[Exception] = None
        for attempt in range(self._retry_attempts + 1):
            try:
                if self._http_client is not None:
                    response = await self._http_client.get(url, params=params)
                else:
                    logger.warning(
                        "OpenMeteoClient: no shared HTTP client available, creating per-call client."
                    )
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.get(url, params=params)

                if response.status_code == 429:
                    logger.warning("Open-Meteo rate limit hit: %s", response.text[:200])
                    raise OpenMeteoRateLimitError()

                if response.status_code != 200:
                    logger.error(
                        "Open-Meteo request failed %s: %s",
                        response.status_code,
                        response.text[:500],
                    )
                    raise OpenMeteoAPIError()

                return response.json()
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError) as exc:
                last_error = exc
                if attempt == self._retry_attempts:
                    logger.error(
                        "Open-Meteo request timed out after %s attempts: %s",
                        attempt + 1,
                        exc,
                    )
                    raise OpenMeteoTimeoutError() from exc

                delay = self._backoff_factor * (2**attempt)
                logger.info(
                    "Open-Meteo request failed, retrying in %.1fs (attempt %s): %s",
                    delay,
                    attempt + 1,
                    exc,
                )
                await asyncio.sleep(delay)

        raise OpenMeteoAPIError("Open-Meteo request failed") from last_error

    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": "auto",
            "current_weather": True,
            "hourly": ",".join(FORECAST_HOURLY_VARIABLES),
            "daily": ",".join(FORECAST_DAILY_VARIABLES),
            "start_date": start_date,
            "end_date": end_date,
        }
        logger.info(
            "Open-Meteo forecast request — lat=%s, lon=%s, start=%s, end=%s",
            latitude,
            longitude,
            start_date,
            end_date,
        )
        return await self._do_request(FORECAST_URL, params)

    async def get_air_quality(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": "auto",
            "hourly": ",".join(AIR_QUALITY_HOURLY_VARIABLES),
            "start_date": start_date,
            "end_date": end_date,
        }
        logger.info(
            "Open-Meteo air quality request — lat=%s, lon=%s, start=%s, end=%s",
            latitude,
            longitude,
            start_date,
            end_date,
        )
        return await self._do_request(AIR_QUALITY_URL, params)
