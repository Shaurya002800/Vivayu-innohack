"""Lock-protected canonical application state and simulation scenario store."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Callable, cast

from app.config import settings
from app.schemas import (
    DataMode,
    MixWaterState,
    PowerState,
    SimulationScenarioSummary,
    SystemState,
    VivayuHealthState,
    WaterSourceState,
    WaterState,
    WeatherState,
    ZoneConfig,
    ZoneId,
    ZoneState,
    ZoneTelemetry,
)
from app.services.crop_service import CropService, crop_service as default_crop_service


SCENARIOS_PATH = Path(__file__).resolve().parent / "data" / "demo_scenarios.json"


class UnknownZoneError(KeyError):
    """Raised when a caller addresses a zone outside the canonical A/B set."""


class UnknownScenarioError(KeyError):
    """Raised when a requested simulation scenario does not exist."""


class SimulationModeDisabledError(RuntimeError):
    """Raised when simulated telemetry is requested while in hardware mode."""


class SimulationWeatherProtectedError(RuntimeError):
    """Raised when live weather attempts to overwrite a simulation scenario."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return a new recursive merge without mutating baseline scenario data."""

    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


class ApplicationStateStore:
    """Own the current state and expose only validated deep copies."""

    def __init__(
        self,
        scenario_path: Path = SCENARIOS_PATH,
        data_mode: DataMode = "simulation",
        *,
        crop_service: CropService = default_crop_service,
        today_provider: Callable[[], date] = date.today,
    ) -> None:
        self._lock = RLock()
        self._data_mode = data_mode
        self._crop_service = crop_service
        self._today_provider = today_provider
        document = json.loads(scenario_path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "1.0":
            raise ValueError("unsupported demo scenario schema_version")

        self._baseline_payload: dict[str, Any] = document["baseline_state"]
        self._scenario_payloads: dict[str, dict[str, Any]] = {}
        self._scenario_summaries: tuple[SimulationScenarioSummary, ...] = tuple(
            SimulationScenarioSummary(
                id=scenario["id"],
                name=scenario["name"],
                description=scenario["description"],
            )
            for scenario in document["scenarios"]
        )
        for scenario in document["scenarios"]:
            scenario_id = scenario["id"]
            if scenario_id in self._scenario_payloads:
                raise ValueError(f"duplicate simulation scenario id: {scenario_id}")
            self._scenario_payloads[scenario_id] = scenario["overrides"]

        self._validate_scenario_document()
        self._state = self._new_initial_state()

    def _validate_scenario_document(self) -> None:
        SystemState.model_validate(
            self._state_payload(
                self._baseline_payload,
                active_scenario_id=None,
                data_mode="simulation",
            )
        )
        for scenario_id, overrides in self._scenario_payloads.items():
            merged = _deep_merge(self._baseline_payload, overrides)
            SystemState.model_validate(
                self._state_payload(
                    merged,
                    active_scenario_id=scenario_id,
                    data_mode="simulation",
                )
            )

    def _state_payload(
        self,
        payload: dict[str, Any],
        *,
        active_scenario_id: str | None,
        data_mode: DataMode | None = None,
    ) -> dict[str, Any]:
        state_payload = deepcopy(payload)
        state_payload["data_mode"] = data_mode or self._data_mode
        state_payload["active_scenario_id"] = active_scenario_id
        state_payload["updated_at"] = _utc_now().isoformat()
        return state_payload

    def _new_initial_state(self) -> SystemState:
        if self._data_mode == "hardware":
            return self._new_safe_hardware_state()
        return self._with_derived_contexts(
            SystemState.model_validate(
                self._state_payload(self._baseline_payload, active_scenario_id=None)
            )
        )

    def _new_safe_hardware_state(self) -> SystemState:
        baseline = SystemState.model_validate(
            self._state_payload(
                self._baseline_payload,
                active_scenario_id=None,
                data_mode="simulation",
            )
        )
        zones: dict[ZoneId, ZoneState] = {}
        for zone_id, baseline_zone in baseline.zones.items():
            zones[zone_id] = ZoneState(
                zone_id=zone_id,
                config=baseline_zone.config,
                telemetry=ZoneTelemetry(zone_id=zone_id),
                growth_stage=(
                    baseline_zone.config.manual_growth_stage
                    if baseline_zone.config.growth_stage_mode == "MANUAL"
                    else None
                ),
                days_after_sowing=None,
                telemetry_age_s=None,
                online=False,
                vivayu_health=VivayuHealthState(
                    available=False,
                    reason="waiting_for_compatible_hardware_telemetry",
                ),
            )
        return self._with_derived_contexts(SystemState(
            data_mode="hardware",
            updated_at=_utc_now(),
            zones=zones,
            water=WaterState(
                fresh=WaterSourceState(),
                marginal=WaterSourceState(),
                mix=MixWaterState(),
            ),
            weather=WeatherState(
                status="OFFLINE",
                stale=True,
                provider=settings.weather_provider,
                provider_status="NOT_FETCHED",
                error="weather forecast has not been fetched",
            ),
            power=PowerState(connected=False),
        ))

    def _with_derived_contexts(self, state: SystemState) -> SystemState:
        zones: dict[ZoneId, ZoneState] = {}
        for zone_id, zone in state.zones.items():
            context = self._crop_service.derive_context(
                zone.config,
                on_date=self._today_provider(),
            )
            zones[zone_id] = zone.model_copy(
                update={
                    "growth_stage": context.growth_stage,
                    "days_after_sowing": context.days_after_sowing,
                    "crop_context": context,
                },
                deep=True,
            )

        weather = state.weather
        if state.data_mode == "simulation":
            age_s = None
            if weather.fetched_at is not None:
                age_s = max(0.0, (_utc_now() - weather.fetched_at).total_seconds())
            weather = weather.model_copy(
                update={
                    "age_s": age_s,
                    "stale": False,
                    "provider": "demo_scenarios",
                    "provider_status": "SIMULATED",
                    "error": None,
                },
                deep=True,
            )
        return state.model_copy(update={"zones": zones, "weather": weather}, deep=True)

    @staticmethod
    def _require_zone(zone_id: str) -> ZoneId:
        if zone_id not in {"A", "B"}:
            raise UnknownZoneError(zone_id)
        return cast(ZoneId, zone_id)

    def get_state(self) -> SystemState:
        with self._lock:
            return self._state.model_copy(deep=True)

    def get_zone(self, zone_id: str) -> ZoneState:
        canonical_zone_id = self._require_zone(zone_id)
        with self._lock:
            return self._state.zones[canonical_zone_id].model_copy(deep=True)

    def list_scenarios(self) -> tuple[SimulationScenarioSummary, ...]:
        return tuple(summary.model_copy(deep=True) for summary in self._scenario_summaries)

    def load_scenario(self, scenario_id: str) -> SystemState:
        if self._data_mode != "simulation":
            raise SimulationModeDisabledError("simulation is disabled in hardware mode")
        try:
            overrides = self._scenario_payloads[scenario_id]
        except KeyError as error:
            raise UnknownScenarioError(scenario_id) from error

        with self._lock:
            merged = _deep_merge(self._baseline_payload, overrides)
            self._state = self._with_derived_contexts(
                SystemState.model_validate(
                    self._state_payload(merged, active_scenario_id=scenario_id)
                )
            )
            return self._state.model_copy(deep=True)

    def reset(self) -> SystemState:
        with self._lock:
            self._state = self._new_initial_state()
            return self._state.model_copy(deep=True)

    def update_zone_config(self, zone_id: str, config: ZoneConfig) -> ZoneState:
        canonical_zone_id = self._require_zone(zone_id)
        if config.zone_id != canonical_zone_id:
            raise ValueError("path zone_id does not match config zone_id")

        with self._lock:
            current_zone = self._state.zones[canonical_zone_id]
            context = self._crop_service.derive_context(
                config,
                on_date=self._today_provider(),
            )
            updated_zone = ZoneState(
                zone_id=canonical_zone_id,
                config=config,
                telemetry=current_zone.telemetry,
                growth_stage=context.growth_stage,
                days_after_sowing=context.days_after_sowing,
                crop_context=context,
                telemetry_age_s=current_zone.telemetry_age_s,
                online=current_zone.online,
                vivayu_health=current_zone.vivayu_health,
            )
            self._replace_zone(canonical_zone_id, updated_zone)
            return updated_zone.model_copy(deep=True)

    def set_manual_stage(self, zone_id: str, growth_stage: str) -> ZoneState:
        canonical_zone_id = self._require_zone(zone_id)
        with self._lock:
            current = self._state.zones[canonical_zone_id]
            config = ZoneConfig.model_validate(
                {
                    **current.config.model_dump(),
                    "growth_stage_mode": "MANUAL",
                    "manual_growth_stage": growth_stage,
                }
            )
            return self.update_zone_config(canonical_zone_id, config)

    def update_zone_telemetry(self, zone_id: str, telemetry: ZoneTelemetry) -> ZoneState:
        canonical_zone_id = self._require_zone(zone_id)
        if telemetry.zone_id != canonical_zone_id:
            raise ValueError("path zone_id does not match telemetry zone_id")

        with self._lock:
            current = self._state.zones[canonical_zone_id]
            updated_zone = ZoneState(
                zone_id=canonical_zone_id,
                config=current.config,
                telemetry=telemetry,
                growth_stage=current.growth_stage,
                days_after_sowing=current.days_after_sowing,
                crop_context=current.crop_context,
                telemetry_age_s=0.0,
                online=True,
                vivayu_health=current.vivayu_health,
            )
            self._replace_zone(canonical_zone_id, updated_zone)
            return updated_zone.model_copy(deep=True)

    def update_weather(self, weather: WeatherState) -> WeatherState:
        with self._lock:
            if self._state.data_mode == "simulation":
                raise SimulationWeatherProtectedError(
                    "live weather cannot overwrite simulation scenario weather"
                )
            self._state = self._state.model_copy(
                update={"weather": weather, "updated_at": _utc_now()},
                deep=True,
            )
            return weather.model_copy(deep=True)

    def _replace_zone(self, zone_id: ZoneId, zone: ZoneState) -> None:
        zones = dict(self._state.zones)
        zones[zone_id] = zone
        self._state = SystemState(
            schema_version=self._state.schema_version,
            data_mode=self._state.data_mode,
            active_scenario_id=self._state.active_scenario_id,
            updated_at=_utc_now(),
            zones=zones,
            water=self._state.water,
            weather=self._state.weather,
            power=self._state.power,
        )


application_state = ApplicationStateStore(data_mode=settings.data_mode)
