from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.schemas import FieldTelemetryPacket
from app.services.dashboard_snapshot import build_dashboard_snapshot
from app.services.serial_bridge import SerialBridge
from app.state import ApplicationStateStore, simulation_state_store


UTC = timezone.utc


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 21, 10, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def packet(zone_id: str = "A", **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "type": "field_telemetry",
        "node_id": f"field-node-{zone_id.lower()}",
        "zone_id": zone_id,
        "timestamp_ms": 123_456,
        "soil_moisture_raw": 2510,
        "soil_moisture_pct": 24.3,
        "temperature_c": 30.6,
        "humidity_pct": 62.4,
        "pressure_pa": 97_481.0,
        "gas_resistance_ohm": None,
        "sraw": None,
        "battery_voltage_v": None,
        "battery_pct": None,
        "signal_rssi_dbm": None,
    }
    payload.update(overrides)
    return payload


def bridge(store: ApplicationStateStore, clock: Clock) -> SerialBridge:
    return SerialBridge(
        state_store=store,
        data_mode="hardware",
        port="test-port",
        now_provider=clock,
    )


def line(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode() + b"\n"


def test_all_requested_physical_channels_propagate_to_canonical_state() -> None:
    clock = Clock()
    store = ApplicationStateStore(data_mode="hardware", now_provider=clock)
    serial = bridge(store, clock)

    assert serial.feed_bytes(line(packet())) == 1

    telemetry = store.get_state().zones["A"].telemetry
    assert telemetry.soil_moisture_raw == 2510
    assert telemetry.soil_moisture_pct == 24.3
    assert telemetry.temperature_c == 30.6
    assert telemetry.humidity_pct == 62.4
    assert telemetry.pressure_pa == 97_481.0
    assert telemetry.gas_resistance_ohm is None
    assert telemetry.sraw is None


def test_bme280_failure_keeps_soil_live_and_environment_null() -> None:
    clock = Clock()
    store = ApplicationStateStore(data_mode="hardware", now_provider=clock)
    serial = bridge(store, clock)

    assert serial.feed_bytes(line(packet(
        temperature_c=None,
        humidity_pct=None,
        pressure_pa=None,
    ))) == 1

    zone = store.get_state().zones["A"]
    assert zone.online is True
    assert zone.telemetry.soil_moisture_pct == 24.3
    assert zone.telemetry.temperature_c is None
    assert zone.telemetry.humidity_pct is None
    assert zone.telemetry.pressure_pa is None


def test_soil_failure_keeps_bme280_channels_live() -> None:
    clock = Clock()
    store = ApplicationStateStore(data_mode="hardware", now_provider=clock)
    serial = bridge(store, clock)

    assert serial.feed_bytes(line(packet(
        soil_moisture_raw=None,
        soil_moisture_pct=None,
    ))) == 1

    telemetry = store.get_state().zones["A"].telemetry
    assert telemetry.soil_moisture_raw is None
    assert telemetry.soil_moisture_pct is None
    assert telemetry.temperature_c == 30.6
    assert telemetry.pressure_pa == 97_481.0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("temperature_c", float("nan")),
        ("temperature_c", float("inf")),
        ("humidity_pct", -1.0),
        ("pressure_pa", 0.0),
        ("pressure_pa", float("inf")),
    ],
)
def test_malformed_bme_values_are_rejected(field: str, value: float) -> None:
    payload = packet(**{field: value})
    with pytest.raises(ValueError):
        FieldTelemetryPacket.model_validate(payload)


def test_packet_rate_metadata_and_staleness_use_backend_receive_time() -> None:
    clock = Clock()
    store = ApplicationStateStore(
        data_mode="hardware",
        now_provider=clock,
        stale_telemetry_after_s=10,
    )
    serial = bridge(store, clock)
    serial.feed_bytes(line(packet()))
    clock.advance(1.05)
    serial.feed_bytes(line(packet(timestamp_ms=124_506)))

    live = store.get_state().zones["A"]
    assert live.hardware_metadata.source == "HARDWARE"
    assert live.hardware_metadata.packets_received == 2
    assert live.hardware_metadata.packet_interval_s == pytest.approx(1.05)
    assert live.online is True

    clock.advance(10.1)
    stale = store.get_state().zones["A"]
    assert stale.online is False
    assert stale.telemetry.temperature_c == 30.6
    assert stale.telemetry_age_s == pytest.approx(10.1)


def test_hardware_state_is_never_replaced_by_isolated_demo_state() -> None:
    clock = Clock()
    hardware = ApplicationStateStore(data_mode="hardware", now_provider=clock)
    demo = ApplicationStateStore(data_mode="simulation")
    serial = bridge(hardware, clock)
    serial.feed_bytes(line(packet(soil_moisture_pct=19.7, temperature_c=31.2)))
    hardware_before = hardware.get_state()

    selected = simulation_state_store(hardware, demo)
    assert selected is demo
    selected.load_scenario("freshwater_shortage")
    demo_snapshot = build_dashboard_snapshot(selected.get_state())

    hardware_after = hardware.get_state()
    assert demo_snapshot.state.data_mode == "simulation"
    assert demo_snapshot.state.active_scenario_id == "freshwater_shortage"
    assert hardware_after.data_mode == "hardware"
    assert hardware_after.active_scenario_id is None
    assert hardware_after.zones["A"].telemetry == hardware_before.zones["A"].telemetry
    assert hardware_after.zones["A"].telemetry.soil_moisture_pct == 19.7
    assert hardware_after.zones["A"].telemetry.temperature_c == 31.2
    assert hardware_after.zones["B"] == hardware_before.zones["B"]


def test_simulation_store_preserves_legacy_single_store_behavior() -> None:
    simulation = ApplicationStateStore(data_mode="simulation")
    separate_demo = ApplicationStateStore(data_mode="simulation")

    assert simulation_state_store(simulation, separate_demo) is simulation
