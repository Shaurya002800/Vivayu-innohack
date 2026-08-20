"""Canonical API schemas introduced milestone-by-milestone."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    data_mode: Literal["simulation", "hardware"]
    schema_version: Literal["1.0"] = "1.0"
