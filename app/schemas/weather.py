from datetime import date
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, model_validator


class WeatherRequest(BaseModel):
    start_date: Optional[date] = Field(
        None,
    )
    end_date: Optional[date] = Field(
        None,
    )

    @model_validator(mode="after")
    def validate_date_range(self):
        if (
            self.end_date is not None
            and self.start_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date cannot be before start_date")
        return self


class WeatherLocationData(BaseModel):
    latitude: float
    longitude: float
    elevation: Optional[float]
    timezone: Optional[str]
    utc_offset_seconds: Optional[int]


class WeatherForecastData(BaseModel):
    hourly: Optional[Dict[str, Any]] = None
    daily: Optional[Dict[str, Any]] = None
    current_weather: Optional[Dict[str, Any]] = None


class AirQualityData(BaseModel):
    hourly: Optional[Dict[str, Any]] = None


class WeatherData(BaseModel):
    location: WeatherLocationData
    forecast: WeatherForecastData
    air_quality: AirQualityData


class WeatherResponse(BaseModel):
    success: bool
    message: str
    data: Optional[WeatherData] = None
