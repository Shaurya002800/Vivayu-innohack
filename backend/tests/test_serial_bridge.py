from __future__ import annotations

import json
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from threading import Event
from typing import Any, Callable

import pytest

from app.schemas import PrototypeIrrigationParameters
from app.services.irrigation_need import calculate_irrigation_need, irrigation_need_policy
from app.services.serial_bridge import SerialBridge
from app.state import ApplicationStateStore


UTC = timezone.utc


class FakeClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 21, 10, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += timedelta(seconds=seconds)


class FakeSerial:
    def __init__(self, chunks: list[bytes | Exception] | None = None) -> None:
        self.chunks = deque(chunks or [])
        self.closed = Event()
        self.write_calls = 0

    def read(self, _size: int = 1) -> bytes:
        if self.closed.is_set():
            return b""
        if self.chunks:
            item = self.chunks.popleft()
            if isinstance(item, Exception):
                raise item
            return item
        time.sleep(0.001)
        return b""

    def write(self, _data: bytes) -> int:
        self.write_calls += 1
        raise AssertionError("Milestone 9 must never write to serial")

    def close(self) -> None:
        self.closed.set()


class SequenceFactory:
    def __init__(self, outcomes: list[FakeSerial | Exception]) -> None:
        self.outcomes = deque(outcomes)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> FakeSerial:
        self.calls.append(kwargs)
        if not self.outcomes:
            raise OSError("test device remains unavailable")
        outcome = self.outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def wait_until(predicate: Callable[[], bool], timeout_s: float = 1.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition did not become true before timeout")


def packet(
    zone_id: str = "A",
    *,
    node_id: str | None = None,
    timestamp_ms: int = 1_181_072,
    soil_moisture_pct: float | None = 24.3,
    gas_resistance_ohm: float | None = 62_070.0,
    sraw: int | None = 29_005,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "type": "field_telemetry",
        "node_id": node_id or f"field-node-{zone_id.lower()}",
        "zone_id": zone_id,
        "timestamp_ms": timestamp_ms,
        "soil_moisture_raw": 2510,
        "soil_moisture_pct": soil_moisture_pct,
        "temperature_c": 30.6,
        "humidity_pct": 62.4,
        "pressure_pa": 97_481.0,
        "gas_resistance_ohm": gas_resistance_ohm,
        "sraw": sraw,
        "battery_voltage_v": 3.91,
        "battery_pct": 74.0,
        "signal_rssi_dbm": -62.0,
    }


def line(value: dict[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode() + b"\n"


def hardware_store(clock: FakeClock | None = None) -> ApplicationStateStore:
    active_clock = clock or FakeClock()
    return ApplicationStateStore(
        data_mode="hardware",
        now_provider=active_clock,
        stale_telemetry_after_s=10.0,
    )


def bridge_for(
    store: ApplicationStateStore,
    *,
    clock: FakeClock | None = None,
    factory: Callable[..., FakeSerial] | None = None,
    max_line_bytes: int = 8_192,
    data_mode: str = "hardware",
    port: str | None = "test-port",
) -> SerialBridge:
    return SerialBridge(
        state_store=store,
        data_mode=data_mode,  # type: ignore[arg-type]
        port=port,
        baud_rate=115_200,
        read_timeout_s=0.01,
        reconnect_interval_s=0.01,
        max_line_bytes=max_line_bytes,
        serial_factory=factory or SequenceFactory([]),
        now_provider=clock or FakeClock(),
    )


def test_valid_zone_a_and_b_packets_remain_isolated_when_interleaved() -> None:
    clock = FakeClock()
    store = hardware_store(clock)
    bridge = bridge_for(store, clock=clock)

    assert bridge.feed_bytes(line(packet("A", soil_moisture_pct=21.0))) == 1
    clock.advance(1)
    assert bridge.feed_bytes(line(packet("B", soil_moisture_pct=38.0))) == 1
    clock.advance(1)
    assert bridge.feed_bytes(line(packet("A", soil_moisture_pct=25.0))) == 1

    state = store.get_state()
    assert state.zones["A"].telemetry.soil_moisture_pct == 25.0
    assert state.zones["B"].telemetry.soil_moisture_pct == 38.0
    assert state.zones["A"].telemetry.node_id == "field-node-a"
    assert state.zones["B"].telemetry.node_id == "field-node-b"


def test_missing_optional_sensors_remain_null_and_vivayu_is_unavailable() -> None:
    store = hardware_store()
    bridge = bridge_for(store)
    minimal = {
        "schema_version": "1.0",
        "type": "field_telemetry",
        "node_id": "field-node-a",
        "zone_id": "A",
    }

    assert bridge.feed_bytes(line(minimal)) == 1

    zone = store.get_zone("A")
    assert zone.telemetry.soil_moisture_pct is None
    assert zone.telemetry.temperature_c is None
    assert zone.telemetry.gas_resistance_ohm is None
    assert zone.telemetry.sraw is None
    assert zone.vivayu_health.status == "UNAVAILABLE"
    assert zone.vivayu_health.pattern is None


def test_five_serial_packets_flow_through_canonical_vivayu_window() -> None:
    clock = FakeClock()
    store = hardware_store(clock)
    bridge = bridge_for(store, clock=clock)
    progress: list[tuple[str, int]] = []

    for index in range(5):
        value = packet("A", timestamp_ms=1_000 + index)
        assert bridge.feed_bytes(line(value)) == 1
        health = store.get_vivayu_health("A")
        progress.append((health.status, health.readings_received))
        clock.advance(1)

    assert progress[:4] == [
        ("COLLECTING", 1),
        ("COLLECTING", 2),
        ("COLLECTING", 3),
        ("COLLECTING", 4),
    ]
    assert progress[4] == ("READY", 5)
    assert store.get_vivayu_health("A").research_only is True
    assert store.get_vivayu_health("B").status == "UNAVAILABLE"


def test_real_style_soil_packet_changes_existing_m4_preview_via_state() -> None:
    clock = FakeClock()
    store = hardware_store(clock)
    store.update_irrigation_parameters(
        "A",
        PrototypeIrrigationParameters(
            target_moisture_pct=45.0,
            critical_moisture_pct=25.0,
            ml_per_moisture_point=20.0,
        ),
    )
    bridge = bridge_for(store, clock=clock)

    assert bridge.feed_bytes(line(packet("A", soil_moisture_pct=22.0))) == 1
    state = store.get_state()
    result = calculate_irrigation_need(
        state.zones["A"],
        state.weather,
        irrigation_need_policy,
    )

    assert result.status == "CRITICAL"
    assert result.current_moisture_pct == 22.0
    assert result.requested_water_ml == 460.0


def test_partial_lines_multiple_lines_and_blanks_are_assembled() -> None:
    store = hardware_store()
    bridge = bridge_for(store)
    first = line(packet("A", soil_moisture_pct=20.0))
    second = line(packet("B", soil_moisture_pct=35.0))
    split = len(first) // 2

    assert bridge.feed_bytes(first[:split]) == 0
    assert bridge.feed_bytes(first[split:] + b"\n\r\n" + second) == 2
    assert store.get_zone("A").telemetry.soil_moisture_pct == 20.0
    assert store.get_zone("B").telemetry.soil_moisture_pct == 35.0
    assert bridge.get_connection_state().packets_received == 2


@pytest.mark.parametrize(
    "invalid_line",
    [
        b"{not-json}\n",
        b"\xff\xfe\n",
        line({**packet(), "schema_version": "2.0"}),
        line({**packet(), "type": "water_source_telemetry"}),
        line({**packet(), "zone_id": "C"}),
        line({**packet(), "node_id": "field-node-b"}),
        line({**packet(), "humidity_pct": 101.0}),
        b'{"schema_version":"1.0","type":"field_telemetry","node_id":"field-node-a","zone_id":"A","temperature_c":NaN}\n',
    ],
)
def test_bad_lines_are_rejected_without_state_mutation(invalid_line: bytes) -> None:
    store = hardware_store()
    bridge = bridge_for(store)
    before = store.get_zone("A")

    assert bridge.feed_bytes(invalid_line) == 0

    assert store.get_zone("A") == before
    assert bridge.get_connection_state().packets_rejected == 1


def test_oversized_line_is_discarded_and_next_packet_recovers() -> None:
    store = hardware_store()
    valid = line(packet("A"))
    bridge = bridge_for(store, max_line_bytes=len(valid) + 5)
    oversized = b"x" * (len(valid) + 20)

    assert bridge.feed_bytes(oversized + b"\n" + valid) == 1
    assert bridge.get_connection_state().packets_rejected == 1
    assert store.get_zone("A").online is True


def test_simulation_mode_never_opens_or_consumes_serial() -> None:
    store = ApplicationStateStore(data_mode="simulation")
    factory = SequenceFactory([FakeSerial([line(packet("A"))])])
    bridge = bridge_for(
        store,
        factory=factory,
        data_mode="simulation",
        port="must-not-open",
    )

    bridge.start()

    assert factory.calls == []
    assert bridge.is_running is False
    assert bridge.feed_bytes(line(packet("A"))) == 0
    assert bridge.get_connection_state().status == "DISABLED"
    assert store.get_state().active_scenario_id is None


def test_hardware_mode_has_no_simulation_fallback_values() -> None:
    state = hardware_store().get_state()

    assert state.data_mode == "hardware"
    assert state.zones["A"].telemetry.soil_moisture_pct is None
    assert state.zones["B"].telemetry.temperature_c is None
    assert state.water.fresh.tds_ppm is None
    assert state.water.marginal.available_l is None
    assert state.weather.status == "OFFLINE"


def test_unavailable_port_retries_without_breaking_state_and_stops_cleanly() -> None:
    store = hardware_store()

    def unavailable(**_kwargs: Any) -> FakeSerial:
        raise OSError("test port unavailable")

    bridge = bridge_for(store, factory=unavailable)
    bridge.start()
    wait_until(lambda: bridge.get_connection_state().reconnect_attempt_count >= 2)

    assert store.get_state().schema_version == "1.0"
    assert bridge.get_connection_state().reconnect_pending is True
    assert bridge.is_running is True

    bridge.stop()
    assert bridge.is_running is False
    assert bridge.get_connection_state().status == "DISCONNECTED"


def test_reconnect_recovers_after_startup_failure() -> None:
    store = hardware_store()
    handle = FakeSerial([line(packet("A"))])
    factory = SequenceFactory([OSError("not ready"), handle])
    bridge = bridge_for(store, factory=factory)

    bridge.start()
    wait_until(lambda: bridge.get_connection_state().packets_received == 1)

    assert len(factory.calls) == 2
    assert factory.calls[0] == {
        "port": "test-port",
        "baudrate": 115_200,
        "timeout": 0.01,
        "write_timeout": 1.5,
    }
    assert bridge.get_connection_state().status == "CONNECTED"
    assert store.get_zone("A").online is True
    bridge.stop()
    assert handle.closed.is_set()


def test_disconnect_while_reading_reconnects_and_preserves_zone_isolation() -> None:
    store = hardware_store()
    first = FakeSerial([line(packet("A", soil_moisture_pct=23.0)), OSError("lost")])
    second = FakeSerial([line(packet("B", soil_moisture_pct=37.0))])
    factory = SequenceFactory([first, second])
    bridge = bridge_for(store, factory=factory)

    bridge.start()
    wait_until(lambda: bridge.get_connection_state().packets_received == 2)

    assert store.get_zone("A").telemetry.soil_moisture_pct == 23.0
    assert store.get_zone("B").telemetry.soil_moisture_pct == 37.0
    assert first.closed.is_set()
    bridge.stop()
    assert second.closed.is_set()


def test_receive_time_staleness_is_per_zone_and_fresh_packet_recovers() -> None:
    clock = FakeClock()
    store = hardware_store(clock)
    bridge = bridge_for(store, clock=clock)
    bridge.feed_bytes(line(packet("A", timestamp_ms=8_000)))
    clock.advance(8)
    bridge.feed_bytes(line(packet("B", timestamp_ms=9_000)))
    clock.advance(3)

    stale = store.get_state()
    assert stale.zones["A"].online is False
    assert stale.zones["A"].telemetry.soil_moisture_pct == 24.3
    assert stale.zones["A"].telemetry_age_s == 11.0
    assert stale.zones["B"].online is True
    assert stale.zones["B"].telemetry_age_s == 3.0

    bridge.feed_bytes(line(packet("A", timestamp_ms=0, soil_moisture_pct=30.0)))
    recovered = store.get_state()
    assert recovered.zones["A"].online is True
    assert recovered.zones["A"].telemetry_age_s == 0.0
    assert recovered.zones["A"].telemetry.timestamp_ms == 0
    assert recovered.zones["A"].telemetry.soil_moisture_pct == 30.0


def test_shutdown_closes_receive_handle_without_writes_or_thread_leak() -> None:
    store = hardware_store()
    handle = FakeSerial()
    bridge = bridge_for(store, factory=SequenceFactory([handle]))
    bridge.start()
    wait_until(lambda: bridge.get_connection_state().status == "CONNECTED")

    bridge.stop()

    assert handle.closed.is_set()
    assert handle.write_calls == 0
    assert bridge.is_running is False


def test_missing_port_reports_error_without_starting_thread() -> None:
    store = hardware_store()
    bridge = bridge_for(store, port=None)

    bridge.start()

    assert bridge.is_running is False
    assert bridge.get_connection_state().status == "ERROR"
    assert bridge.get_connection_state().last_error == "SERIAL_PORT is not configured"
    assert store.get_state().telemetry_connection.status == "ERROR"
