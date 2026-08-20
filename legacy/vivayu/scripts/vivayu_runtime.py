"""Runtime utilities shared by the Vivayu dashboard and future ESP32 bridge."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd


RAW_FIELDS = [
    "timestamp_ms",
    "temperature_c",
    "humidity_pct",
    "pressure_pa",
    "gas_resistance_ohm",
    "sraw",
]


class ReadingValidationError(ValueError):
    """Raised when a sensor record cannot safely enter the prediction buffer."""


def parse_sensor_reading(value: str | dict[str, Any]) -> dict[str, float | int]:
    """Parse the ESP32 six-value payload or a JSON sensor object."""
    if isinstance(value, str):
        payload = value.rsplit("->", maxsplit=1)[-1].strip()
        pieces = [piece.strip() for piece in payload.split(",")]
        if len(pieces) != 6:
            raise ReadingValidationError("Expected six comma-separated sensor values.")
        try:
            values = [float(piece) for piece in pieces]
        except ValueError as error:
            raise ReadingValidationError("Every sensor value must be numeric.") from error
        reading: dict[str, float | int] = dict(zip(RAW_FIELDS, values))
    elif isinstance(value, dict):
        missing = [field for field in RAW_FIELDS if field not in value]
        if missing:
            raise ReadingValidationError(f"Missing sensor field(s): {', '.join(missing)}")
        try:
            reading = {field: float(value[field]) for field in RAW_FIELDS}
        except (TypeError, ValueError) as error:
            raise ReadingValidationError("Every sensor field must be numeric.") from error
    else:
        raise ReadingValidationError("Reading must be a CSV payload or a JSON object.")

    reading["timestamp_ms"] = int(reading["timestamp_ms"])
    reading["sraw"] = int(reading["sraw"])
    if reading["timestamp_ms"] < 0:
        raise ReadingValidationError("timestamp_ms cannot be negative.")
    if not -40 <= reading["temperature_c"] <= 85:
        raise ReadingValidationError("temperature_c is outside the BME680 operating range.")
    if not 0 <= reading["humidity_pct"] <= 100:
        raise ReadingValidationError("humidity_pct must be between 0 and 100.")
    if not 30_000 <= reading["pressure_pa"] <= 110_000:
        raise ReadingValidationError("pressure_pa is outside the expected range.")
    if reading["gas_resistance_ohm"] <= 0:
        raise ReadingValidationError("gas_resistance_ohm must be positive.")
    if not 0 <= reading["sraw"] <= 65_535:
        raise ReadingValidationError("sraw must be between 0 and 65535.")
    return reading


def risk_level(probability: float) -> str:
    """Turn a research score into a monitoring level, not a treatment instruction."""
    if probability >= 0.75:
        return "high"
    if probability >= 0.50:
        return "elevated"
    if probability >= 0.35:
        return "watch"
    return "low"


class RollingPredictor:
    """Average five consecutive research-model probabilities for a steadier signal."""

    def __init__(self, model_path: Path, window_size: int = 5) -> None:
        bundle = joblib.load(model_path)
        self.model = bundle["model"]
        self.features = bundle["features"]
        self.model_name = bundle["model_name"]
        self.selection_status = bundle["selection_status"]
        self.window_size = window_size
        self.readings: deque[dict[str, float | int]] = deque(maxlen=window_size)

    def reset(self) -> None:
        self.readings.clear()

    def add_reading(self, value: str | dict[str, Any]) -> dict[str, Any]:
        reading = parse_sensor_reading(value)
        self.readings.append(reading)
        if len(self.readings) < self.window_size:
            return {
                "status": "collecting_readings",
                "readings_received": len(self.readings),
                "readings_needed": self.window_size - len(self.readings),
                "research_only": True,
            }
        return self.predict_current_window()

    def predict_current_window(self) -> dict[str, Any]:
        if len(self.readings) < self.window_size:
            raise ReadingValidationError("A complete five-reading window is required for prediction.")

        frame = pd.DataFrame(list(self.readings))
        probabilities = self.model.predict_proba(frame[self.features])[:, 1]
        mean_probability = float(np.mean(probabilities))
        pattern = "elevated_voc_pattern" if mean_probability >= 0.50 else "baseline_like_pattern"
        decision_confidence = abs(mean_probability - 0.50) * 200
        return {
            "status": "research_monitoring_only",
            "model_name": self.model_name,
            "window_size": self.window_size,
            "pattern": pattern,
            "risk_level": risk_level(mean_probability),
            "disease_pattern_probability": round(mean_probability, 4),
            "confidence_pct": round(decision_confidence, 1),
            "confidence_note": "Decision separation only; not calibrated field confidence.",
            "research_only": self.selection_status == "research_candidate_only",
            "latest_reading": self.readings[-1],
        }
