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
    ControllerState,
    DataMode,
    HardwareTelemetryMetadata,
    MixWaterState,
    PowerState,
    PrototypeIrrigationParameters,
    PrototypeWaterQualityParameters,
    SerialConnectionState,
    SimulationScenarioSummary,
    SystemState,
    VivayuHealthState,
    WaterSourceState,
    WaterSourceId,
    WaterSourceUpdateRequest,
    WaterState,
    WeatherState,
    ZoneConfig,
    ZoneId,
    ZoneState,
    ZoneTelemetry,
)
from app.services.crop_service import CropService, crop_service as default_crop_service
from app.services.vivayu_health_service import (
    VivayuHealthService,
    resolve_model_path,
)


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
        vivayu_service: VivayuHealthService | None = None,
        today_provider: Callable[[], date] = date.today,
        now_provider: Callable[[], datetime] = _utc_now,
        stale_telemetry_after_s: float = settings.irrigation_stale_telemetry_after_s,
    ) -> None:
        self._lock = RLock()
        self._data_mode = data_mode
        self._crop_service = crop_service
        self._vivayu_service = vivayu_service or VivayuHealthService(
            model_path=resolve_model_path(settings.vivayu_model_path)
        )
        self._today_provider = today_provider
        self._now_provider = now_provider
        if stale_telemetry_after_s <= 0:
            raise ValueError("stale_telemetry_after_s must be positive")
        self._stale_telemetry_after_s = stale_telemetry_after_s
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
        state_payload["updated_at"] = self._now_provider().isoformat()
        return state_payload

    def _new_initial_state(self) -> SystemState:
        self._vivayu_service.reset_all_predictors()
        if self._data_mode == "hardware":
            return self._new_safe_hardware_state()
        return self._with_initial_vivayu_health(
            self._with_derived_contexts(
                SystemState.model_validate(
                    self._state_payload(self._baseline_payload, active_scenario_id=None)
                )
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
                    status="UNAVAILABLE",
                    available=False,
                    source_mode="HARDWARE",
                    reason_code="WAITING_FOR_COMPATIBLE_HARDWARE_TELEMETRY",
                    reason="waiting_for_compatible_hardware_telemetry",
                    warnings=(
                        "legacy Vivayu output is research-only and never controls irrigation",
                    ),
                ),
                hardware_metadata=self._hardware_metadata(zone_id),
            )
        return self._with_derived_contexts(SystemState(
            data_mode="hardware",
            updated_at=self._now_provider(),
            zones=zones,
            water=WaterState(
                fresh=WaterSourceState(
                    source_id="fresh",
                    display_name="Freshwater source",
                ),
                marginal=WaterSourceState(
                    source_id="marginal",
                    display_name="Marginal-quality water source",
                ),
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
            telemetry_connection=SerialConnectionState(
                status="DISCONNECTED",
                enabled=True,
                baud_rate=settings.serial_baud,
            ),
            controller=ControllerState(
                status="DISCONNECTED",
                communication_fault="controller status has not been received",
            ),
        ))

    @staticmethod
    def _hardware_metadata(zone_id: ZoneId) -> HardwareTelemetryMetadata:
        prefix = "zone_a" if zone_id == "A" else "zone_b"
        address = getattr(settings, f"{prefix}_bme280_i2c_address")
        return HardwareTelemetryMetadata(
            source="HARDWARE",
            target_interval_s=settings.field_telemetry_interval_s,
            soil_dry_raw=getattr(settings, f"{prefix}_soil_dry_raw"),
            soil_wet_raw=getattr(settings, f"{prefix}_soil_wet_raw"),
            soil_adc_pin=getattr(settings, f"{prefix}_soil_adc_pin"),
            bme280_i2c_address=address.lower() if address is not None else None,
            i2c_sda_pin=getattr(settings, f"{prefix}_i2c_sda_pin"),
            i2c_scl_pin=getattr(settings, f"{prefix}_i2c_scl_pin"),
        )

    def _with_initial_vivayu_health(self, state: SystemState) -> SystemState:
        zones: dict[ZoneId, ZoneState] = {}
        for zone_id, zone in state.zones.items():
            health = self._vivayu_service.add_zone_reading(
                zone_id,
                zone.telemetry,
                zone.config.vivayu_sensors,
                data_mode=state.data_mode,
            )
            zones[zone_id] = zone.model_copy(
                update={"vivayu_health": health},
                deep=True,
            )
        return state.model_copy(update={"zones": zones}, deep=True)

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
        water = state.water
        if state.data_mode == "simulation":
            water = WaterState(
                fresh=self._simulation_source_snapshot(water.fresh),
                marginal=self._simulation_source_snapshot(water.marginal),
                mix=water.mix,
            )
        return state.model_copy(
            update={"zones": zones, "weather": weather, "water": water},
            deep=True,
        )

    @staticmethod
    def _simulation_source_snapshot(source: WaterSourceState) -> WaterSourceState:
        age_s = None
        if source.last_measured_at is not None:
            age_s = max(0.0, (_utc_now() - source.last_measured_at).total_seconds())
        return source.model_copy(
            update={
                "measurement_age_s": age_s,
                "quality_status": "SIMULATED" if source.tds_ppm is not None else "UNKNOWN",
            },
            deep=True,
        )

    @staticmethod
    def _require_zone(zone_id: str) -> ZoneId:
        if zone_id not in {"A", "B"}:
            raise UnknownZoneError(zone_id)
        return cast(ZoneId, zone_id)

    def get_state(self) -> SystemState:
        with self._lock:
            return self._state_snapshot()

    @property
    def data_mode(self) -> DataMode:
        return self._data_mode

    def _state_snapshot(self) -> SystemState:
        """Refresh receive-time freshness and measurement ages without data loss."""

        if self._state.data_mode != "hardware":
            return self._state.model_copy(deep=True)
        source_updates: dict[str, WaterSourceState] = {}
        now = self._now_provider()
        for source_id in ("fresh", "marginal"):
            source = getattr(self._state.water, source_id)
            if source.last_measured_at is None:
                source_updates[source_id] = source.model_copy(deep=True)
                continue
            age_s = max(0.0, (now - source.last_measured_at).total_seconds())
            quality_status = source.quality_status
            if quality_status in {"MEASURED", "STALE"}:
                quality_status = (
                    "STALE"
                    if age_s > settings.tds_source_stale_minutes * 60
                    else "MEASURED"
                )
            source_updates[source_id] = source.model_copy(
                update={
                    "measurement_age_s": age_s,
                    "quality_status": quality_status,
                },
                deep=True,
            )
        water = self._state.water.model_copy(update=source_updates, deep=True)
        zone_updates: dict[ZoneId, ZoneState] = {}
        for zone_id, zone in self._state.zones.items():
            received_at = zone.telemetry.received_at
            if received_at is None:
                age_s = None
                online = False
            else:
                age_s = max(0.0, (now - received_at).total_seconds())
                online = age_s <= self._stale_telemetry_after_s
            zone_updates[zone_id] = zone.model_copy(
                update={"telemetry_age_s": age_s, "online": online},
                deep=True,
            )
        return self._state.model_copy(
            update={"water": water, "zones": zone_updates},
            deep=True,
        )

    def get_zone(self, zone_id: str) -> ZoneState:
        canonical_zone_id = self._require_zone(zone_id)
        with self._lock:
            return self._state_snapshot().zones[canonical_zone_id].model_copy(deep=True)

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
            self._vivayu_service.reset_all_predictors()
            merged = _deep_merge(self._baseline_payload, overrides)
            self._state = self._with_initial_vivayu_health(
                self._with_derived_contexts(
                    SystemState.model_validate(
                        self._state_payload(merged, active_scenario_id=scenario_id)
                    )
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
            health = current_zone.vivayu_health
            if config.vivayu_sensors != current_zone.config.vivayu_sensors:
                self._vivayu_service.reset_zone_predictor(canonical_zone_id)
                health = self._vivayu_service.add_zone_reading(
                    canonical_zone_id,
                    current_zone.telemetry,
                    config.vivayu_sensors,
                    data_mode=self._state.data_mode,
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
                vivayu_health=health,
                hardware_metadata=current_zone.hardware_metadata,
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

    def get_irrigation_parameters(self, zone_id: str) -> PrototypeIrrigationParameters:
        canonical_zone_id = self._require_zone(zone_id)
        with self._lock:
            return self._state.zones[
                canonical_zone_id
            ].config.irrigation_parameters.model_copy(deep=True)

    def update_irrigation_parameters(
        self,
        zone_id: str,
        parameters: PrototypeIrrigationParameters,
    ) -> ZoneState:
        canonical_zone_id = self._require_zone(zone_id)
        with self._lock:
            current = self._state.zones[canonical_zone_id]
            config = ZoneConfig.model_validate(
                {
                    **current.config.model_dump(),
                    "irrigation_parameters": parameters,
                }
            )
            return self.update_zone_config(canonical_zone_id, config)

    def get_water_quality_parameters(
        self,
        zone_id: str,
    ) -> PrototypeWaterQualityParameters:
        canonical_zone_id = self._require_zone(zone_id)
        with self._lock:
            return self._state.zones[
                canonical_zone_id
            ].config.water_quality_parameters.model_copy(deep=True)

    def update_water_quality_parameters(
        self,
        zone_id: str,
        parameters: PrototypeWaterQualityParameters,
    ) -> ZoneState:
        canonical_zone_id = self._require_zone(zone_id)
        with self._lock:
            current = self._state.zones[canonical_zone_id]
            config = ZoneConfig.model_validate(
                {
                    **current.config.model_dump(),
                    "water_quality_parameters": parameters,
                }
            )
            return self.update_zone_config(canonical_zone_id, config)

    def get_water(self) -> WaterState:
        with self._lock:
            return self._state_snapshot().water

    def update_water_source(
        self,
        source_id: WaterSourceId,
        update: WaterSourceUpdateRequest,
    ) -> WaterSourceState:
        with self._lock:
            measured_at = update.last_measured_at
            age_s = None
            if measured_at is not None:
                now = self._now_provider()
                if measured_at > now:
                    raise ValueError("last_measured_at cannot be in the future")
                age_s = (now - measured_at).total_seconds()
            if update.tds_ppm is None:
                quality_status = "UNKNOWN"
            elif self._state.data_mode == "simulation":
                quality_status = "SIMULATED"
            elif age_s is not None and age_s > settings.tds_source_stale_minutes * 60:
                quality_status = "STALE"
            else:
                quality_status = "MEASURED"

            current = getattr(self._state.water, source_id)
            source = WaterSourceState(
                source_id=source_id,
                display_name=current.display_name,
                tds_ppm=update.tds_ppm,
                temperature_c=update.temperature_c,
                available_l=update.available_l,
                last_measured_at=measured_at,
                measurement_age_s=age_s,
                quality_status=quality_status,
            )
            water = self._state.water.model_copy(update={source_id: source}, deep=True)
            self._state = SystemState(
                schema_version=self._state.schema_version,
                data_mode=self._state.data_mode,
                active_scenario_id=self._state.active_scenario_id,
                updated_at=self._now_provider(),
                zones=self._state.zones,
                water=water,
                weather=self._state.weather,
                power=self._state.power,
                telemetry_connection=self._state.telemetry_connection,
                controller=self._state.controller,
            )
            return source.model_copy(deep=True)

    def update_zone_telemetry(self, zone_id: str, telemetry: ZoneTelemetry) -> ZoneState:
        canonical_zone_id = self._require_zone(zone_id)
        if telemetry.zone_id != canonical_zone_id:
            raise ValueError("path zone_id does not match telemetry zone_id")

        with self._lock:
            current = self._state.zones[canonical_zone_id]
            health = self._vivayu_service.add_zone_reading(
                canonical_zone_id,
                telemetry,
                current.config.vivayu_sensors,
                data_mode=self._state.data_mode,
            )
            previous_received_at = current.telemetry.received_at
            packet_interval_s = current.hardware_metadata.packet_interval_s
            if telemetry.received_at is not None and previous_received_at is not None:
                observed_interval = (
                    telemetry.received_at - previous_received_at
                ).total_seconds()
                if observed_interval > 0:
                    packet_interval_s = observed_interval
            hardware_metadata = current.hardware_metadata.model_copy(
                update={
                    "packets_received": (
                        current.hardware_metadata.packets_received + 1
                    ),
                    "packet_interval_s": packet_interval_s,
                },
                deep=True,
            )
            updated_zone = ZoneState(
                zone_id=canonical_zone_id,
                config=current.config,
                telemetry=telemetry,
                growth_stage=current.growth_stage,
                days_after_sowing=current.days_after_sowing,
                crop_context=current.crop_context,
                telemetry_age_s=0.0,
                online=True,
                vivayu_health=health,
                hardware_metadata=hardware_metadata,
            )
            self._replace_zone(canonical_zone_id, updated_zone)
            return updated_zone.model_copy(deep=True)

    def update_telemetry_connection(
        self,
        connection: SerialConnectionState,
    ) -> SerialConnectionState:
        """Publish receive-only gateway status without altering zone telemetry."""

        with self._lock:
            self._state = self._state.model_copy(
                update={
                    "telemetry_connection": connection,
                    "updated_at": self._now_provider(),
                },
                deep=True,
            )
            return connection.model_copy(deep=True)

    def get_telemetry_connection(self) -> SerialConnectionState:
        with self._lock:
            return self._state.telemetry_connection.model_copy(deep=True)

    def update_controller_state(self, controller: ControllerState) -> ControllerState:
        """Publish controller safety truth without mutating telemetry or water."""

        with self._lock:
            if (
                self._state.data_mode == "simulation"
                and controller.status != "SIMULATED"
            ):
                raise ValueError("simulation state cannot publish hardware controller state")
            if (
                self._state.data_mode == "hardware"
                and controller.status == "SIMULATED"
            ):
                raise ValueError("hardware state cannot publish simulated controller state")
            self._state = self._state.model_copy(
                update={
                    "controller": controller,
                    "updated_at": self._now_provider(),
                },
                deep=True,
            )
            return controller.model_copy(deep=True)

    def get_controller_state(self) -> ControllerState:
        with self._lock:
            return self._state.controller.model_copy(deep=True)

    def get_vivayu_health(self, zone_id: str) -> VivayuHealthState:
        canonical_zone_id = self._require_zone(zone_id)
        with self._lock:
            return self._state.zones[canonical_zone_id].vivayu_health.model_copy(
                deep=True
            )

    def reset_zone_vivayu_predictor(self, zone_id: str) -> VivayuHealthState:
        canonical_zone_id = self._require_zone(zone_id)
        with self._lock:
            health = self._vivayu_service.reset_zone_predictor(canonical_zone_id)
            current = self._state.zones[canonical_zone_id]
            updated = current.model_copy(
                update={"vivayu_health": health},
                deep=True,
            )
            self._replace_zone(canonical_zone_id, updated)
            return health.model_copy(deep=True)

    def reset_all_vivayu_predictors(self) -> dict[ZoneId, VivayuHealthState]:
        with self._lock:
            health_by_zone = self._vivayu_service.reset_all_predictors()
            zones = {
                zone_id: zone.model_copy(
                    update={"vivayu_health": health_by_zone[zone_id]},
                    deep=True,
                )
                for zone_id, zone in self._state.zones.items()
            }
            self._state = self._state.model_copy(
                update={"zones": zones, "updated_at": self._now_provider()},
                deep=True,
            )
            return {
                zone_id: health.model_copy(deep=True)
                for zone_id, health in health_by_zone.items()
            }

    def update_weather(self, weather: WeatherState) -> WeatherState:
        with self._lock:
            if self._state.data_mode == "simulation":
                raise SimulationWeatherProtectedError(
                    "live weather cannot overwrite simulation scenario weather"
                )
            self._state = self._state.model_copy(
                update={"weather": weather, "updated_at": self._now_provider()},
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
            updated_at=self._now_provider(),
            zones=zones,
            water=self._state.water,
            weather=self._state.weather,
            power=self._state.power,
            telemetry_connection=self._state.telemetry_connection,
            controller=self._state.controller,
        )


application_state = ApplicationStateStore(data_mode=settings.data_mode)
isolated_demo_state = ApplicationStateStore(data_mode="simulation")


def simulation_state_store(
    live_store: ApplicationStateStore = application_state,
    demo_store: ApplicationStateStore = isolated_demo_state,
) -> ApplicationStateStore:
    """Keep legacy simulation behavior while isolating demos in hardware mode."""

    return live_store if live_store.data_mode == "simulation" else demo_store
