"""Reconnect-safe serial telemetry plus bounded controller command transport."""

from __future__ import annotations

import json
import logging
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from json import JSONDecodeError
from threading import Event, Lock, RLock, Thread, current_thread
from typing import Callable, Protocol, cast
from uuid import uuid4

import serial
from pydantic import TypeAdapter, ValidationError

from app.config import settings
from app.schemas import (
    AddFreshWaterCommand,
    CommandRecord,
    ControllerAckPacket,
    ControllerCommand,
    ControllerState,
    ControllerStatusPacket,
    DataMode,
    FieldTelemetryPacket,
    IrrigateZoneCommand,
    MixWaterCommand,
    SerialConnectionState,
    SerialPacketHeader,
    StopAllCommand,
    ZoneId,
)
from app.state import ApplicationStateStore, application_state


LOGGER = logging.getLogger(__name__)
COMMAND_ADAPTER = TypeAdapter(ControllerCommand)
TERMINAL_COMMAND_STATUSES = {
    "ACKNOWLEDGED",
    "REJECTED",
    "TIMED_OUT",
    "FAILED",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_command_id(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


class SerialPort(Protocol):
    """Narrow bounded I/O surface used by pySerial and deterministic doubles."""

    def read(self, size: int = 1) -> bytes: ...

    def write(self, data: bytes) -> int: ...

    def close(self) -> None: ...


SerialFactory = Callable[..., SerialPort]
CommandIdGenerator = Callable[[str], str]


def _open_serial_port(
    *,
    port: str,
    baudrate: int,
    timeout: float,
    write_timeout: float,
) -> SerialPort:
    return cast(
        SerialPort,
        serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=timeout,
            write_timeout=write_timeout,
        ),
    )


class UnsupportedPacketError(ValueError):
    """Raised when a valid envelope names an unsupported inbound packet."""


class CommandUnavailableError(RuntimeError):
    """Raised when safety state does not permit a controller command."""


class DuplicateCommandIdError(ValueError):
    """Raised before a second logical command can reuse an issued ID."""


class CommandHistoryFullError(RuntimeError):
    """Raised when bounded history contains only nonterminal commands."""


class SerialBridge:
    """Own serial lifecycle, packet framing, command ACKs and fail-safe state."""

    READ_CHUNK_BYTES = 256

    def __init__(
        self,
        *,
        state_store: ApplicationStateStore,
        data_mode: DataMode,
        port: str | None,
        baud_rate: int = 115_200,
        read_timeout_s: float = 0.25,
        reconnect_interval_s: float = 2.0,
        max_line_bytes: int = 8_192,
        command_ack_timeout_s: float = 1.5,
        command_max_retries: int = 2,
        command_max_runtime_s: float = 120.0,
        command_history_limit: int = 100,
        serial_factory: SerialFactory = _open_serial_port,
        command_id_generator: CommandIdGenerator = _new_command_id,
        now_provider: Callable[[], datetime] = _utc_now,
    ) -> None:
        if baud_rate <= 0:
            raise ValueError("serial baud_rate must be positive")
        if read_timeout_s <= 0:
            raise ValueError("serial read_timeout_s must be positive")
        if reconnect_interval_s <= 0:
            raise ValueError("serial reconnect_interval_s must be positive")
        if max_line_bytes <= 0:
            raise ValueError("serial max_line_bytes must be positive")
        if command_ack_timeout_s <= 0:
            raise ValueError("command_ack_timeout_s must be positive")
        if command_max_retries < 0:
            raise ValueError("command_max_retries cannot be negative")
        if command_max_runtime_s <= 0 or command_max_runtime_s > 3_600:
            raise ValueError("command_max_runtime_s must be in (0, 3600]")
        if command_history_limit < 2:
            raise ValueError("command_history_limit must be at least 2")

        self._state_store = state_store
        self._data_mode = data_mode
        self._port = port
        self._baud_rate = baud_rate
        self._read_timeout_s = read_timeout_s
        self._reconnect_interval_s = reconnect_interval_s
        self._max_line_bytes = max_line_bytes
        self._command_ack_timeout_s = command_ack_timeout_s
        self._command_max_retries = command_max_retries
        self._command_max_runtime_s = command_max_runtime_s
        self._command_history_limit = command_history_limit
        self._serial_factory = serial_factory
        self._command_id_generator = command_id_generator
        self._now_provider = now_provider

        self._lock = RLock()
        self._write_lock = Lock()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._serial: SerialPort | None = None
        self._buffer = bytearray()
        self._discarding_oversized_line = False
        self._connection = self._initial_connection_state()
        self._command_history: OrderedDict[str, CommandRecord] = OrderedDict()
        self._issued_command_ids: OrderedDict[str, None] = OrderedDict()
        self._command_id_cache_limit = max(1_024, command_history_limit * 4)
        self._fail_safe_required = False
        self._controller = self._initial_controller_state()
        self._publish_connection(self._connection)
        self._publish_controller()

    def _initial_connection_state(self) -> SerialConnectionState:
        if self._data_mode == "simulation":
            return SerialConnectionState(
                status="DISABLED",
                enabled=False,
                configured_port=None,
                baud_rate=self._baud_rate,
            )
        if self._port is None:
            return SerialConnectionState(
                status="ERROR",
                enabled=True,
                configured_port=None,
                baud_rate=self._baud_rate,
                last_error="SERIAL_PORT is not configured",
                reconnect_pending=False,
            )
        return SerialConnectionState(
            status="DISCONNECTED",
            enabled=True,
            configured_port=self._port,
            baud_rate=self._baud_rate,
            reconnect_pending=False,
        )

    def _initial_controller_state(self) -> ControllerState:
        if self._data_mode == "simulation":
            return ControllerState(status="SIMULATED")
        return ControllerState(
            status="DISCONNECTED",
            communication_fault="controller status has not been received",
        )

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def get_connection_state(self) -> SerialConnectionState:
        with self._lock:
            return self._connection.model_copy(deep=True)

    def get_controller_state(self) -> ControllerState:
        with self._lock:
            return self._controller.model_copy(deep=True)

    def get_command_history(self) -> tuple[CommandRecord, ...]:
        with self._lock:
            return tuple(record.model_copy(deep=True) for record in self._command_history.values())

    def get_command(self, command_id: str) -> CommandRecord | None:
        with self._lock:
            record = self._command_history.get(command_id)
            return record.model_copy(deep=True) if record is not None else None

    def start(self) -> None:
        """Start the bounded reconnect loop only for configured hardware mode."""

        with self._lock:
            if self._data_mode == "simulation":
                self._set_connection(
                    status="DISABLED",
                    enabled=False,
                    configured_port=None,
                    reconnect_pending=False,
                )
                return
            if self._thread is not None and self._thread.is_alive():
                return
            if self._port is None:
                self._set_connection(
                    status="ERROR",
                    enabled=True,
                    configured_port=None,
                    last_error="SERIAL_PORT is not configured",
                    reconnect_pending=False,
                )
                return
            self._stop_event.clear()
            self._set_connection(
                status="CONNECTING",
                enabled=True,
                configured_port=self._port,
                reconnect_pending=True,
                last_error=None,
            )
            self._thread = Thread(
                target=self._run,
                name="vivayu-serial-reader",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Stop I/O, close the bidirectional handle and join the worker."""

        self._stop_event.set()
        with self._lock:
            handle = self._serial
            self._serial = None
        if handle is not None:
            self._close_handle(handle)
        with self._lock:
            thread = self._thread
        if thread is not None and thread is not current_thread():
            thread.join(timeout=max(1.0, self._read_timeout_s + 0.5))
        with self._lock:
            self._thread = None
            if self._data_mode == "simulation":
                self._set_connection(
                    status="DISABLED",
                    enabled=False,
                    configured_port=None,
                    reconnect_pending=False,
                )
            else:
                self._set_connection(
                    status="DISCONNECTED",
                    enabled=True,
                    configured_port=self._port,
                    last_disconnected_at=self._now_provider(),
                    reconnect_pending=False,
                )
                self._handle_transport_disconnected("serial bridge stopped")

    def feed_bytes(self, data: bytes) -> int:
        """Consume arbitrary chunks while preserving bounded newline framing."""

        if self._data_mode != "hardware":
            return 0
        if not isinstance(data, bytes):
            raise TypeError("serial chunks must be bytes")
        accepted = 0
        complete_lines: list[bytes] = []
        with self._lock:
            for byte in data:
                if self._discarding_oversized_line:
                    if byte == 0x0A:
                        self._discarding_oversized_line = False
                    continue
                if byte == 0x0A:
                    complete_lines.append(bytes(self._buffer).rstrip(b"\r"))
                    self._buffer.clear()
                    continue
                if len(self._buffer) >= self._max_line_bytes:
                    self._buffer.clear()
                    self._discarding_oversized_line = True
                    self._record_rejection("serial line exceeded configured byte limit")
                    continue
                self._buffer.append(byte)

        for line in complete_lines:
            if not line.strip():
                continue
            if self._process_line(line):
                accepted += 1
        return accepted

    def new_mix_water_command(
        self,
        *,
        fresh_ml: float,
        marginal_ml: float,
        max_runtime_s: float,
    ) -> MixWaterCommand:
        return MixWaterCommand(
            command_id=self._generate_command_id("cmd"),
            fresh_ml=fresh_ml,
            marginal_ml=marginal_ml,
            max_runtime_s=max_runtime_s,
        )

    def new_add_fresh_water_command(
        self,
        *,
        fresh_ml: float,
        max_runtime_s: float,
    ) -> AddFreshWaterCommand:
        return AddFreshWaterCommand(
            command_id=self._generate_command_id("cmd"),
            fresh_ml=fresh_ml,
            max_runtime_s=max_runtime_s,
        )

    def new_irrigate_zone_command(
        self,
        *,
        zone_id: ZoneId,
        volume_ml: float,
        max_runtime_s: float,
    ) -> IrrigateZoneCommand:
        return IrrigateZoneCommand(
            command_id=self._generate_command_id("cmd"),
            zone_id=zone_id,
            volume_ml=volume_ml,
            max_runtime_s=max_runtime_s,
        )

    def send_command(self, command: ControllerCommand) -> CommandRecord:
        """Send one explicitly supplied command; never derive it from M4-M6."""

        if self._data_mode != "hardware":
            raise CommandUnavailableError(
                "controller commands are disabled in simulation mode"
            )
        validated = COMMAND_ADAPTER.validate_python(command.model_dump())
        self._validate_runtime(validated)
        with self._lock:
            if validated.command_id in self._issued_command_ids:
                raise DuplicateCommandIdError(
                    f"command_id already issued: {validated.command_id}"
                )
            if validated.action != "STOP_ALL":
                if not self._controller.ready or self._fail_safe_required:
                    raise CommandUnavailableError(
                        "controller must report IDLE before actuation commands are allowed"
                    )
                if self._has_pending_non_stop_command():
                    raise CommandUnavailableError(
                        "another pump-affecting command is awaiting acknowledgement"
                    )
            record = self._create_record(validated)
        self._attempt_send(record.command.command_id, is_retry=False)
        current = self.get_command(record.command.command_id)
        assert current is not None
        return current

    def emergency_stop(self) -> CommandRecord:
        """Request or queue highest-priority STOP_ALL regardless of pending work."""

        if self._data_mode != "hardware":
            raise CommandUnavailableError(
                "emergency STOP is disabled in simulation mode"
            )
        with self._lock:
            existing = self._pending_stop_record()
            if existing is not None:
                return existing.model_copy(deep=True)
            self._fail_safe_required = True
            self._set_controller(
                status="UNKNOWN",
                ready=False,
                stop_required=True,
                execution_uncertain=True,
                communication_fault="STOP_ALL requested; waiting for controller IDLE",
            )
            command = StopAllCommand(
                command_id=self._generate_command_id("cmd-stop")
            )
            record = self._create_record(command)
        self._attempt_send(record.command.command_id, is_retry=False)
        current = self.get_command(record.command.command_id)
        assert current is not None
        return current

    def process_command_timeouts(self) -> None:
        """Apply finite ACK retries and enter fail-safe after exhaustion."""

        now = self._now_provider()
        retry_ids: list[str] = []
        timed_out_non_stop = False
        with self._lock:
            for command_id, record in tuple(self._command_history.items()):
                if record.status != "SENT" or record.sent_at is None:
                    continue
                if now < record.sent_at + timedelta(seconds=self._command_ack_timeout_s):
                    continue
                is_stop = record.command.action == "STOP_ALL"
                if (
                    record.retry_count < self._command_max_retries
                    and self._serial is not None
                    and (is_stop or not self._fail_safe_required)
                ):
                    retry_ids.append(command_id)
                    continue
                self._replace_record(
                    command_id,
                    status="TIMED_OUT",
                    updated_at=now,
                    error="controller acknowledgement timeout",
                )
                if not is_stop:
                    timed_out_non_stop = True
                else:
                    self._fail_safe_required = True
                    self._set_controller(
                        status="UNKNOWN",
                        ready=False,
                        stop_required=True,
                        execution_uncertain=True,
                        communication_fault=(
                            "STOP_ALL acknowledgement timed out; controller IDLE not confirmed"
                        ),
                    )

        for command_id in retry_ids:
            self._attempt_send(command_id, is_retry=True)
        if timed_out_non_stop:
            self._enter_fail_safe(
                "command acknowledgement timed out; physical execution is unknown"
            )

    @staticmethod
    def serialize_command_line(command: ControllerCommand) -> bytes:
        validated = COMMAND_ADAPTER.validate_python(command.model_dump())
        encoded = json.dumps(
            validated.model_dump(mode="json"),
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return encoded + b"\n"

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._set_connection(
                status="CONNECTING",
                enabled=True,
                configured_port=self._port,
                reconnect_pending=True,
                reconnect_attempt_count=(
                    self.get_connection_state().reconnect_attempt_count + 1
                ),
            )
            try:
                assert self._port is not None
                handle = self._serial_factory(
                    port=self._port,
                    baudrate=self._baud_rate,
                    timeout=self._read_timeout_s,
                    write_timeout=self._command_ack_timeout_s,
                )
            except Exception as error:
                self._record_connection_failure(error)
                self.process_command_timeouts()
                if self._stop_event.wait(self._reconnect_interval_s):
                    break
                continue

            with self._lock:
                self._serial = handle
            self._set_connection(
                status="CONNECTED",
                enabled=True,
                configured_port=self._port,
                last_connected_at=self._now_provider(),
                last_error=None,
                reconnect_pending=False,
            )
            self._send_pending_stop_first()

            try:
                while not self._stop_event.is_set():
                    with self._lock:
                        if self._serial is not handle:
                            break
                    chunk = handle.read(self.READ_CHUNK_BYTES)
                    if chunk:
                        self.feed_bytes(chunk)
                    self.process_command_timeouts()
            except Exception as error:
                if not self._stop_event.is_set():
                    self._record_connection_failure(error)
            finally:
                self._close_handle(handle)
                with self._lock:
                    if self._serial is handle:
                        self._serial = None

            if not self._stop_event.is_set():
                self._set_connection(
                    status="DISCONNECTED",
                    enabled=True,
                    configured_port=self._port,
                    last_disconnected_at=self._now_provider(),
                    reconnect_pending=True,
                )
                self._handle_transport_disconnected("serial transport disconnected")
                self.process_command_timeouts()
                if self._stop_event.wait(self._reconnect_interval_s):
                    break

    def _process_line(self, line: bytes) -> bool:
        try:
            text = line.decode("utf-8", errors="strict")
            payload = json.loads(text)
            header = SerialPacketHeader.model_validate(payload)
            received_at = self._now_provider()
            if header.type == "field_telemetry":
                packet = FieldTelemetryPacket.model_validate(payload)
                self._validate_node_zone_consistency(packet.zone_id, packet.node_id)
                telemetry = packet.to_zone_telemetry(received_at=received_at)
                self._state_store.update_zone_telemetry(packet.zone_id, telemetry)
            elif header.type == "ack":
                packet = ControllerAckPacket.model_validate(payload)
                if not self._handle_ack(packet, received_at=received_at):
                    raise ValueError(
                        f"unknown, stale, or conflicting ACK ID: {packet.command_id}"
                    )
            elif header.type == "controller_status":
                packet = ControllerStatusPacket.model_validate(payload)
                self._handle_controller_status(packet, received_at=received_at)
            else:
                raise UnsupportedPacketError(
                    f"unsupported serial packet type: {header.type}"
                )
        except (
            UnicodeDecodeError,
            JSONDecodeError,
            ValidationError,
            UnsupportedPacketError,
            ValueError,
        ) as error:
            self._record_rejection(f"{type(error).__name__}: {error}")
            return False

        with self._lock:
            self._set_connection(
                last_valid_packet_at=received_at,
                last_error=None,
                packets_received=self._connection.packets_received + 1,
            )
        return True

    def _handle_ack(
        self,
        packet: ControllerAckPacket,
        *,
        received_at: datetime,
    ) -> bool:
        with self._lock:
            record = self._command_history.get(packet.command_id)
            if record is None:
                self._set_controller(
                    unknown_ack_count=self._controller.unknown_ack_count + 1,
                )
                return False
            if record.status in TERMINAL_COMMAND_STATUSES:
                if record.ack_status == packet.status or (
                    record.status == "ACKNOWLEDGED"
                    and record.command.action == "STOP_ALL"
                    and record.confirmation_source == "CONTROLLER_STATUS"
                    and packet.status in {"accepted", "duplicate"}
                ):
                    self._set_controller(
                        last_ack_command_id=packet.command_id,
                        last_ack_status=packet.status,
                        last_ack_at=received_at,
                        duplicate_ack_count=self._controller.duplicate_ack_count + 1,
                    )
                    return True
                self._set_controller(
                    unknown_ack_count=self._controller.unknown_ack_count + 1,
                )
                return False
            if record.status != "SENT":
                self._set_controller(
                    unknown_ack_count=self._controller.unknown_ack_count + 1,
                )
                return False

            next_status = (
                "ACKNOWLEDGED"
                if packet.status in {"accepted", "duplicate"}
                else "REJECTED"
            )
            self._replace_record(
                packet.command_id,
                status=next_status,
                acknowledged_at=received_at,
                updated_at=received_at,
                ack_status=packet.status,
                confirmation_source="ACK",
                error=(
                    None
                    if next_status == "ACKNOWLEDGED"
                    else f"controller returned {packet.status}"
                ),
            )
            changes: dict[str, object] = {
                "last_ack_command_id": packet.command_id,
                "last_ack_status": packet.status,
                "last_ack_at": received_at,
            }
            if packet.status in {"accepted", "duplicate"}:
                stop_already_confirmed = (
                    record.command.action == "STOP_ALL"
                    and self._controller.status == "IDLE"
                    and self._controller.last_status_at is not None
                    and record.sent_at is not None
                    and self._controller.last_status_at >= record.sent_at
                )
                if not stop_already_confirmed:
                    changes.update(
                        {
                            "status": "UNKNOWN",
                            "ready": False,
                            "reported_state": None,
                            "execution_uncertain": True,
                            "stop_required": self._fail_safe_required,
                            "communication_fault": (
                                "command acknowledged; awaiting controller status"
                            ),
                        }
                    )
            elif packet.status == "busy":
                changes.update(
                    {
                        "status": "UNKNOWN",
                        "ready": False,
                        "reported_state": None,
                        "execution_uncertain": True,
                        "communication_fault": "controller reported busy",
                    }
                )
            self._set_controller(**changes)
            return True

    def _handle_controller_status(
        self,
        packet: ControllerStatusPacket,
        *,
        received_at: datetime,
    ) -> None:
        with self._lock:
            if packet.state == "IDLE":
                self._fail_safe_required = False
                for command_id, record in tuple(self._command_history.items()):
                    if (
                        record.command.action == "STOP_ALL"
                        and record.status in {"CREATED", "SENT"}
                        and record.sent_at is not None
                        and received_at >= record.sent_at
                    ):
                        self._replace_record(
                            command_id,
                            status="ACKNOWLEDGED",
                            acknowledged_at=received_at,
                            updated_at=received_at,
                            confirmation_source="CONTROLLER_STATUS",
                            error=None,
                        )
                status = "IDLE"
                ready = True
                execution_uncertain = False
                stop_required = False
                fault = None
            elif packet.state in {"MIXING", "IRRIGATING"}:
                status = "ACTIVE"
                ready = False
                execution_uncertain = False
                stop_required = self._fail_safe_required
                fault = None
            elif packet.state == "EMERGENCY_STOP":
                status = "EMERGENCY_STOP"
                ready = False
                execution_uncertain = False
                stop_required = False
                fault = None
            else:
                status = "FAULT"
                ready = False
                execution_uncertain = False
                stop_required = self._fail_safe_required
                fault = "controller reported FAULT"

            self._set_controller(
                status=status,
                connected=True,
                ready=ready,
                controller_id=packet.controller_id,
                reported_state=packet.state,
                emergency_stop=packet.emergency_stop,
                stop_required=stop_required,
                execution_uncertain=execution_uncertain,
                last_status_at=received_at,
                last_device_timestamp_ms=packet.timestamp_ms,
                last_command_id=packet.last_command_id,
                communication_fault=fault,
            )

    def _attempt_send(self, command_id: str, *, is_retry: bool) -> None:
        with self._lock:
            record = self._command_history.get(command_id)
            if record is None or record.status in TERMINAL_COMMAND_STATUSES:
                return
            handle = self._serial
            is_stop = record.command.action == "STOP_ALL"
            if handle is None:
                if not is_stop:
                    self._replace_record(
                        command_id,
                        status="FAILED",
                        updated_at=self._now_provider(),
                        error="serial transport unavailable before command write",
                    )
                return
            payload = self.serialize_command_line(record.command)
            send_started_at = self._now_provider()
            self._replace_record(
                command_id,
                status="SENT",
                sent_at=send_started_at,
                updated_at=send_started_at,
                retry_count=record.retry_count + (1 if is_retry else 0),
                error=None,
            )

        try:
            with self._write_lock:
                written = handle.write(payload)
                if written != len(payload):
                    raise OSError(
                        f"partial serial command write: {written}/{len(payload)} bytes"
                    )
        except Exception as error:
            detail = f"{type(error).__name__}: {error}".replace("\n", " ")[:240]
            with self._lock:
                self._replace_record(
                    command_id,
                    status="FAILED",
                    updated_at=self._now_provider(),
                    error=detail,
                )
                if self._serial is handle:
                    self._serial = None
            self._close_handle(handle)
            self._record_connection_failure(error)
            if not is_stop:
                self._enter_fail_safe(
                    "serial command write failed; physical execution is unknown"
                )
            return

    def _enter_fail_safe(self, detail: str) -> None:
        with self._lock:
            self._fail_safe_required = True
            self._set_controller(
                status="UNKNOWN",
                ready=False,
                stop_required=True,
                execution_uncertain=True,
                communication_fault=detail,
            )
            existing = self._pending_stop_record()
            if existing is None:
                command = StopAllCommand(
                    command_id=self._generate_command_id("cmd-stop")
                )
                existing = self._create_record(command)
            should_send = existing.status == "CREATED"
            stop_id = existing.command.command_id
        if should_send:
            self._attempt_send(stop_id, is_retry=False)

    def _send_pending_stop_first(self) -> None:
        with self._lock:
            record = self._pending_stop_record()
            stop_id = record.command.command_id if record is not None else None
            is_retry = record is not None and record.status == "SENT"
            retry_allowed = (
                record is None
                or record.status == "CREATED"
                or record.retry_count < self._command_max_retries
            )
        if stop_id is not None and retry_allowed:
            self._attempt_send(stop_id, is_retry=is_retry)

    def _handle_transport_disconnected(self, detail: str) -> None:
        with self._lock:
            potentially_active = self._has_pending_non_stop_command() or (
                self._controller.status in {"ACTIVE", "UNKNOWN"}
            )
        if potentially_active:
            self._enter_fail_safe(
                f"{detail}; controller execution state is unknown"
            )
            with self._lock:
                self._set_controller(connected=False)
        else:
            with self._lock:
                self._set_controller(
                    status="DISCONNECTED",
                    connected=False,
                    ready=False,
                    reported_state=None,
                    emergency_stop=False,
                    execution_uncertain=False,
                    communication_fault=detail,
                )

    def _validate_runtime(self, command: ControllerCommand) -> None:
        if command.action != "STOP_ALL" and (
            command.max_runtime_s > self._command_max_runtime_s
        ):
            raise ValueError(
                "command max_runtime_s exceeds configured COMMAND_MAX_RUNTIME_S"
            )

    def _generate_command_id(self, prefix: str) -> str:
        command_id = self._command_id_generator(prefix)
        with self._lock:
            if command_id in self._issued_command_ids:
                raise DuplicateCommandIdError(
                    f"command ID generator repeated an issued ID: {command_id}"
                )
        return command_id

    def _create_record(self, command: ControllerCommand) -> CommandRecord:
        self._make_history_room()
        now = self._now_provider()
        record = CommandRecord(
            command=command,
            status="CREATED",
            created_at=now,
            updated_at=now,
        )
        self._command_history[command.command_id] = record
        self._issued_command_ids[command.command_id] = None
        while len(self._issued_command_ids) > self._command_id_cache_limit:
            self._issued_command_ids.popitem(last=False)
        self._set_controller(last_command_id=command.command_id)
        return record

    def _replace_record(self, command_id: str, **changes: object) -> CommandRecord:
        current = self._command_history[command_id]
        updated = CommandRecord.model_validate(
            {**current.model_dump(), **changes}
        )
        self._command_history[command_id] = updated
        self._publish_controller()
        return updated

    def _make_history_room(self) -> None:
        while len(self._command_history) >= self._command_history_limit:
            terminal_id = next(
                (
                    command_id
                    for command_id, record in self._command_history.items()
                    if record.status in TERMINAL_COMMAND_STATUSES
                ),
                None,
            )
            if terminal_id is None:
                raise CommandHistoryFullError(
                    "bounded command history contains only pending commands"
                )
            self._command_history.pop(terminal_id)

    def _has_pending_non_stop_command(self) -> bool:
        return any(
            record.command.action != "STOP_ALL"
            and record.status in {"CREATED", "SENT"}
            for record in self._command_history.values()
        )

    def _pending_stop_record(self) -> CommandRecord | None:
        return next(
            (
                record
                for record in reversed(tuple(self._command_history.values()))
                if record.command.action == "STOP_ALL"
                and record.status in {"CREATED", "SENT"}
            ),
            None,
        )

    def _validate_node_zone_consistency(self, zone_id: ZoneId, node_id: str) -> None:
        configured_node = self._state_store.get_zone(zone_id).config.field_node_id
        if configured_node is not None and node_id != configured_node:
            raise ValueError(
                f"node_id does not match configured field node for Zone {zone_id}"
            )

    def _record_rejection(self, detail: str) -> None:
        safe_detail = detail.replace("\n", " ")[:240]
        LOGGER.warning("Rejected inbound serial packet: %s", safe_detail)
        with self._lock:
            self._set_connection(
                last_error=f"packet rejected: {safe_detail}",
                packets_rejected=self._connection.packets_rejected + 1,
            )

    def _record_connection_failure(self, error: Exception) -> None:
        detail = f"{type(error).__name__}: {error}".replace("\n", " ")[:240]
        LOGGER.warning("Serial transport unavailable: %s", detail)
        self._set_connection(
            status="ERROR",
            enabled=True,
            configured_port=self._port,
            last_disconnected_at=self._now_provider(),
            last_error=detail,
            reconnect_pending=True,
        )
        self._handle_transport_disconnected(detail)

    def _set_connection(self, **changes: object) -> None:
        with self._lock:
            next_state = SerialConnectionState.model_validate(
                {
                    **self._connection.model_dump(),
                    **changes,
                }
            )
            self._connection = next_state
            self._publish_connection(next_state)

    def _set_controller(self, **changes: object) -> None:
        with self._lock:
            next_state = ControllerState.model_validate(
                {
                    **self._controller.model_dump(exclude={"command_history"}),
                    **changes,
                    "command_history": tuple(self._command_history.values()),
                }
            )
            self._controller = next_state
            self._publish_controller()

    def _publish_connection(self, connection: SerialConnectionState) -> None:
        self._state_store.update_telemetry_connection(connection)

    def _publish_controller(self) -> None:
        with self._lock:
            controller = ControllerState.model_validate(
                {
                    **self._controller.model_dump(exclude={"command_history"}),
                    "command_history": tuple(self._command_history.values()),
                }
            )
            self._controller = controller
            self._state_store.update_controller_state(controller)

    @staticmethod
    def _close_handle(handle: SerialPort) -> None:
        try:
            handle.close()
        except Exception:
            LOGGER.exception("Could not close serial transport handle cleanly")


serial_bridge = SerialBridge(
    state_store=application_state,
    data_mode=settings.data_mode,
    port=settings.serial_port,
    baud_rate=settings.serial_baud,
    read_timeout_s=settings.serial_read_timeout_s,
    reconnect_interval_s=settings.serial_reconnect_interval_s,
    max_line_bytes=settings.serial_max_line_bytes,
    command_ack_timeout_s=settings.command_ack_timeout_s,
    command_max_retries=settings.command_max_retries,
    command_max_runtime_s=settings.command_max_runtime_s,
    command_history_limit=settings.command_history_limit,
)
