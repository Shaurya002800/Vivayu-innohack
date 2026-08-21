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


def _optional_int(name: str, default: str = "") -> int | None:
    value = os.getenv(name, default).strip()
    return int(value) if value else None


def _optional_text(name: str, default: str = "") -> str | None:
    return os.getenv(name, default).strip() or None


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "VIVAYU Aqua API"
    api_prefix: str = "/api/v1"
    data_mode: Literal["simulation", "hardware"] = _data_mode()
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    serial_port: str | None = os.getenv("SERIAL_PORT", "").strip() or None
    serial_baud: int = int(os.getenv("SERIAL_BAUD", "115200"))
    serial_read_timeout_s: float = float(
        os.getenv("SERIAL_READ_TIMEOUT_S", "0.25")
    )
    serial_reconnect_interval_s: float = float(
        os.getenv("SERIAL_RECONNECT_INTERVAL_S", "2")
    )
    serial_max_line_bytes: int = int(os.getenv("SERIAL_MAX_LINE_BYTES", "8192"))
    command_ack_timeout_s: float = float(
        os.getenv("COMMAND_ACK_TIMEOUT_S", "1.5")
    )
    command_max_retries: int = int(os.getenv("COMMAND_MAX_RETRIES", "2"))
    command_max_runtime_s: float = float(
        os.getenv("COMMAND_MAX_RUNTIME_S", "120")
    )
    command_history_limit: int = int(os.getenv("COMMAND_HISTORY_LIMIT", "100"))
    farm_latitude: float | None = _optional_float("FARM_LATITUDE", "12.9692")
    farm_longitude: float | None = _optional_float("FARM_LONGITUDE", "79.1559")
    weather_provider: str = os.getenv("WEATHER_PROVIDER", "open-meteo")
    weather_api_url: str = os.getenv(
        "WEATHER_API_URL", "https://api.open-meteo.com/v1/forecast"
    )
    weather_cache_minutes: float = float(os.getenv("WEATHER_CACHE_MINUTES", "15"))
    weather_request_timeout_s: float = float(os.getenv("WEATHER_REQUEST_TIMEOUT_SECONDS", "5"))
    irrigation_stale_telemetry_after_s: float = float(os.getenv("ZONE_STALE_SECONDS", "10"))
    field_telemetry_interval_s: float = float(
        os.getenv("FIELD_TELEMETRY_INTERVAL_S", "1")
    )
    zone_a_soil_dry_raw: int | None = _optional_int("ZONE_A_SOIL_DRY_RAW")
    zone_a_soil_wet_raw: int | None = _optional_int("ZONE_A_SOIL_WET_RAW")
    zone_b_soil_dry_raw: int | None = _optional_int("ZONE_B_SOIL_DRY_RAW")
    zone_b_soil_wet_raw: int | None = _optional_int("ZONE_B_SOIL_WET_RAW")
    zone_a_soil_adc_pin: int | None = _optional_int("ZONE_A_SOIL_ADC_PIN")
    zone_b_soil_adc_pin: int | None = _optional_int("ZONE_B_SOIL_ADC_PIN")
    zone_a_bme280_i2c_address: str | None = _optional_text(
        "ZONE_A_BME280_I2C_ADDRESS"
    )
    zone_b_bme280_i2c_address: str | None = _optional_text(
        "ZONE_B_BME280_I2C_ADDRESS"
    )
    zone_a_i2c_sda_pin: int | None = _optional_int("ZONE_A_I2C_SDA_PIN")
    zone_a_i2c_scl_pin: int | None = _optional_int("ZONE_A_I2C_SCL_PIN")
    zone_b_i2c_sda_pin: int | None = _optional_int("ZONE_B_I2C_SDA_PIN")
    zone_b_i2c_scl_pin: int | None = _optional_int("ZONE_B_I2C_SCL_PIN")
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
    tds_safety_margin_ppm: float | None = _optional_float("TDS_SAFETY_MARGIN_PPM", "50")
    tds_source_stale_minutes: float = float(os.getenv("TDS_SOURCE_STALE_MINUTES", "240"))
    tds_volume_rounding_decimals: int = int(os.getenv("TDS_VOLUME_ROUNDING_DECIMALS", "6"))
    tds_volume_tolerance_ml: float = float(os.getenv("TDS_VOLUME_TOLERANCE_ML", "0.000001"))
    tds_prediction_tolerance_ppm: float = float(
        os.getenv("TDS_PREDICTION_TOLERANCE_PPM", "0.000001")
    )
    allocation_critical_minimum_fraction: float = float(
        os.getenv("ALLOCATION_CRITICAL_MINIMUM_FRACTION", "0.25")
    )
    allocation_rounding_decimals: int = int(
        os.getenv("ALLOCATION_ROUNDING_DECIMALS", "6")
    )
    allocation_volume_tolerance_ml: float = float(
        os.getenv("ALLOCATION_VOLUME_TOLERANCE_ML", "0.000001")
    )
    allocation_ratio_tolerance: float = float(
        os.getenv("ALLOCATION_RATIO_TOLERANCE", "0.000001")
    )
    vivayu_model_path: str | None = (
        os.getenv("VIVAYU_MODEL_PATH", "").strip() or None
    )


settings = Settings()
