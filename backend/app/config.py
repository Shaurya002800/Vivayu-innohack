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
    irrigation_stale_telemetry_after_s: float = float(os.getenv("ZONE_STALE_SECONDS", "10"))
    irrigation_strong_rain_probability_pct: float = float(
        os.getenv("IRRIGATION_STRONG_RAIN_PROBABILITY_PCT", "70")
    )
    irrigation_meaningful_rain_6h_mm: float = float(
        os.getenv("IRRIGATION_MEANINGFUL_RAIN_6H_MM", "2")
    )
    irrigation_high_et0_6h_mm: float = float(
        os.getenv("IRRIGATION_HIGH_ET0_6H_MM", "1")
    )
    irrigation_soil_deficit_weight: float = float(
        os.getenv("IRRIGATION_SOIL_DEFICIT_WEIGHT", "0.60")
    )
    irrigation_critical_moisture_boost: float = float(
        os.getenv("IRRIGATION_CRITICAL_MOISTURE_BOOST", "0.25")
    )
    irrigation_high_stage_sensitivity_boost: float = float(
        os.getenv("IRRIGATION_HIGH_STAGE_SENSITIVITY_BOOST", "0.10")
    )
    irrigation_moderate_stage_sensitivity_boost: float = float(
        os.getenv("IRRIGATION_MODERATE_STAGE_SENSITIVITY_BOOST", "0.05")
    )
    irrigation_high_et0_boost: float = float(os.getenv("IRRIGATION_HIGH_ET0_BOOST", "0.05"))


settings = Settings()
