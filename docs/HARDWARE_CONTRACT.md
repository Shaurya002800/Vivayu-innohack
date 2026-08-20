# Hardware Contract

This document freezes the Milestone 9 inbound telemetry contract. Sections 6
and 7 of `CODEX_MASTER_REFERENCE.md` remain the architectural source of truth.
Milestone 9 implements only receive-side field telemetry; command and actuation
contracts remain deferred.

## Transport and configuration

- Transport: USB serial through pySerial.
- Framing: one complete UTF-8 JSON object followed by `\n`.
- Default baud: `115200`.
- Partial reads are buffered and multiple lines in one read are processed in
  order. Blank lines are ignored and `\r\n` is accepted.
- The buffer is bounded by `SERIAL_MAX_LINE_BYTES`. An oversized line is
  rejected through its next newline, after which normal parsing resumes.
- Configuration is environment-backed: `SERIAL_PORT`, `SERIAL_BAUD`,
  `SERIAL_READ_TIMEOUT_S`, `SERIAL_RECONNECT_INTERVAL_S`, and
  `SERIAL_MAX_LINE_BYTES`. No operating-system-specific port is hard-coded.

## Mandatory inbound packet: `field_telemetry`

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

`schema_version`, `type`, `node_id`, and `zone_id` must be present. The only
supported version is `1.0`, the only Milestone 9 packet type is
`field_telemetry`, and `zone_id` must be `A` or `B`. `node_id` must be nonempty
and, when the zone has a configured `field_node_id`, must match that
configuration. A serial port never determines the zone.

All measurement fields are nullable. Hardware must send JSON `null` when a
physical channel is unavailable. The backend also treats an omitted optional
measurement as unavailable; it never substitutes zero, a simulation value, or
another zone's value.

Validation rules include:

- all numeric values must be finite;
- percentage fields must be between 0 and 100 inclusive;
- raw moisture and uptime must be non-negative integers;
- pressure and gas resistance must be positive when present;
- `sraw` must be an integer from 0 through 65535;
- battery voltage must be non-negative.

Unknown fields are rejected by the canonical packet model. Malformed JSON,
invalid UTF-8, unsupported versions/types, invalid zones, inconsistent nodes,
invalid values, and oversized lines are logged and counted as rejected. One bad
line does not terminate the reader or FastAPI.

## Receive time, device time, and zone freshness

`timestamp_ms` is device uptime metadata. It may return to zero after an ESP32
restart and is not required to increase forever.

For every valid packet, the backend attaches its own timezone-aware
`received_at`. Zone freshness and `telemetry_age_s` use that backend receive
time. A zone is online through `ZONE_STALE_SECONDS` after its latest valid
packet, then becomes offline. Its last telemetry remains available for display
but M4 sees the explicit stale/offline state. A new valid packet immediately
restores that zone online. Freshness is calculated independently for A and B.

## Mode and lifecycle behavior

- In `DATA_MODE=simulation`, serial status is `DISABLED`; the bridge opens no
  port and consumes no serial bytes. All six demo scenarios remain available.
- In `DATA_MODE=hardware`, the canonical state starts with unavailable sensor,
  water, and weather values rather than simulation data. Valid field packets
  enter the same `ZoneTelemetry` state path used by the simulation layer.
- FastAPI lifespan starts and stops the bridge. Startup port failures do not
  crash the API. A configured but unavailable port is retried at the bounded
  configured interval, and disconnects while reading trigger the same recovery
  loop.
- Shutdown closes the receive handle and joins the reader thread.

The canonical `/api/v1/state` response includes receive-gateway status:
`DISABLED`, `CONNECTING`, `CONNECTED`, `DISCONNECTED`, or `ERROR`, plus the
configured port, baud, connection/packet timestamps, last safe error summary,
reconnect state/count, and accepted/rejected packet counters.

Gateway connectivity means only that inbound telemetry can be received. It
does not mean that the irrigation controller, pumps, valves, or actuators are
connected or ready.

## Canonical downstream path

The serial bridge parses and validates packets, then calls the existing state
ingestion method. It does not calculate irrigation or invoke Vivayu directly:

```text
serial field_telemetry
        -> canonical ZoneTelemetry / ZoneState
        -> existing M4 irrigation preview
        -> existing independent M7 Vivayu window when channels are compatible
        -> existing dashboard polling
```

Interleaved A/B packets remain isolated. Missing BME680 gas resistance or SGP40
`sraw` produces the existing explicit Vivayu unavailable result and no
fabricated research-health output.

## Explicitly not implemented in Milestone 9

There are no serial writes, controller commands, command IDs, ACKs, STOP
commands, firmware changes, pump/valve control, irrigation execution, physical
TDS feedback/correction, freshwater deduction, persistent orchestration, or
model retraining. These remain later-milestone work.
