"""Safe boundary around the pinned, research-only legacy Vivayu runtime."""

from __future__ import annotations

import logging
from math import isfinite
from pathlib import Path
import sys
from threading import RLock
from typing import Any, Callable, Protocol, cast

from app.schemas import (
    DataMode,
    VivayuHealthState,
    VivayuSensorConfiguration,
    ZoneId,
    ZoneTelemetry,
)


LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[3]
LEGACY_SCRIPTS_PATH = ROOT / "legacy" / "vivayu" / "scripts"
DEFAULT_MODEL_PATH = (
    ROOT / "legacy" / "vivayu" / "models" / "vivayu_research_candidate.joblib"
)
READINGS_REQUIRED = 5
RESEARCH_BOUNDARY_WARNING = (
    "legacy Vivayu output is a research monitoring signal from a small tomato experiment; "
    "it is not a diagnosis or irrigation trigger"
)
SENSOR_SEMANTICS_WARNING = (
    "BME680 gas resistance and compatible original SGP40-style sraw semantics are required"
)
RESEARCH_SCORE_NOTE = (
    "legacy historical model score exposed as a research separation score; not validated disease probability"
)


class _Predictor(Protocol):
    model_name: str
    window_size: int
    readings: Any

    def add_reading(self, value: dict[str, Any]) -> dict[str, Any]: ...

    def reset(self) -> None: ...


def resolve_model_path(configured_path: str | None) -> Path:
    if not configured_path:
        return DEFAULT_MODEL_PATH
    path = Path(configured_path).expanduser()
    return path if path.is_absolute() else ROOT / path


def _utc_now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def _load_legacy_runtime() -> tuple[type[Any], type[Exception]]:
    """Make pinned legacy modules importable before joblib resolves custom classes."""

    scripts = str(LEGACY_SCRIPTS_PATH)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from vivayu_runtime import ReadingValidationError, RollingPredictor

    return RollingPredictor, ReadingValidationError


