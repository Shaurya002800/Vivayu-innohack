"""Application configuration with safe development defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, cast


def _data_mode() -> Literal["simulation", "hardware"]:
    value = os.getenv("DATA_MODE", "simulation").strip().lower()
    if value not in {"simulation", "hardware"}:
        raise ValueError("DATA_MODE must be either 'simulation' or 'hardware'")
    return cast(Literal["simulation", "hardware"], value)


def _optional_float(name: str, default: str) -> float | None:
    value = os.getenv(name, default).strip()
    return float(value) if value else None


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "VIVAYU Aqua API"
    api_prefix: str = "/api/v1"
    data_mode: Literal["simulation", "hardware"] = _data_mode()
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    farm_latitude: float | None = _optional_float("FARM_LATITUDE", "12.9692")
    farm_longitude: float | None = _optional_float("FARM_LONGITUDE", "79.1559")
    weather_provider: str = os.getenv("WEATHER_PROVIDER", "open-meteo")
    weather_api_url: str = os.getenv(
        "WEATHER_API_URL", "https://api.open-meteo.com/v1/forecast"
    )
    weather_cache_minutes: float = float(os.getenv("WEATHER_CACHE_MINUTES", "15"))
    weather_request_timeout_s: float = float(os.getenv("WEATHER_REQUEST_TIMEOUT_SECONDS", "5"))


settings = Settings()
