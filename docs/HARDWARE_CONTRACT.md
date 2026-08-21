# Hardware Contract

This document freezes the implemented Milestone 9 inbound telemetry contract
and the Milestone 10 controller command/acknowledgement safety contract.
Sections 6 and 7 of `CODEX_MASTER_REFERENCE.md` remain the architectural source
of truth.

## Shared serial transport

- Transport: USB serial through pySerial.
- Framing in both directions: one complete UTF-8 JSON object followed by `\n`.
- Default baud: `115200`.
- Incoming partial reads are buffered and multiple lines in one read are
  processed in order. Blank lines are ignored and `\r\n` is accepted.
- `SERIAL_MAX_LINE_BYTES` bounds inbound memory. An oversized line is rejected
  through its next newline, after which parsing resumes.
- A dedicated write lock serializes an entire command line in one write call;
  concurrent callers cannot interleave command bytes.
- Read and write timeouts are bounded. All serial I/O is behind an injectable
  interface for tests.
- Environment configuration: `SERIAL_PORT`, `SERIAL_BAUD`,
  `SERIAL_READ_TIMEOUT_S`, `SERIAL_RECONNECT_INTERVAL_S`,
  `SERIAL_MAX_LINE_BYTES`, `COMMAND_ACK_TIMEOUT_S`, `COMMAND_MAX_RETRIES`,
  `COMMAND_MAX_RUNTIME_S`, and `COMMAND_HISTORY_LIMIT`.
- No operating-system-specific serial port is hard-coded.

## Inbound `field_telemetry` (Milestone 9, unchanged)

```json
{
  "schema_version": "1.0",
  "type": "field_telemetry",
  "node_id": "field-node-a",
  "zone_id": "A",
  "timestamp_ms": 1181072,
  "soil_moisture_raw": 2510,
  "soil_moisture_pct": 24.3,
  "temperature_c": 30.6,
  "humidity_pct": 62.4,
  "pressure_pa": 97481.0,
  "gas_resistance_ohm": 62070.0,
  "sraw": 29005,
  "battery_voltage_v": 3.91,
  "battery_pct": 74.0,
  "signal_rssi_dbm": -62.0
}
```

`schema_version`, `type`, `node_id`, and `zone_id` are mandatory. Only version
`1.0`, type `field_telemetry`, and zones `A`/`B` are supported. A nonempty
`node_id` must match the zone's configured `field_node_id` when configured. The
serial port never determines the zone.

Measurement fields are nullable. Missing hardware channels must be JSON `null`;
the backend never substitutes zero, simulation values, or another zone's value.
Numbers must be finite, percentages must be in 0-100, raw/uptime values must be
non-negative, pressure/gas resistance must be positive, and `sraw` must be in
0-65535. Unknown fields are rejected.

Backend `received_at`, not ESP32 `timestamp_ms`, drives freshness. Device uptime
may restart at zero. A zone becomes offline after `ZONE_STALE_SECONDS` without
erasing its last values; a fresh valid packet restores only that zone.

## Backend-to-controller commands (Milestone 10)

Every pump-affecting command has a globally unique `command_id` and a finite
`max_runtime_s`. The backend uses UUID-based IDs by default and supports an
injectable generator in tests. A retry reuses exactly the original packet and
ID. The configured runtime ceiling defaults to 120 seconds and the protocol has
an absolute 3600-second validation ceiling.

### `MIX_WATER`

```json
{
  "schema_version": "1.0",
  "type": "command",
  "command_id": "cmd-...",
  "action": "MIX_WATER",
  "fresh_ml": 250.0,
  "marginal_ml": 150.0,
  "max_runtime_s": 45.0
}
```

Both volumes and runtime must be finite and greater than zero.

### `ADD_FRESH_WATER`

```json
{
  "schema_version": "1.0",
  "type": "command",
  "command_id": "cmd-...",
  "action": "ADD_FRESH_WATER",
  "fresh_ml": 30.0,
  "max_runtime_s": 15.0
}
```

The volume and runtime must be finite and greater than zero.

### `IRRIGATE_ZONE`

```json
{
  "schema_version": "1.0",
  "type": "command",
  "command_id": "cmd-...",
  "action": "IRRIGATE_ZONE",
  "zone_id": "A",
  "volume_ml": 430.0,
  "max_runtime_s": 60.0
}
```

`zone_id` must be `A` or `B`; volume and runtime must be finite and greater than
zero.

### `STOP_ALL`

```json
{
  "schema_version": "1.0",
  "type": "command",
  "command_id": "cmd-stop-...",
  "action": "STOP_ALL"
}
```

`STOP_ALL` intentionally has no runtime because it only turns outputs off. It
is the highest-priority command, bypasses the normal pending-command/IDLE gate,
and is queued when serial communication is unavailable. It cannot interrupt an
already-partially-written JSON line, but the write lock guarantees it is the
next complete command line.

All command schemas forbid unknown fields, invalid actions/versions/zones,
invalid IDs, non-finite values, non-positive quantities, and unbounded runtime
before any serial write occurs.

Milestone 10 exposes no general command/start API. The only public command
endpoint is the deliberate safety action:

```text
POST /api/v1/system/stop-all
```

