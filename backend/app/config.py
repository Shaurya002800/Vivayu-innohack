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


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "VIVAYU Aqua API"
    api_prefix: str = "/api/v1"
    data_mode: Literal["simulation", "hardware"] = _data_mode()
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")


settings = Settings()
