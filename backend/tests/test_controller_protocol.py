from __future__ import annotations

import json
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from threading import Event, Lock, Thread
from typing import Any, Callable

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas import (
    ControllerCommand,
    ControllerStatusPacket,
    IrrigateZoneCommand,
    MixWaterCommand,
    StopAllCommand,
)
from app.services.serial_bridge import (
    CommandUnavailableError,
    DuplicateCommandIdError,
    SerialBridge,
)
from app.state import ApplicationStateStore


UTC = timezone.utc
COMMAND_ADAPTER = TypeAdapter(ControllerCommand)


class FakeClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += timedelta(seconds=seconds)


class DuplexFakeSerial:
    def __init__(
        self,
        chunks: list[bytes | Exception] | None = None,
        *,
        on_write: Callable[[bytes], None] | None = None,
    ) -> None:
        self._chunks = deque(chunks or [])
        self._chunks_lock = Lock()
        self.closed = Event()
        self.writes: list[bytes] = []
        self.on_write = on_write

    def push(self, item: bytes | Exception) -> None:
        with self._chunks_lock:
            self._chunks.append(item)

    def read(self, _size: int = 1) -> bytes:
        if self.closed.is_set():
            return b""
        with self._chunks_lock:
            item = self._chunks.popleft() if self._chunks else None
        if isinstance(item, Exception):
            raise item
        if item is not None:
            return item
        time.sleep(0.001)
        return b""

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        if self.on_write is not None:
            self.on_write(data)
        return len(data)

    def close(self) -> None:
        self.closed.set()


class BlockingWriteSerial(DuplexFakeSerial):
    def __init__(self) -> None:
        super().__init__()
        self.first_write_entered = Event()
        self.release_first_write = Event()
        self._active_lock = Lock()
        self._active_writers = 0
        self.max_active_writers = 0
        self._write_number = 0

    def write(self, data: bytes) -> int:
        with self._active_lock:
            self._active_writers += 1
            self.max_active_writers = max(
                self.max_active_writers,
                self._active_writers,
            )
            self._write_number += 1
            write_number = self._write_number
        try:
            if write_number == 1:
                self.first_write_entered.set()
                assert self.release_first_write.wait(1.0)
            self.writes.append(data)
            return len(data)
        finally:
            with self._active_lock:
                self._active_writers -= 1


class SequenceFactory:
    def __init__(self, outcomes: list[DuplexFakeSerial | Exception]) -> None:
        self.outcomes = deque(outcomes)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> DuplexFakeSerial:
        self.calls.append(kwargs)
        if not self.outcomes:
            raise OSError("test controller remains unavailable")
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


