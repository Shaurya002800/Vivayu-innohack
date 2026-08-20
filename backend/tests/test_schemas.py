from pydantic import ValidationError
import pytest

from app.schemas import (
    PowerState,
    SystemState,
    VivayuHealthState,
    ZoneConfig,
    ZoneState,
    ZoneTelemetry,
)
from app.state import ApplicationStateStore


def test_unavailable_sensor_values_remain_null() -> None:
    telemetry = ZoneTelemetry(zone_id="A")

    assert telemetry.soil_moisture_pct is None
    assert telemetry.temperature_c is None
    assert telemetry.gas_resistance_ohm is None
    assert telemetry.sraw is None
    assert telemetry.model_dump()["soil_moisture_pct"] is None


def test_invalid_zone_id_is_rejected_by_schema() -> None:
    with pytest.raises(ValidationError):
        ZoneConfig(zone_id="C", name="Invalid zone")  # type: ignore[arg-type]


def test_zone_state_rejects_mixed_zone_identity() -> None:
    store = ApplicationStateStore()
    zone_a = store.get_zone("A")
    zone_b = store.get_zone("B")

    with pytest.raises(ValidationError, match="zone config does not match"):
        ZoneState(
            zone_id="A",
            config=zone_b.config,
            telemetry=zone_a.telemetry,
            growth_stage=None,
            days_after_sowing=None,
            telemetry_age_s=1.0,
            online=True,
            vivayu_health=zone_a.vivayu_health,
        )


def test_system_state_requires_exactly_two_canonical_zones() -> None:
    payload = ApplicationStateStore().get_state().model_dump()
    payload["zones"].pop("B")

    with pytest.raises(ValidationError, match="exactly Zone A and Zone B"):
        SystemState.model_validate(payload)


def test_disconnected_power_cannot_contain_fabricated_measurements() -> None:
    with pytest.raises(ValidationError, match="cannot contain measurements"):
        PowerState(connected=False, solar_power_w=5.0)


def test_unavailable_vivayu_state_cannot_contain_model_results() -> None:
    with pytest.raises(ValidationError, match="cannot contain model results"):
        VivayuHealthState(
            available=False,
            risk_level="watch",
            reason="sensor_signature_incomplete",
        )


def test_complete_state_round_trips_through_canonical_schema() -> None:
    state = ApplicationStateStore().get_state()

    restored = SystemState.model_validate_json(state.model_dump_json())

    assert restored == state
    assert set(restored.zones) == {"A", "B"}
    assert restored.schema_version == "1.0"
