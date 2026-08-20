import pytest

from app.schemas import SystemState
from app.state import ApplicationStateStore


EXPECTED_SCENARIOS = {
    "zone_a_critical",
    "rain_soon",
    "tds_correction",
    "freshwater_shortage",
    "sensor_offline",
    "legacy_ml_unavailable",
}


def test_all_six_required_scenarios_are_listed() -> None:
    store = ApplicationStateStore()

    assert {scenario.id for scenario in store.list_scenarios()} == EXPECTED_SCENARIOS


@pytest.mark.parametrize("scenario_id", sorted(EXPECTED_SCENARIOS))
def test_every_scenario_loads_as_canonical_simulation_state(scenario_id: str) -> None:
    state = ApplicationStateStore().load_scenario(scenario_id)

    assert isinstance(state, SystemState)
    assert state.data_mode == "simulation"
    assert state.active_scenario_id == scenario_id
    assert set(state.zones) == {"A", "B"}
    assert state.zones["A"].zone_id == "A"
    assert state.zones["B"].zone_id == "B"


def test_zone_a_critical_scenario_values() -> None:
    state = ApplicationStateStore().load_scenario("zone_a_critical")

    assert state.zones["A"].telemetry.soil_moisture_pct == 22.0
    assert state.zones["B"].telemetry.soil_moisture_pct == 38.0
    assert state.weather.rain_probability_6h_pct == 10.0
    assert state.water.fresh.available_l == 0.6


def test_rain_soon_scenario_values() -> None:
    state = ApplicationStateStore().load_scenario("rain_soon")

    assert state.zones["A"].telemetry.soil_moisture_pct == 32.0
    assert state.weather.rain_probability_6h_pct == 85.0
    assert state.weather.rain_6h_mm == 7.4


def test_tds_correction_scenario_is_input_state_only() -> None:
    state = ApplicationStateStore().load_scenario("tds_correction")

    assert state.water.mix.tds_ppm == 560.0
    assert state.water.mix.volume_estimate_ml == 400.0
    assert not hasattr(state, "decision")


def test_freshwater_shortage_scenario_values() -> None:
    state = ApplicationStateStore().load_scenario("freshwater_shortage")

    assert state.zones["A"].telemetry.soil_moisture_pct == 24.0
    assert state.zones["B"].telemetry.soil_moisture_pct == 27.0
    assert state.water.fresh.available_l == 0.25


def test_sensor_offline_scenario_marks_only_zone_a_offline() -> None:
    state = ApplicationStateStore().load_scenario("sensor_offline")

    assert state.zones["A"].online is False
    assert state.zones["A"].telemetry_age_s == 90.0
    assert state.zones["B"].online is True


def test_legacy_ml_unavailable_keeps_missing_sensors_null() -> None:
    state = ApplicationStateStore().load_scenario("legacy_ml_unavailable")
    zone_b = state.zones["B"]

    assert zone_b.telemetry.gas_resistance_ohm is None
    assert zone_b.telemetry.sraw is None
    assert zone_b.vivayu_health.available is False
    assert zone_b.vivayu_health.research_only is True
    assert zone_b.vivayu_health.reason == "legacy_vivayu_sensor_signature_incomplete"


def test_loading_a_new_scenario_cannot_leak_previous_overrides() -> None:
    store = ApplicationStateStore()
    store.load_scenario("tds_correction")

    state = store.load_scenario("legacy_ml_unavailable")

    assert state.water.mix.tds_ppm is None
    assert state.zones["A"].telemetry.soil_moisture_pct == 32.0
    assert state.zones["B"].telemetry.gas_resistance_ohm is None
