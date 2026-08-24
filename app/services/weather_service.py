import asyncio
import logging
from datetime import date
from typing import Dict, Tuple
from sqlalchemy.orm import Session
from app.exceptions.places import UserLocationNotFoundError
from app.integrations.open_meteo import OpenMeteoClient
from app.models.user_location import UserLocation
from app.repositories.location_repository import LocationRepository

logger = logging.getLogger(__name__)


class WeatherService:
    def __init__(
        self,
        db: Session,
        open_meteo_client: OpenMeteoClient,
    ) -> None:
        self._db = db
        self._location_repo = LocationRepository(db)
        self._open_meteo_client = open_meteo_client

    def _get_location(self, user_id: int) -> UserLocation:
        location = self._location_repo.get_current_location(user_id)
        if not location:
            raise UserLocationNotFoundError()
        return location

    async def get_weather(
        self,
        user_id: int,
        start_date: date,
        end_date: date,
    ) -> Tuple[Dict, Dict]:
        location = self._get_location(user_id)
        logger.info(
            "Weather requested — user_id=%s lat=%s lon=%s start=%s end=%s",
            user_id,
            location.latitude,
            location.longitude,
            start_date,
            end_date,
        )
        request_args = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        forecast, air_quality = await asyncio.gather(
            self._open_meteo_client.get_forecast(**request_args),
            self._open_meteo_client.get_air_quality(**request_args),
        )
        return forecast, air_quality
