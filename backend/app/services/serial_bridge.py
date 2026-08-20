"""Receive-only, reconnecting line-delimited serial telemetry adapter."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from json import JSONDecodeError
from threading import Event, RLock, Thread, current_thread
from typing import Callable, Protocol, cast

import serial
from pydantic import ValidationError

from app.config import settings
from app.schemas import (
    DataMode,
    FieldTelemetryPacket,
    SerialConnectionState,
    SerialPacketHeader,
    ZoneId,
)
from app.state import ApplicationStateStore, application_state


LOGGER = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SerialPort(Protocol):
    """Narrow receive-only surface used by production pySerial and test doubles."""

    def read(self, size: int = 1) -> bytes: ...

    def close(self) -> None: ...


SerialFactory = Callable[..., SerialPort]


def _open_serial_port(*, port: str, baudrate: int, timeout: float) -> SerialPort:
    return cast(
        SerialPort,
        serial.Serial(port=port, baudrate=baudrate, timeout=timeout),
    )


class UnsupportedPacketError(ValueError):
    """Raised when a valid envelope names a packet not supported in Milestone 9."""


class SerialBridge:
    """Own serial lifecycle, framing and validation; delegate state mutation."""

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
        serial_factory: SerialFactory = _open_serial_port,
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

        self._state_store = state_store
        self._data_mode = data_mode
        self._port = port
        self._baud_rate = baud_rate
        self._read_timeout_s = read_timeout_s
        self._reconnect_interval_s = reconnect_interval_s
        self._max_line_bytes = max_line_bytes
        self._serial_factory = serial_factory
        self._now_provider = now_provider

        self._lock = RLock()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._serial: SerialPort | None = None
        self._buffer = bytearray()
        self._discarding_oversized_line = False
        self._connection = self._initial_connection_state()
        self._publish_connection(self._connection)

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

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def get_connection_state(self) -> SerialConnectionState:
        with self._lock:
            return self._connection.model_copy(deep=True)

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
        """Stop reading, close the receive handle and join the worker."""

        self._stop_event.set()
        with self._lock:
            handle = self._serial
        if handle is not None:
            self._close_handle(handle)
        with self._lock:
            thread = self._thread
        if thread is not None and thread is not current_thread():
            thread.join(timeout=max(1.0, self._read_timeout_s + 0.5))
        with self._lock:
            self._thread = None
            self._serial = None
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

    def feed_bytes(self, data: bytes) -> int:
        """Consume arbitrary read chunks; useful for the reader and deterministic tests."""

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
                )
            except Exception as error:
                self._record_connection_failure(error)
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

            try:
                while not self._stop_event.is_set():
                    chunk = handle.read(self.READ_CHUNK_BYTES)
                    if chunk:
                        self.feed_bytes(chunk)
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
                if self._stop_event.wait(self._reconnect_interval_s):
                    break

    def _process_line(self, line: bytes) -> bool:
        try:
            text = line.decode("utf-8", errors="strict")
            payload = json.loads(text)
            header = SerialPacketHeader.model_validate(payload)
            if header.type != "field_telemetry":
                raise UnsupportedPacketError(
                    f"unsupported serial packet type: {header.type}"
                )
            packet = FieldTelemetryPacket.model_validate(payload)
            self._validate_node_zone_consistency(packet.zone_id, packet.node_id)
            received_at = self._now_provider()
            telemetry = packet.to_zone_telemetry(received_at=received_at)
            self._state_store.update_zone_telemetry(packet.zone_id, telemetry)
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
        LOGGER.warning("Serial telemetry connection unavailable: %s", detail)
        self._set_connection(
            status="ERROR",
            enabled=True,
            configured_port=self._port,
            last_disconnected_at=self._now_provider(),
            last_error=detail,
            reconnect_pending=True,
        )

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

    def _publish_connection(self, connection: SerialConnectionState) -> None:
        self._state_store.update_telemetry_connection(connection)

    @staticmethod
    def _close_handle(handle: SerialPort) -> None:
        try:
            handle.close()
        except Exception:
            LOGGER.exception("Could not close serial telemetry handle cleanly")


serial_bridge = SerialBridge(
    state_store=application_state,
    data_mode=settings.data_mode,
    port=settings.serial_port,
    baud_rate=settings.serial_baud,
    read_timeout_s=settings.serial_read_timeout_s,
    reconnect_interval_s=settings.serial_reconnect_interval_s,
    max_line_bytes=settings.serial_max_line_bytes,
)
