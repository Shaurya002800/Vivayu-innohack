"""Canonical weather state and explicit provider refresh endpoints."""

from fastapi import APIRouter

from app.schemas import WeatherState
from app.services.weather_service import weather_service
from app.state import application_state


router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("", response_model=WeatherState)
def get_weather() -> WeatherState:
    """Return canonical state without causing a network request."""

    return application_state.get_state().weather


@router.post("/refresh", response_model=WeatherState)
def refresh_weather() -> WeatherState:
    """Refresh live weather only when the application is in hardware mode."""

    state = application_state.get_state()
    if state.data_mode == "simulation":
        return state.weather
    weather = weather_service.get_forecast(force_refresh=True)
    return application_state.update_weather(weather)
