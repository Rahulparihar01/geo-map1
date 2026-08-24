import logging
from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, Request
from app.dependencies.auth import get_current_user
from app.dependencies.weather import get_weather_service
from app.exceptions.places import UserLocationNotFoundError
from app.models.user import User
from app.schemas.weather import (
    AirQualityData,
    WeatherForecastData,
    WeatherData,
    WeatherLocationData,
    WeatherRequest,
    WeatherResponse,
)
from app.services.weather_service import WeatherService
from app.core.rate_limiter import shared_limiter as limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/weather", tags=["Weather"])


def _normalize_dates(request: WeatherRequest) -> tuple[date, date]:
    today = datetime.now(timezone.utc).date()
    start_date = request.start_date or today
    end_date = request.end_date or start_date
    return start_date, end_date


def _build_location_data(raw: dict) -> WeatherLocationData:
    return WeatherLocationData(
        latitude=raw.get("latitude"),
        longitude=raw.get("longitude"),
        elevation=raw.get("elevation"),
        timezone=raw.get("timezone"),
        utc_offset_seconds=raw.get("utc_offset_seconds"),
    )


@router.post("", response_model=WeatherResponse)
@limiter.limit("10/minute")
async def get_weather(
    request: Request,
    payload: WeatherRequest,
    current_user: User = Depends(get_current_user),
    service: WeatherService = Depends(get_weather_service),):
    start_date, end_date = _normalize_dates(payload)
    logger.info(
        "weather — user_id=%s start_date=%s end_date=%s",
        current_user.id,
        start_date,
        end_date,
    )

    try:
        forecast_data, air_quality_data = await service.get_weather(
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
        )
    except UserLocationNotFoundError:
        logger.error(
            "weather failed — user_id=%s no saved location", current_user.id
        )
        raise

    return WeatherResponse(
        success=True,
        message="Weather and air quality data retrieved successfully",
        data=WeatherData(
            location=_build_location_data(forecast_data),
            forecast=WeatherForecastData(
                hourly=forecast_data.get("hourly"),
                daily=forecast_data.get("daily"),
                current_weather=forecast_data.get("current_weather"),
            ),
            air_quality=AirQualityData(
                hourly=air_quality_data.get("hourly"),
            ),
        ),
    )