It sends or queues `STOP_ALL` in hardware mode. In simulation mode it returns a
conflict response and performs no physical I/O.

## Inbound acknowledgement

```json
{
  "schema_version": "1.0",
  "type": "ack",
  "command_id": "cmd-...",
  "status": "accepted"
}
```

The only statuses are:

- `accepted`: the controller accepted this ID;
- `duplicate`: this ID was already handled and was not executed again;
- `rejected`: validation or safety policy rejected it;
- `busy`: the controller could not accept it in its current state.

Only `accepted` and `duplicate` acknowledge command transport success.
`rejected` and `busy` create a rejected lifecycle result and are never treated
as success. Matching is strictly by `command_id`. Unknown, stale, premature, or
conflicting ACKs are rejected/counted and cannot mutate another command.
Repeated identical ACKs are counted without replaying or corrupting history.

## Inbound controller status

```json
{
  "schema_version": "1.0",
  "type": "controller_status",
  "controller_id": "irrigation-controller",
  "state": "IDLE",
  "emergency_stop": false,
  "last_command_id": null,
  "timestamp_ms": 1181300
}
```

Supported reported states are `IDLE`, `MIXING`, `IRRIGATING`,
`EMERGENCY_STOP`, and `FAULT`. The emergency flag must agree with the
`EMERGENCY_STOP` state. Device uptime may restart and is metadata only.

Canonical dashboard safety states are `SIMULATED`, `DISCONNECTED`, `UNKNOWN`,
`IDLE`, `ACTIVE`, `EMERGENCY_STOP`, and `FAULT`. A connected serial gateway is
not controller readiness. Only a valid controller `IDLE` report makes
`controller.ready=true`.

## Command lifecycle, timeout, and history

Each command has one of:

```text
CREATED -> SENT -> ACKNOWLEDGED
                -> REJECTED
                -> TIMED_OUT
                -> FAILED
```

History includes the canonical command, created/latest-send/ACK/update times,
retry count, ACK status/confirmation source, lifecycle status, and a bounded
safe error summary. History defaults to 100 records. A separate bounded recent
ID cache prevents accidental reuse after a record is evicted. No SQLite command
history is introduced in Milestone 10.

ACK timeout defaults to 1.5 seconds, with at most two retries by default. Each
retry uses the same command ID and bytes. There is no infinite retry loop.

## Fail-safe uncertainty rules

The central rule is:

> No ACK does not prove that a physical command never started.

Therefore:

1. Exhausted ACK retries mark the command `TIMED_OUT`.
2. Controller state becomes `UNKNOWN`, `execution_uncertain=true`, and
   `stop_required=true`.
3. A same-transport `STOP_ALL` is issued or queued with priority.
4. An ACK for `STOP_ALL` confirms only command receipt; it does not by itself
   prove all outputs are off.
5. Safety uncertainty clears only after a valid controller status reports
   `IDLE` with emergency stop false.

If serial disconnects while a command awaits ACK or the controller may be
active, the same unsafe state and queued stop apply. On reconnect, the pending
`STOP_ALL` is sent before any normal actuation can be accepted. New non-stop
commands require a fresh `IDLE` status.

The laptop stop is only one safety layer. Controller firmware must enforce each
command's `max_runtime_s` locally and default all pumps/valves OFF on boot,
reset, timeout, or fault. Backend loss must not leave an output energized.

## Controller duplicate-command requirement

Controller firmware must maintain a bounded recent-command-ID cache. When it
receives an already accepted/executed ID, it must not repeat the physical
action; it returns an ACK with status `duplicate`. Cache retention must cover at
least the backend's complete retry window.

The deterministic Milestone 10 mock proves this contract:

```text
cmd-001 physically executes once
ACK is lost
backend retries cmd-001
mock finds cmd-001 in its recent-ID cache
mock returns duplicate
physical action count remains exactly 1
```

Real controller firmware is not implemented in Milestone 10, so physical
exactly-once behavior remains a required firmware contract rather than a claim
about currently connected pumps.

## Mode and malformed-input behavior

- Simulation leaves serial `DISABLED`, opens no port, sends no command, and
  exposes controller state `SIMULATED`. All six demo scenarios remain intact.
- Hardware starts with null/unavailable measurements and controller
  `DISCONNECTED`. It never substitutes simulation data.
- Port open/read/write failures do not crash FastAPI. Reconnect is bounded and
  automatic.
- Malformed JSON/UTF-8, unsupported packets, invalid telemetry, malformed ACKs,
  and invalid controller status are logged/rejected per line; later packets
  continue.
- FastAPI lifespan owns startup/shutdown, closes the serial handle, and joins
  the reader thread.

`GET /api/v1/state` exposes telemetry-gateway state separately from controller
safety/readiness, last command/ACK, communication fault, and bounded history.
Pump/valve state is never displayed unless genuine controller telemetry reports
it.

## Explicitly deferred after Milestone 10

There is no automatic M4/M5/M6 execution, automatic irrigation decision,
approved-decision execution workflow, M11 TDS feedback/correction, M12
irrigation/post-soil verification, freshwater deduction, autonomous pump
sequencing, calibration learning, SQLite expansion, firmware, or model
retraining.
