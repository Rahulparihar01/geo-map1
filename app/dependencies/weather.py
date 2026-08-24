from fastapi import Depends, Request
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.integrations.open_meteo import OpenMeteoClient
from app.services.weather_service import WeatherService


def get_weather_service(
    request: Request,
    db: Session = Depends(get_db),
) -> WeatherService:
    http_open_meteo = getattr(request.app.state, "http_open_meteo", None)
    open_meteo_client = OpenMeteoClient(http_client=http_open_meteo)
    return WeatherService(db=db, open_meteo_client=open_meteo_client)
