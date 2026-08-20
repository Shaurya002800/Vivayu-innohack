# Implementation Status

## Current milestone

Milestone 9 - Inbound serial telemetry adapter (complete)

## Working

- [x] Milestones 1-8 remain frozen and their existing contracts/tests remain green
- [x] Simulation and hardware both feed the same canonical `SystemState`,
  `ZoneState`, and `ZoneTelemetry` models
- [x] `field_telemetry` has a strict canonical Pydantic packet schema with
  version/type, node, zone, finite-number, percentage, range, and extra-field
  validation
- [x] Missing/omitted physical sensor channels remain `null`; no zero, demo, or
  cross-zone value is substituted
- [x] The receive-only pySerial bridge supports partial reads, multiple lines per
  read, blank lines, CRLF, strict UTF-8, and a configurable maximum line length
- [x] Malformed JSON, invalid UTF-8, unsupported versions/types, invalid zones,
  node/zone mismatches, invalid numbers, and oversized lines are rejected without
  stopping the reader or FastAPI
- [x] Interleaved A/B packets are routed by explicit `zone_id` and remain fully
  isolated; the serial port is never used to infer a zone
- [x] Valid packets call the existing state ingestion path rather than duplicating
  irrigation or Vivayu logic in the bridge
- [x] Five compatible Zone A hardware packets naturally produce M7
  `COLLECTING 1/5` through `READY`, while Zone B remains unchanged
- [x] Missing Vivayu-compatible channels produce the existing explicit
  `UNAVAILABLE` research-health state without fabricated output
- [x] Real-style soil telemetry changes the existing M4 preview through canonical
  state, with no M4 calculation inside the serial adapter
- [x] Backend-owned receive timestamps drive per-zone freshness; device
  `timestamp_ms` may restart at zero after reboot
- [x] Stale zones become offline independently without erasing last-known values,
  and a fresh valid packet restores online state immediately
- [x] Hardware mode starts from safe unavailable/null values and never falls back
  to simulation data
- [x] Simulation mode keeps all six demo scenarios, leaves serial `DISABLED`, and
  never opens or consumes a hardware port
- [x] A configured unavailable port does not crash the backend; bounded reconnect
  attempts continue and recover automatically when a device becomes available
- [x] Disconnects during reads close the old handle and enter the reconnect loop
- [x] FastAPI lifespan owns bridge startup/shutdown; shutdown closes the receive
  handle and joins the reader thread
- [x] The bridge's production interface is receive-only and performs no serial
  writes
- [x] Canonical `/api/v1/state` includes gateway connection status, timestamps,
  last error, configured port/baud, reconnect metadata, and packet counters
- [x] The dashboard labels this as `Telemetry gateway`, shows simulation-only or
  connected/reconnecting state, and does not claim actuator-controller readiness

## Configuration

- `DATA_MODE=simulation|hardware`
- `SERIAL_PORT` (blank/unset by default; no OS-specific port is hard-coded)
- `SERIAL_BAUD=115200`
- `SERIAL_READ_TIMEOUT_S=0.25`
- `SERIAL_RECONNECT_INTERVAL_S=2`
- `SERIAL_MAX_LINE_BYTES=8192`
- `ZONE_STALE_SECONDS=10` controls receive-time zone freshness

The exact implemented inbound packet, framing, rejection, reconnect, staleness,
and mode behavior is frozen in `docs/HARDWARE_CONTRACT.md`.

## Files completed for Milestone 9

- `.env.example`: safe serial configuration defaults
- `backend/app/config.py`: environment-backed serial settings
- `backend/app/schemas.py`: field packet and gateway-state schemas plus additive
  canonical `SystemState.telemetry_connection`
- `backend/app/services/serial_bridge.py`: receive-only framing, validation,
  dispatch, lifecycle, status, and reconnect implementation
- `backend/app/state.py`: backend receive-time freshness, per-zone stale recovery,
  and gateway-state publication
- `backend/app/main.py`: FastAPI lifespan ownership
- `backend/tests/test_serial_bridge.py`: 22 focused unit/integration tests
- `frontend/src/types/index.ts`: matching additive gateway state contract
- `frontend/src/components/dashboard/system-summary.tsx`: truthful telemetry-gateway
  status separate from actuator readiness
- `docs/HARDWARE_CONTRACT.md`: frozen Milestone 9 inbound contract
- `docs/STATUS.md`: this completion record

## Simulation versus hardware after Milestone 9

Simulation has not been removed. In simulation mode, scenario sensor inputs are
demo data and M3-M7 calculations remain real. In hardware mode, genuine ESP32
field packets replace zone telemetry through the same backend path. Water-source
TDS/volume, physical mixed TDS, power, pumps, and valves do not become hardware
data merely because field telemetry is connected; unavailable channels remain
explicitly unavailable.

## Not working / intentionally deferred

- No Milestone 9 blockers.
- No serial writes, controller commands, command IDs, ACK, `STOP_ALL`, firmware,
  pump/valve actuation, or irrigation execution was added.
- No physical mix-TDS verification/correction loop or source-bank deduction exists.
- No persistent decision orchestration or SQLite expansion was added.
- No crop, weather, irrigation, blending, allocation, or Vivayu logic was
  duplicated in the serial bridge or frontend.
- No Vivayu model retraining, threshold change, or frozen legacy-file change was
  made.

## Tests and verification

- Focused Milestone 9 serial suite: `22 passed`
- Complete backend regression suite: `244 passed` (the prior 222 plus 22 M9 tests)
- Python compilation: passed (`.venv/bin/python -m compileall -q app tests`)
- Frontend lint: passed (`npm run lint`)
- Frontend production build and TypeScript check: passed (`npm run build`)
- Patch whitespace/error validation: passed (`git diff --check`)
- Physical serial hardware was not required; serial I/O was tested through an
  injectable deterministic adapter

## Last end-to-end verified paths

```text
five compatible Zone A serial packets
  -> canonical Zone A telemetry
  -> independent Vivayu window
  -> COLLECTING 1/5 ... READY
  -> Zone B unchanged

real-style Zone A soil packet
  -> canonical Zone A state
  -> existing M4 CRITICAL preview and calculated request
```

Reconnect, malformed input recovery, independent A/B staleness, ESP32 uptime
restart, simulation separation, no-write behavior, and clean shutdown are also
covered by automated tests.

## Next exact task

1. Freeze Milestone 9.
2. Connect a physical ESP32 only for a contract smoke test when hardware is
   available; this does not require changing the Milestone 9 design.
3. Begin Milestone 10 only when explicitly authorized: controller command IDs,
   ACK/timeout handling, duplicate-ID safety, and `STOP_ALL` fail-safe behavior.
4. Do not implement TDS correction, irrigation execution, source deduction, or
   broader orchestration as part of Milestone 10 unless separately authorized.