class VivayuHealthService:
    """Own one independent legacy rolling predictor and public state per zone."""

    def __init__(
        self,
        model_path: Path = DEFAULT_MODEL_PATH,
        *,
        predictor_factory: Callable[[Path], _Predictor] | None = None,
        now_provider: Callable[[], Any] = _utc_now,
    ) -> None:
        self._lock = RLock()
        self._model_path = model_path
        self._now_provider = now_provider
        self._predictors: dict[ZoneId, _Predictor] = {}
        self._load_errors: dict[ZoneId, str] = {}
        self._reading_validation_error: type[Exception] = ValueError
        self._health: dict[ZoneId, VivayuHealthState] = {}

        if predictor_factory is None:
            try:
                predictor_class, reading_error = _load_legacy_runtime()
                predictor_factory = cast(
                    Callable[[Path], _Predictor], predictor_class
                )
                self._reading_validation_error = reading_error
            except Exception as error:  # pragma: no cover - environment-dependent
                LOGGER.exception("Could not import the pinned legacy Vivayu runtime")
                for zone_id in ("A", "B"):
                    self._load_errors[zone_id] = type(error).__name__

        for zone_id in ("A", "B"):
            if predictor_factory is not None:
                try:
                    self._predictors[zone_id] = predictor_factory(model_path)
                except Exception as error:
                    LOGGER.exception(
                        "Could not load pinned Vivayu model for Zone %s", zone_id
                    )
                    self._load_errors[zone_id] = type(error).__name__
            self._health[zone_id] = self._initial_health(zone_id)

    @staticmethod
    def _require_zone(zone_id: str) -> ZoneId:
        if zone_id not in {"A", "B"}:
            raise ValueError("zone_id must be A or B")
        return cast(ZoneId, zone_id)

    def add_zone_reading(
        self,
        zone_id: str,
        telemetry: ZoneTelemetry,
        sensor_config: VivayuSensorConfiguration,
        *,
        data_mode: DataMode,
    ) -> VivayuHealthState:
        canonical_zone = self._require_zone(zone_id)
        if telemetry.zone_id != canonical_zone:
            raise ValueError("telemetry zone does not match predictor zone")
        source_mode = "SIMULATION" if data_mode == "simulation" else "HARDWARE"
        updated_at = telemetry.received_at or self._now_provider()
        with self._lock:
            compatibility = self._compatibility_failure(
                telemetry,
                sensor_config,
                source_mode=source_mode,
                zone_id=canonical_zone,
                updated_at=updated_at,
            )
            if compatibility is not None:
                self._health[canonical_zone] = compatibility
                return compatibility.model_copy(deep=True)

            predictor = self._predictors.get(canonical_zone)
            if predictor is None:
                state = self._model_unavailable(
                    canonical_zone, source_mode, updated_at=updated_at
                )
                self._health[canonical_zone] = state
                return state.model_copy(deep=True)

            payload = {
                "timestamp_ms": telemetry.timestamp_ms,
                "temperature_c": telemetry.temperature_c,
                "humidity_pct": telemetry.humidity_pct,
                "pressure_pa": telemetry.pressure_pa,
                "gas_resistance_ohm": telemetry.gas_resistance_ohm,
                "sraw": telemetry.sraw,
            }
            numeric_values = tuple(float(value) for value in payload.values())
            if not all(isfinite(value) for value in numeric_values):
                state = self._invalid_reading(
                    canonical_zone,
                    source_mode,
                    "legacy sensor fields must be finite",
                    updated_at=updated_at,
                )
                self._health[canonical_zone] = state
                return state.model_copy(deep=True)
            try:
                result = predictor.add_reading(payload)
            except self._reading_validation_error as error:
                state = self._invalid_reading(
                    canonical_zone,
                    source_mode,
                    str(error),
                    updated_at=updated_at,
                )
            except Exception:
                LOGGER.exception(
                    "Pinned Vivayu inference failed for Zone %s", canonical_zone
                )
                state = VivayuHealthState(
                    status="ERROR",
                    available=False,
                    model_name=getattr(predictor, "model_name", None),
                    readings_received=len(predictor.readings),
                    readings_required=predictor.window_size,
                    readings_in_window=len(predictor.readings),
                    last_updated_at=updated_at,
                    source_mode=source_mode,
                    reason_code="LEGACY_MODEL_UNAVAILABLE",
                    reason="legacy Vivayu inference failed; research monitoring is unavailable",
                    warnings=(RESEARCH_BOUNDARY_WARNING,),
                )
            else:
                state = self._map_legacy_result(
                    predictor,
                    result,
                    source_mode=source_mode,
                    updated_at=updated_at,
                )
            self._health[canonical_zone] = state
            return state.model_copy(deep=True)

    def get_zone_health(self, zone_id: str) -> VivayuHealthState:
        canonical_zone = self._require_zone(zone_id)
        with self._lock:
            return self._health[canonical_zone].model_copy(deep=True)

    def reset_zone_predictor(self, zone_id: str) -> VivayuHealthState:
        canonical_zone = self._require_zone(zone_id)
        with self._lock:
            predictor = self._predictors.get(canonical_zone)
            if predictor is None:
                state = self._model_unavailable(canonical_zone, None)
            else:
                predictor.reset()
                state = VivayuHealthState(
                    status="COLLECTING",
                    available=True,
                    model_name=predictor.model_name,
                    readings_received=0,
                    readings_required=predictor.window_size,
                    readings_in_window=0,
                    reason_code="PREDICTOR_RESET",
                    reason="independent zone predictor window was reset",
                    warnings=(RESEARCH_BOUNDARY_WARNING, SENSOR_SEMANTICS_WARNING),
                )
            self._health[canonical_zone] = state
            return state.model_copy(deep=True)

    def reset_all_predictors(self) -> dict[ZoneId, VivayuHealthState]:
        with self._lock:
            return {
                zone_id: self.reset_zone_predictor(zone_id)
                for zone_id in ("A", "B")
            }

    def _initial_health(self, zone_id: ZoneId) -> VivayuHealthState:
        predictor = self._predictors.get(zone_id)
        if predictor is None:
            return self._model_unavailable(zone_id, None)
        return VivayuHealthState(
            status="COLLECTING",
            available=True,
            model_name=predictor.model_name,
            readings_received=0,
            readings_required=predictor.window_size,
            readings_in_window=0,
            reason_code="COLLECTING_COMPATIBLE_READINGS",
            reason="waiting for compatible legacy-format sensor readings",
            warnings=(RESEARCH_BOUNDARY_WARNING, SENSOR_SEMANTICS_WARNING),
        )

    def _map_legacy_result(
        self,
        predictor: _Predictor,
        result: dict[str, Any],
        *,
        source_mode: str,
        updated_at: Any,
    ) -> VivayuHealthState:
        readings = len(predictor.readings)
        if result.get("status") == "collecting_readings":
            return VivayuHealthState.model_validate(
                {
                    "status": "COLLECTING",
                    "available": True,
                    "model_name": predictor.model_name,
                    "readings_received": result["readings_received"],
                    "readings_required": predictor.window_size,
                    "readings_in_window": readings,
                    "last_updated_at": updated_at,
                    "source_mode": source_mode,
                    "research_only": True,
                    "reason_code": "COLLECTING_COMPATIBLE_READINGS",
                    "reason": (
                        f"collecting compatible readings: {result['readings_received']}"
                        f"/{predictor.window_size}"
                    ),
                    "warnings": [RESEARCH_BOUNDARY_WARNING, SENSOR_SEMANTICS_WARNING],
                }
            )
        return VivayuHealthState.model_validate(
            {
                "status": "READY",
                "available": True,
                "risk_level": result["risk_level"],
                "pattern": result["pattern"],
                "research_score": result.get("disease_pattern_probability"),
                "research_score_note": RESEARCH_SCORE_NOTE,
                "confidence_pct": result.get("confidence_pct"),
                "confidence_note": result.get("confidence_note"),
                "model_name": result.get("model_name", predictor.model_name),
                "readings_received": readings,
                "readings_required": predictor.window_size,
                "readings_in_window": readings,
                "last_updated_at": updated_at,
                "source_mode": source_mode,
                "research_only": True,
                "reason_code": "LEGACY_RESEARCH_WINDOW_READY",
                "reason": "five-reading legacy VOC research-monitoring window is ready",
                "warnings": [RESEARCH_BOUNDARY_WARNING, SENSOR_SEMANTICS_WARNING],
            }
        )

    def _compatibility_failure(
        self,
        telemetry: ZoneTelemetry,
        sensor_config: VivayuSensorConfiguration,
        *,
        source_mode: str,
        zone_id: ZoneId,
        updated_at: Any,
    ) -> VivayuHealthState | None:
        if sensor_config.environment_sensor == "BME280":
            return self._unavailable(
                zone_id,
                source_mode,
                "BME280_GAS_RESISTANCE_UNAVAILABLE",
                "BME280 does not provide the compatible BME680 gas-resistance channel",
                updated_at=updated_at,
            )
        if sensor_config.environment_sensor != "BME680":
            return self._unavailable(
                zone_id,
                source_mode,
                "SENSOR_COMPATIBILITY_NOT_CONFIRMED",
                "compatible BME680 gas-resistance provenance is not confirmed",
                updated_at=updated_at,
            )
        if telemetry.gas_resistance_ohm is None:
            return self._unavailable(
                zone_id,
                source_mode,
                "BME680_GAS_RESISTANCE_CHANNEL_UNAVAILABLE",
                "compatible BME680 gas-resistance channel is not available",
                updated_at=updated_at,
            )
        if sensor_config.voc_sensor == "AGS10":
            return self._unavailable(
                zone_id,
                source_mode,
                "AGS10_NOT_COMPATIBLE_WITH_SGP40_SRAW",
                "AGS10 data cannot be silently substituted for the legacy SGP40-style sraw signal",
                updated_at=updated_at,
            )
        if sensor_config.voc_sensor != "SGP40_COMPATIBLE":
            return self._unavailable(
                zone_id,
                source_mode,
                "SENSOR_COMPATIBILITY_NOT_CONFIRMED",
                "compatible original SGP40-style sraw semantics are not confirmed",
                updated_at=updated_at,
            )
        if telemetry.sraw is None:
            return self._unavailable(
                zone_id,
                source_mode,
                "SGP40_SRAW_CHANNEL_UNAVAILABLE",
                "compatible original SGP40-style sraw channel is not available",
                updated_at=updated_at,
            )
        required = (
            telemetry.timestamp_ms,
            telemetry.temperature_c,
            telemetry.humidity_pct,
            telemetry.pressure_pa,
        )
        if any(value is None for value in required):
            return self._unavailable(
                zone_id,
                source_mode,
                "LEGACY_VIVAYU_SENSOR_SIGNATURE_INCOMPLETE",
                "complete timestamp, temperature, humidity, pressure, gas resistance, and sraw are required",
                updated_at=updated_at,
            )
        return None

    def _invalid_reading(
        self,
        zone_id: ZoneId,
        source_mode: str,
        detail: str,
        *,
        updated_at: Any,
    ) -> VivayuHealthState:
        return self._unavailable(
            zone_id,
            source_mode,
            "LEGACY_READING_INVALID",
            f"legacy sensor reading was rejected: {detail}",
            updated_at=updated_at,
        )

    def _unavailable(
        self,
        zone_id: ZoneId,
        source_mode: str,
        reason_code: str,
        reason: str,
        *,
        updated_at: Any,
    ) -> VivayuHealthState:
        predictor = self._predictors.get(zone_id)
        readings = len(predictor.readings) if predictor is not None else 0
        return VivayuHealthState.model_validate(
            {
                "status": "UNAVAILABLE",
                "available": False,
                "model_name": getattr(predictor, "model_name", None),
                "readings_received": readings,
                "readings_required": getattr(predictor, "window_size", READINGS_REQUIRED),
                "readings_in_window": readings,
                "last_updated_at": updated_at,
                "source_mode": source_mode,
                "research_only": True,
                "reason_code": reason_code,
                "reason": reason,
                "warnings": [RESEARCH_BOUNDARY_WARNING, SENSOR_SEMANTICS_WARNING],
            }
        )

    def _model_unavailable(
        self,
        zone_id: ZoneId,
        source_mode: str | None,
        *,
        updated_at: Any | None = None,
    ) -> VivayuHealthState:
        return VivayuHealthState(
            status="ERROR",
            available=False,
            readings_received=0,
            readings_required=READINGS_REQUIRED,
            readings_in_window=0,
            last_updated_at=updated_at or self._now_provider(),
            source_mode=source_mode,
            reason_code="LEGACY_MODEL_UNAVAILABLE",
            reason="pinned legacy Vivayu research model is unavailable",
            warnings=(RESEARCH_BOUNDARY_WARNING,),
        )
