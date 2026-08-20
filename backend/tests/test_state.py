import pytest

from app.schemas import ZoneConfig, ZoneTelemetry
from app.state import (
    ApplicationStateStore,
    SimulationModeDisabledError,
    UnknownZoneError,
)


def test_zone_a_telemetry_update_does_not_touch_zone_b() -> None:
    store = ApplicationStateStore()
    zone_a_before = store.get_zone("A")
    zone_b_before = store.get_zone("B")
    telemetry_payload = zone_a_before.telemetry.model_dump()
    telemetry_payload.update({"soil_moisture_pct": 11.5, "timestamp_ms": 2222222})

    store.update_zone_telemetry("A", ZoneTelemetry.model_validate(telemetry_payload))

    assert store.get_zone("A").telemetry.soil_moisture_pct == 11.5
    assert store.get_zone("A").telemetry.timestamp_ms == 2222222
    assert store.get_zone("B") == zone_b_before


def test_zone_b_config_update_does_not_touch_zone_a_and_persists() -> None:
    store = ApplicationStateStore()
    zone_a_before = store.get_zone("A")
    config_payload = store.get_zone("B").config.model_dump()
    config_payload.update(
        {
            "crop_id": "okra",
            "growth_stage_mode": "MANUAL",
            "manual_growth_stage": "flowering",
        }
    )

    store.update_zone_config("B", ZoneConfig.model_validate(config_payload))

    assert store.get_zone("A") == zone_a_before
    assert store.get_zone("B").config.crop_id == "okra"
    assert store.get_zone("B").growth_stage == "flowering"
    assert store.get_state().zones["B"].config.crop_id == "okra"


def test_manual_stage_override_is_isolated_and_persistent() -> None:
    store = ApplicationStateStore()
    zone_b_before = store.get_zone("B")

    updated = store.set_manual_stage("A", "flowering")

    assert updated.config.growth_stage_mode == "MANUAL"
    assert updated.config.manual_growth_stage == "flowering"
    assert store.get_zone("A").growth_stage == "flowering"
    assert store.get_zone("B") == zone_b_before


def test_returned_state_is_a_copy_and_cannot_mutate_store() -> None:
    store = ApplicationStateStore()
    returned = store.get_state()
    returned.zones["A"] = returned.zones["B"]

    fresh = store.get_state()

    assert fresh.zones["A"].zone_id == "A"
    assert fresh.zones["B"].zone_id == "B"


def test_reset_restores_clean_baseline() -> None:
    store = ApplicationStateStore()
    baseline = store.get_state()
    store.load_scenario("zone_a_critical")
    store.set_manual_stage("A", "flowering")

    reset = store.reset()

    assert reset.active_scenario_id is None
    assert reset.zones["A"].telemetry == baseline.zones["A"].telemetry
    assert reset.zones["A"].config == baseline.zones["A"].config
    assert reset.zones["B"] == baseline.zones["B"]


def test_invalid_zone_is_rejected_by_store() -> None:
    store = ApplicationStateStore()

    with pytest.raises(UnknownZoneError):
        store.get_zone("C")


def test_hardware_mode_starts_with_null_real_sensor_state() -> None:
    store = ApplicationStateStore(data_mode="hardware")
    state = store.get_state()

    assert state.data_mode == "hardware"
    assert state.zones["A"].telemetry.soil_moisture_pct is None
    assert state.zones["B"].telemetry.temperature_c is None
    assert state.water.fresh.tds_ppm is None
    assert state.power.solar_power_w is None
    assert state.weather.status == "OFFLINE"
    assert state.weather.provider_status == "NOT_FETCHED"
    assert state.weather.stale is True

    with pytest.raises(SimulationModeDisabledError):
        store.load_scenario("zone_a_critical")
