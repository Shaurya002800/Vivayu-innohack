"""Application configuration with safe development defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "VIVAYU Aqua API"
    api_prefix: str = "/api/v1"
    data_mode: str = os.getenv("DATA_MODE", "simulation")
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")


settings = Settings()