def json_line(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"


def status_line(
    state: str = "IDLE",
    *,
    emergency_stop: bool = False,
    last_command_id: str | None = None,
    timestamp_ms: int = 100,
) -> bytes:
    return json_line(
        {
            "schema_version": "1.0",
            "type": "controller_status",
            "controller_id": "irrigation-controller",
            "state": state,
            "emergency_stop": emergency_stop,
            "last_command_id": last_command_id,
            "timestamp_ms": timestamp_ms,
        }
    )


def ack_line(command_id: str, status: str = "accepted") -> bytes:
    return json_line(
        {
            "schema_version": "1.0",
            "type": "ack",
            "command_id": command_id,
            "status": status,
        }
    )


def field_line(zone_id: str, moisture: float) -> bytes:
    return json_line(
        {
            "schema_version": "1.0",
            "type": "field_telemetry",
            "node_id": f"field-node-{zone_id.lower()}",
            "zone_id": zone_id,
            "timestamp_ms": 1_000,
            "soil_moisture_pct": moisture,
        }
    )


def make_bridge(
    handle: DuplexFakeSerial | None = None,
    *,
    clock: FakeClock | None = None,
    factory: Callable[..., DuplexFakeSerial] | None = None,
    data_mode: str = "hardware",
    max_retries: int = 1,
    history_limit: int = 100,
    id_generator: Callable[[str], str] | None = None,
) -> tuple[SerialBridge, ApplicationStateStore, DuplexFakeSerial | None]:
    active_clock = clock or FakeClock()
    store = ApplicationStateStore(
        data_mode=data_mode,  # type: ignore[arg-type]
        now_provider=active_clock,
    )
    active_handle = handle
    if data_mode == "hardware" and active_handle is None and factory is None:
        active_handle = DuplexFakeSerial()
    serial_factory = factory or SequenceFactory(
        [active_handle] if active_handle is not None else []
    )
    bridge = SerialBridge(
        state_store=store,
        data_mode=data_mode,  # type: ignore[arg-type]
        port="test-port" if data_mode == "hardware" else "must-not-open",
        read_timeout_s=0.01,
        reconnect_interval_s=0.01,
        command_ack_timeout_s=1.0,
        command_max_retries=max_retries,
        command_max_runtime_s=120.0,
        command_history_limit=history_limit,
        serial_factory=serial_factory,
        command_id_generator=id_generator or (lambda prefix: f"{prefix}-generated"),
        now_provider=active_clock,
    )
    return bridge, store, active_handle


def start_ready(bridge: SerialBridge) -> None:
    bridge.start()
    wait_until(lambda: bridge.get_connection_state().status == "CONNECTED")
    assert bridge.feed_bytes(status_line()) == 1
    assert bridge.get_controller_state().status == "IDLE"


@pytest.mark.parametrize(
    "model,payload",
    [
        (MixWaterCommand, {"command_id": "cmd-1", "fresh_ml": 0, "marginal_ml": 10, "max_runtime_s": 5}),
        (MixWaterCommand, {"command_id": "cmd-1", "fresh_ml": 10, "marginal_ml": -1, "max_runtime_s": 5}),
        (MixWaterCommand, {"command_id": "cmd-1", "fresh_ml": 10, "marginal_ml": 10, "max_runtime_s": float("inf")}),
        (IrrigateZoneCommand, {"command_id": "cmd-1", "zone_id": "C", "volume_ml": 10, "max_runtime_s": 5}),
        (IrrigateZoneCommand, {"command_id": "cmd-1", "zone_id": "A", "volume_ml": 0, "max_runtime_s": 5}),
        (StopAllCommand, {"command_id": "cmd-stop", "max_runtime_s": 1}),
    ],
)
def test_command_schemas_reject_invalid_payloads(model: Any, payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_command_union_rejects_unknown_action_version_and_fields() -> None:
    base = {
        "schema_version": "1.0",
        "type": "command",
        "command_id": "cmd-1",
        "action": "STOP_ALL",
    }

    for invalid in (
        {**base, "action": "OPEN_VALVE"},
        {**base, "schema_version": "2.0"},
        {**base, "unexpected": True},
    ):
        with pytest.raises(ValidationError):
            COMMAND_ADAPTER.validate_python(invalid)


def test_controller_status_requires_consistent_emergency_flag() -> None:
    with pytest.raises(ValidationError, match="must match"):
        ControllerStatusPacket(
            controller_id="controller",
            state="IDLE",
            emergency_stop=True,
        )


def test_generated_command_ids_are_unique_and_injectable() -> None:
    counter = 0

    def generator(prefix: str) -> str:
        nonlocal counter
        counter += 1
        return f"{prefix}-{counter:03d}"

    bridge, _, _ = make_bridge(id_generator=generator)
    first = bridge.new_mix_water_command(
        fresh_ml=10,
        marginal_ml=10,
        max_runtime_s=5,
    )
    second = bridge.new_irrigate_zone_command(
        zone_id="A",
        volume_ml=20,
        max_runtime_s=5,
    )

    assert first.command_id == "cmd-001"
    assert second.command_id == "cmd-002"


def test_command_serialization_is_exactly_one_utf8_json_line() -> None:
    command = MixWaterCommand(
        command_id="cmd-001",
        fresh_ml=250,
        marginal_ml=150,
        max_runtime_s=45,
    )

    encoded = SerialBridge.serialize_command_line(command)

    assert encoded.endswith(b"\n")
    assert encoded.count(b"\n") == 1
    assert json.loads(encoded) == command.model_dump(mode="json")


def test_matching_accepted_ack_completes_only_its_command() -> None:
    bridge, _, handle = make_bridge()
    assert handle is not None
    start_ready(bridge)
    try:
        command = MixWaterCommand(
            command_id="cmd-001",
            fresh_ml=20,
            marginal_ml=10,
            max_runtime_s=5,
        )
        sent = bridge.send_command(command)
        assert sent.status == "SENT"

        assert bridge.feed_bytes(ack_line("cmd-001", "accepted")) == 1

        record = bridge.get_command("cmd-001")
        assert record is not None
        assert record.status == "ACKNOWLEDGED"
        assert record.ack_status == "accepted"
        assert record.confirmation_source == "ACK"
        assert bridge.get_controller_state().status == "UNKNOWN"
    finally:
        bridge.stop()


def test_wrong_or_unknown_ack_never_mutates_pending_command() -> None:
    bridge, _, _ = make_bridge()
    start_ready(bridge)
    try:
        bridge.send_command(
            MixWaterCommand(
                command_id="cmd-001",
                fresh_ml=20,
                marginal_ml=10,
                max_runtime_s=5,
            )
        )

        assert bridge.feed_bytes(ack_line("cmd-other")) == 0

        record = bridge.get_command("cmd-001")
        assert record is not None and record.status == "SENT"
        assert bridge.get_controller_state().unknown_ack_count == 1
    finally:
        bridge.stop()


@pytest.mark.parametrize("ack_status", ["rejected", "busy"])
def test_negative_ack_is_not_treated_as_success(ack_status: str) -> None:
    bridge, _, _ = make_bridge()
    start_ready(bridge)
    try:
        bridge.send_command(
            MixWaterCommand(
                command_id="cmd-001",
                fresh_ml=20,
                marginal_ml=10,
                max_runtime_s=5,
            )
        )
        assert bridge.feed_bytes(ack_line("cmd-001", ack_status)) == 1

        record = bridge.get_command("cmd-001")
        assert record is not None
        assert record.status == "REJECTED"
        assert record.ack_status == ack_status
    finally:
        bridge.stop()


def test_duplicate_ack_is_recorded_without_reexecuting_or_corrupting_state() -> None:
    bridge, _, _ = make_bridge()
    start_ready(bridge)
    try:
        bridge.send_command(
            MixWaterCommand(
                command_id="cmd-001",
                fresh_ml=20,
                marginal_ml=10,
                max_runtime_s=5,
            )
        )
        bridge.feed_bytes(ack_line("cmd-001"))
        before = bridge.get_command("cmd-001")

        assert bridge.feed_bytes(ack_line("cmd-001")) == 1

        assert bridge.get_command("cmd-001") == before
        assert bridge.get_controller_state().duplicate_ack_count == 1
    finally:
        bridge.stop()


def test_retry_reuses_same_command_id_and_is_bounded() -> None:
    clock = FakeClock()
    bridge, _, handle = make_bridge(clock=clock, max_retries=1)
    assert handle is not None
    start_ready(bridge)
    try:
        bridge.send_command(
            MixWaterCommand(
                command_id="cmd-001",
                fresh_ml=20,
                marginal_ml=10,
                max_runtime_s=5,
            )
        )
        clock.advance(1.1)
        bridge.process_command_timeouts()

        assert len(handle.writes) == 2
        assert handle.writes[0] == handle.writes[1]
        assert json.loads(handle.writes[1])["command_id"] == "cmd-001"
        assert bridge.get_command("cmd-001").retry_count == 1  # type: ignore[union-attr]

        clock.advance(1.1)
        bridge.process_command_timeouts()
        normal = bridge.get_command("cmd-001")
        assert normal is not None and normal.status == "TIMED_OUT"
        assert len([line for line in handle.writes if b'"action":"MIX_WATER"' in line]) == 2
        assert any(b'"action":"STOP_ALL"' in line for line in handle.writes)
    finally:
        bridge.stop()


def test_stop_all_bypasses_pending_command_and_has_write_priority() -> None:
    bridge, _, handle = make_bridge()
    assert handle is not None
    start_ready(bridge)
    try:
        bridge.send_command(
            MixWaterCommand(
                command_id="cmd-001",
                fresh_ml=20,
                marginal_ml=10,
                max_runtime_s=5,
            )
        )
        stop = bridge.emergency_stop()

        assert stop.command.action == "STOP_ALL"
        assert len(handle.writes) == 2
        assert json.loads(handle.writes[-1])["action"] == "STOP_ALL"
        assert bridge.get_controller_state().stop_required is True
    finally:
        bridge.stop()


def test_concurrent_command_and_stop_writes_never_interleave() -> None:
    handle = BlockingWriteSerial()
    bridge, _, _ = make_bridge(handle)
    start_ready(bridge)
    errors: list[Exception] = []
    command = MixWaterCommand(
        command_id="cmd-001",
        fresh_ml=20,
        marginal_ml=10,
        max_runtime_s=5,
    )

    def send_normal() -> None:
        try:
            bridge.send_command(command)
        except Exception as error:  # pragma: no cover - asserted below
            errors.append(error)

    def send_stop() -> None:
        try:
            bridge.emergency_stop()
        except Exception as error:  # pragma: no cover - asserted below
            errors.append(error)

    first = Thread(target=send_normal)
    second = Thread(target=send_stop)
    first.start()
    assert handle.first_write_entered.wait(1.0)
    second.start()
    time.sleep(0.02)
    handle.release_first_write.set()
    first.join(1.0)
    second.join(1.0)
    try:
        assert errors == []
        assert handle.max_active_writers == 1
        assert len(handle.writes) == 2
        assert all(line.count(b"\n") == 1 and line.endswith(b"\n") for line in handle.writes)
    finally:
        bridge.stop()


def test_lost_ack_retry_duplicate_contract_executes_physical_action_once() -> None:
    clock = FakeClock()
    physical_action_ids: set[str] = set()
    physical_action_count = 0
    handle = DuplexFakeSerial()

    def mock_controller_write(data: bytes) -> None:
        nonlocal physical_action_count
        payload = json.loads(data)
        command_id = payload["command_id"]
        if payload["action"] == "STOP_ALL":
            handle.push(ack_line(command_id))
            return
        if command_id not in physical_action_ids:
            physical_action_ids.add(command_id)
            physical_action_count += 1
            return  # Deliberately lose the first ACK.
        handle.push(ack_line(command_id, "duplicate"))

    handle.on_write = mock_controller_write
    bridge, _, _ = make_bridge(handle, clock=clock, max_retries=1)
    start_ready(bridge)
    try:
        bridge.send_command(
            MixWaterCommand(
                command_id="cmd-001",
                fresh_ml=20,
                marginal_ml=10,
                max_runtime_s=5,
            )
        )
        clock.advance(1.1)
        bridge.process_command_timeouts()
        wait_until(
            lambda: bridge.get_command("cmd-001") is not None
            and bridge.get_command("cmd-001").status == "ACKNOWLEDGED"  # type: ignore[union-attr]
        )

        record = bridge.get_command("cmd-001")
        assert physical_action_count == 1
        assert len([line for line in handle.writes if b'"action":"MIX_WATER"' in line]) == 2
        assert record is not None and record.ack_status == "duplicate"
        assert record.retry_count == 1
    finally:
        bridge.stop()


def test_timeout_enters_fail_safe_stop_then_idle_status_restores_safety() -> None:
    clock = FakeClock()
    bridge, _, handle = make_bridge(clock=clock, max_retries=0)
    assert handle is not None
    start_ready(bridge)
    try:
        bridge.send_command(
            IrrigateZoneCommand(
                command_id="cmd-001",
                zone_id="A",
                volume_ml=40,
                max_runtime_s=5,
            )
        )
        clock.advance(1.1)
        bridge.process_command_timeouts()

        unsafe = bridge.get_controller_state()
        assert unsafe.status == "UNKNOWN"
        assert unsafe.execution_uncertain is True
        assert unsafe.stop_required is True
        stop_record = next(
            record for record in bridge.get_command_history()
            if record.command.action == "STOP_ALL"
        )
        assert json.loads(handle.writes[-1])["action"] == "STOP_ALL"

        bridge.feed_bytes(ack_line(stop_record.command.command_id, "accepted"))
        assert bridge.get_controller_state().ready is False
        bridge.feed_bytes(
            status_line(
                "EMERGENCY_STOP",
                emergency_stop=True,
                last_command_id=stop_record.command.command_id,
            )
        )
        assert bridge.get_controller_state().status == "EMERGENCY_STOP"
        bridge.feed_bytes(
            status_line(
                "IDLE",
                last_command_id=stop_record.command.command_id,
                timestamp_ms=0,
            )
        )

        safe = bridge.get_controller_state()
        assert safe.status == "IDLE"
        assert safe.ready is True
        assert safe.execution_uncertain is False
        assert safe.stop_required is False
    finally:
        bridge.stop()


def test_disconnect_while_waiting_ack_marks_unknown_and_reconnect_sends_stop_first() -> None:
    first = DuplexFakeSerial()
    second = DuplexFakeSerial()
    factory = SequenceFactory([first, second])
    bridge, _, _ = make_bridge(factory=factory, max_retries=1)
    start_ready(bridge)
    try:
        bridge.send_command(
            MixWaterCommand(
                command_id="cmd-001",
                fresh_ml=20,
                marginal_ml=10,
                max_runtime_s=5,
            )
        )
        first.push(OSError("controller cable lost"))
        wait_until(lambda: len(factory.calls) >= 2)
        wait_until(lambda: len(second.writes) >= 1)

        controller = bridge.get_controller_state()
        assert controller.status == "UNKNOWN"
        assert controller.connected is False
        assert controller.execution_uncertain is True
        assert json.loads(second.writes[0])["action"] == "STOP_ALL"
        with pytest.raises(CommandUnavailableError):
            bridge.send_command(
                MixWaterCommand(
                    command_id="cmd-002",
                    fresh_ml=20,
                    marginal_ml=10,
                    max_runtime_s=5,
                )
            )
    finally:
        bridge.stop()


@pytest.mark.parametrize(
    "bad_line",
    [
        ack_line("cmd-unknown", "not-a-status"),
        json_line({"schema_version": "2.0", "type": "ack", "command_id": "cmd-1", "status": "accepted"}),
        json_line({"schema_version": "1.0", "type": "controller_status", "controller_id": "c", "state": "IDLE", "emergency_stop": True}),
        json_line({"schema_version": "1.0", "type": "controller_status", "controller_id": "c", "state": "PUMPING", "emergency_stop": False}),
    ],
)
def test_malformed_ack_and_controller_status_are_rejected(bad_line: bytes) -> None:
    bridge, store, _ = make_bridge()
    before = store.get_controller_state()

    assert bridge.feed_bytes(bad_line) == 0

    assert store.get_controller_state() == before
    assert bridge.get_connection_state().packets_rejected == 1


def test_simulation_never_opens_or_sends_controller_commands() -> None:
    factory = SequenceFactory([DuplexFakeSerial()])
    bridge, store, _ = make_bridge(data_mode="simulation", factory=factory)

    bridge.start()

    assert factory.calls == []
    assert store.get_controller_state().status == "SIMULATED"
    with pytest.raises(CommandUnavailableError):
        bridge.emergency_stop()


def test_field_telemetry_still_isolated_and_never_auto_actuates_or_deducts_water() -> None:
    bridge, store, handle = make_bridge()
    assert handle is not None
    start_ready(bridge)
    water_before = store.get_state().water
    try:
        assert bridge.feed_bytes(field_line("A", 21.0) + field_line("B", 37.0)) == 2

        state = store.get_state()
        assert state.zones["A"].telemetry.soil_moisture_pct == 21.0
        assert state.zones["B"].telemetry.soil_moisture_pct == 37.0
        assert state.water == water_before
        assert handle.writes == []
        assert bridge.get_command_history() == ()
    finally:
        bridge.stop()


def test_command_history_is_bounded_and_duplicate_logical_id_is_rejected() -> None:
    bridge, _, _ = make_bridge(history_limit=2)
    start_ready(bridge)
    try:
        for index in range(3):
            command_id = f"cmd-{index}"
            bridge.send_command(
                MixWaterCommand(
                    command_id=command_id,
                    fresh_ml=20,
                    marginal_ml=10,
                    max_runtime_s=5,
                )
            )
            bridge.feed_bytes(ack_line(command_id))
            bridge.feed_bytes(status_line("IDLE", last_command_id=command_id))

        assert len(bridge.get_command_history()) == 2
        with pytest.raises(DuplicateCommandIdError):
            bridge.send_command(
                MixWaterCommand(
                    command_id="cmd-0",
                    fresh_ml=20,
                    marginal_ml=10,
                    max_runtime_s=5,
                )
            )
    finally:
        bridge.stop()


def test_configured_runtime_limit_rejects_command_before_serial_write() -> None:
    bridge, _, handle = make_bridge()
    assert handle is not None
    start_ready(bridge)
    try:
        with pytest.raises(ValueError, match="COMMAND_MAX_RUNTIME_S"):
            bridge.send_command(
                MixWaterCommand(
                    command_id="cmd-too-long",
                    fresh_ml=20,
                    marginal_ml=10,
                    max_runtime_s=121,
                )
            )
        assert handle.writes == []
    finally:
        bridge.stop()
