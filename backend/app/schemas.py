"""Canonical VIVAYU Aqua API and application-state schemas."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


SchemaVersion = Literal["1.0"]
DataMode = Literal["simulation", "hardware"]
ZoneId = Literal["A", "B"]
GrowthStageMode = Literal["AUTO", "MANUAL"]
WeatherStatus = Literal["SIMULATED", "LIVE", "CACHED", "OFFLINE"]
WeatherProviderStatus = Literal[
    "SIMULATED",
    "OK",
    "ERROR",
    "NOT_CONFIGURED",
    "NOT_FETCHED",
]
RiskLevel = Literal["low", "watch", "elevated", "high"]
CropContextStatus = Literal[
    "READY",
    "CROP_UNCONFIGURED",
    "SOWING_DATE_MISSING",
    "OUTSIDE_REFERENCE_CALENDAR",
]
CropStageSource = Literal["AUTO", "MANUAL"]
WaterStressSensitivity = Literal["low", "moderate", "high"]

Percentage = Annotated[float, Field(ge=0, le=100)]
NonNegativeFloat = Annotated[float, Field(ge=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]


class CanonicalModel(BaseModel):
    """Reject unknown state fields and prevent mutation outside the state store."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class HealthResponse(CanonicalModel):
    status: Literal["ok"] = "ok"
    service: str
    data_mode: DataMode
    schema_version: SchemaVersion = "1.0"


class ZoneConfig(CanonicalModel):
    zone_id: ZoneId
    name: Annotated[str, Field(min_length=1)]
    crop_id: str | None = None
    sowing_date: date | None = None
    growth_stage_mode: GrowthStageMode = "AUTO"
    manual_growth_stage: str | None = None
    soil_sensor_id: str | None = None
    field_node_id: str | None = None
    enabled: bool = True

    @model_validator(mode="after")
    def validate_manual_stage(self) -> Self:
        if self.growth_stage_mode == "MANUAL" and not self.manual_growth_stage:
            raise ValueError("manual_growth_stage is required in MANUAL mode")
        if self.growth_stage_mode == "AUTO" and self.manual_growth_stage is not None:
            raise ValueError("manual_growth_stage must be null in AUTO mode")
        return self


class ZoneTelemetry(CanonicalModel):
    schema_version: SchemaVersion = "1.0"
    type: Literal["field_telemetry"] = "field_telemetry"
    node_id: str | None = None
    zone_id: ZoneId
    timestamp_ms: NonNegativeInt | None = None
    soil_moisture_raw: NonNegativeInt | None = None
    soil_moisture_pct: Percentage | None = None
    temperature_c: float | None = None
    humidity_pct: Percentage | None = None
    pressure_pa: Annotated[float, Field(gt=0)] | None = None
    gas_resistance_ohm: Annotated[float, Field(gt=0)] | None = None
    sraw: Annotated[int, Field(ge=0, le=65_535)] | None = None
    battery_voltage_v: NonNegativeFloat | None = None
    battery_pct: Percentage | None = None
    signal_rssi_dbm: float | None = None
    received_at: AwareDatetime | None = None


class SourceMetadata(CanonicalModel):
    source_id: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    url: Annotated[str, Field(min_length=1)]
    notes: str | None = None


class CropStageProfile(CanonicalModel):
    stage_id: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    start_day: NonNegativeInt | None = None
    end_day: NonNegativeInt | None = None
    water_stress_sensitivity: WaterStressSensitivity | None = None
    crop_coefficient_kc: NonNegativeFloat | None = None

    @model_validator(mode="after")
    def validate_day_range(self) -> Self:
        if (self.start_day is None) != (self.end_day is None):
            raise ValueError("crop stage start_day and end_day must both be set or both be null")
        if self.start_day is not None and self.end_day is not None and self.end_day < self.start_day:
            raise ValueError("crop stage end_day must not precede start_day")
        return self


class CropMoistureTargets(CanonicalModel):
    target_moisture_pct: Percentage | None = None
    critical_moisture_pct: Percentage | None = None
    source_id: str | None = None
    notes: Annotated[str, Field(min_length=1)]


class CropSalinityConstraint(CanonicalModel):
    max_irrigation_tds_ppm: NonNegativeFloat | None = None
    qualitative_tolerance: str | None = None
    source_id: str | None = None
    notes: Annotated[str, Field(min_length=1)]


class CropProfile(CanonicalModel):
    crop_id: Annotated[str, Field(min_length=1)]
    display_name: Annotated[str, Field(min_length=1)]
    scientific_name: str | None = None
    reference_context: Annotated[str, Field(min_length=1)]
    stages: tuple[CropStageProfile, ...]
    moisture: CropMoistureTargets
    salinity: CropSalinityConstraint
    sources: tuple[SourceMetadata, ...]
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_stage_ranges(self) -> Self:
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("crop profile source IDs must be unique")
        for referenced_source in (self.moisture.source_id, self.salinity.source_id):
            if referenced_source is not None and referenced_source not in source_ids:
                raise ValueError(f"crop profile references unknown source: {referenced_source}")
        seen: set[str] = set()
        previous_end: int | None = None
        for stage in self.stages:
            if stage.stage_id in seen:
                raise ValueError(f"duplicate crop stage id: {stage.stage_id}")
            seen.add(stage.stage_id)
            if stage.start_day is not None:
                if previous_end is not None and stage.start_day != previous_end + 1:
                    raise ValueError("configured crop stage ranges must be contiguous")
                previous_end = stage.end_day
        return self


class CropContext(CanonicalModel):
    zone_id: ZoneId
    crop_id: str | None = None
    crop_name: str | None = None
    sowing_date: date | None = None
    days_after_sowing: NonNegativeInt | None = None
    growth_stage: str | None = None
    stage_source: CropStageSource | None = None
    status: CropContextStatus
    crop_coefficient_kc: NonNegativeFloat | None = None
    water_stress_sensitivity: WaterStressSensitivity | None = None
    target_moisture_pct: Percentage | None = None
    critical_moisture_pct: Percentage | None = None
    max_irrigation_tds_ppm: NonNegativeFloat | None = None
    source_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class VivayuHealthState(CanonicalModel):
    available: bool = False
    risk_level: RiskLevel | None = None
    pattern: str | None = None
    confidence_pct: Percentage | None = None
    research_only: Literal[True] = True
    reason: str | None = None

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        result_fields = (self.risk_level, self.pattern, self.confidence_pct)
        if self.available and (self.risk_level is None or self.pattern is None):
            raise ValueError("available Vivayu state requires risk_level and pattern")
        if not self.available and any(value is not None for value in result_fields):
            raise ValueError("unavailable Vivayu state cannot contain model results")
        if not self.available and not self.reason:
            raise ValueError("unavailable Vivayu state requires a reason")
        return self


class ZoneState(CanonicalModel):
    zone_id: ZoneId
    config: ZoneConfig
    telemetry: ZoneTelemetry
    growth_stage: str | None = None
    days_after_sowing: NonNegativeInt | None = None
    crop_context: CropContext | None = None
    telemetry_age_s: NonNegativeFloat | None = None
    online: bool = False
    vivayu_health: VivayuHealthState

    @model_validator(mode="after")
    def validate_zone_identity(self) -> Self:
        if self.config.zone_id != self.zone_id:
            raise ValueError("zone config does not match ZoneState zone_id")
        if self.telemetry.zone_id != self.zone_id:
            raise ValueError("zone telemetry does not match ZoneState zone_id")
        if self.crop_context is not None:
            if self.crop_context.zone_id != self.zone_id:
                raise ValueError("crop context does not match ZoneState zone_id")
            if self.crop_context.growth_stage != self.growth_stage:
                raise ValueError("crop context growth stage does not match ZoneState")
            if self.crop_context.days_after_sowing != self.days_after_sowing:
                raise ValueError("crop context days after sowing do not match ZoneState")
        if self.online and self.telemetry_age_s is None:
            raise ValueError("online zone requires telemetry_age_s")
        return self


class WaterSourceState(CanonicalModel):
    tds_ppm: NonNegativeFloat | None = None
    temperature_c: float | None = None
    available_l: NonNegativeFloat | None = None
    last_measured_at: AwareDatetime | None = None


class MixWaterState(CanonicalModel):
    tds_ppm: NonNegativeFloat | None = None
    temperature_c: float | None = None
    volume_estimate_ml: NonNegativeFloat | None = None
    last_measured_at: AwareDatetime | None = None


class WaterState(CanonicalModel):
    fresh: WaterSourceState
    marginal: WaterSourceState
    mix: MixWaterState


class WeatherState(CanonicalModel):
    status: WeatherStatus
    rain_probability_6h_pct: Percentage | None = None
    rain_6h_mm: NonNegativeFloat | None = None
    et0_6h_mm: NonNegativeFloat | None = None
    temperature_max_6h_c: float | None = None
    fetched_at: AwareDatetime | None = None
    age_s: NonNegativeFloat | None = None
    stale: bool = False
    provider: str | None = None
    provider_status: WeatherProviderStatus | None = None
    error: str | None = None

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        forecast_values = (
            self.rain_probability_6h_pct,
            self.rain_6h_mm,
            self.et0_6h_mm,
            self.temperature_max_6h_c,
        )
        if self.status == "OFFLINE" and any(value is not None for value in forecast_values):
            raise ValueError("offline weather cannot contain forecast values")
        if self.fetched_at is None and self.age_s is not None:
            raise ValueError("weather age requires fetched_at")
        return self


class PowerState(CanonicalModel):
    connected: bool = False
    solar_power_w: NonNegativeFloat | None = None
    battery_voltage_v: NonNegativeFloat | None = None
    battery_pct: Percentage | None = None
    load_current_a: NonNegativeFloat | None = None
    measured_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_disconnected_state(self) -> Self:
        readings = (
            self.solar_power_w,
            self.battery_voltage_v,
            self.battery_pct,
            self.load_current_a,
            self.measured_at,
        )
        if not self.connected and any(value is not None for value in readings):
            raise ValueError("disconnected power state cannot contain measurements")
        return self


class SystemState(CanonicalModel):
    schema_version: SchemaVersion = "1.0"
    data_mode: DataMode
    active_scenario_id: str | None = None
    updated_at: AwareDatetime
    zones: dict[ZoneId, ZoneState]
    water: WaterState
    weather: WeatherState
    power: PowerState

    @model_validator(mode="after")
    def validate_complete_zone_set(self) -> Self:
        if set(self.zones) != {"A", "B"}:
            raise ValueError("SystemState must contain exactly Zone A and Zone B")
        for zone_id, zone in self.zones.items():
            if zone.zone_id != zone_id:
                raise ValueError(f"zone map key {zone_id} does not match nested zone_id")
        if self.data_mode == "hardware" and self.active_scenario_id is not None:
            raise ValueError("hardware state cannot have an active simulation scenario")
        return self


class SimulationScenarioSummary(CanonicalModel):
    id: str
    name: str
    description: str


class ActivateSimulationRequest(CanonicalModel):
    scenario_id: str


class StageOverrideRequest(CanonicalModel):
    growth_stage: Annotated[str, Field(min_length=1)]
