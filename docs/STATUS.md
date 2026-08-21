# Implementation Status

## Current milestone

Milestone 10 - Controller command/ACK protocol and fail-safe STOP remains
complete and frozen. The post-Milestone-10 real field-sensor telemetry software
integration is implemented and automated checks pass, but it is **not physically
accepted yet**. No Milestone 11 behavior was added.

## Real field telemetry integration (software-ready; bench acceptance pending)

- [x] The field-node sketch reads a capacitive soil probe on an ESP32 ADC1 pin,
  applies a seven-sample median, publishes the real raw value, and calculates a
  clamped 0-100 prototype moisture index only when distinct dry/wet calibration
  references are explicitly compiled in
- [x] Uncalibrated soil percentage is `null`; example calibration values are not
  presented as measurements and the result is not described as VWC
- [x] The field-node sketch reads BME280 temperature, humidity, and pressure,
  tries I2C addresses `0x76` then `0x77`, preserves pressure in Pa on the wire,
  and emits failed/missing channels as `null`
- [x] BME280 failure does not suppress a valid soil channel, and soil failure
  does not suppress valid BME280 channels
- [x] Field nodes send a fixed, versioned internal ESP-NOW frame carrying their
  explicit node and zone identity; the gateway never assigns a zone by arrival
  order
- [x] The gateway emits exactly one frozen `field_telemetry` JSON object plus
  newline at 115200 baud and emits no production debug text on that serial link
- [x] Direct USB smoke mode produces the same canonical JSON contract
- [x] The existing M9 serial bridge remains the sole parser and state-ingestion
  path; no parallel hardware store or duplicate telemetry parser was added
- [x] Backend receive time still controls freshness; per-zone observed packet
  interval/count and explicit wiring/calibration metadata are additive state
  fields
- [x] Hardware Zone A and Zone B remain isolated, retain last readings when
  stale, and start with `null` measurements until real packets arrive
- [x] Hardware-mode scenario load/reset now targets a separate simulation store;
  the permanent demo context can be entered and exited without replacing current
  hardware telemetry
- [x] M4/M5/M6 previews for the isolated demo reuse the existing frozen pure
  functions; no irrigation, water-quality, allocation, or M7 semantics changed
- [x] Zones shows soil as the primary measurement plus temperature, humidity,
  and pressure in farmer-facing hPa, with explicit `LIVE`, `NODE OFFLINE`, or
  `SIMULATED DATA` provenance and last-reading language for stale packets
- [x] System shows the zone/node/source/channel/age/status truth table and an
  advanced hardware panel for real raw/calibrated soil, configured references,
  pins/address, channel availability, packet interval/count, and freshness
- [x] `scripts/watch_telemetry.py` observes canonical `/api/v1/state`; it does
  not open serial or implement another packet parser
- [x] Firmware configuration, per-probe calibration, direct USB/ESP-NOW smoke
  testing, disconnect tests, and physical limitations are documented in
  `firmware/README.md`
- [ ] Physical ESP32/BME280/soil/gateway USB bench test has not been performed in
  this environment; wiring, calibration, RF range, real ~1 Hz stability, and
  dashboard behavior with actual devices are not yet claimed

### Final field packet, pins, calibration, and cadence

The gateway/direct-USB production stream remains the frozen 115200-baud,
one-JSON-object-per-line contract:

```json
{"schema_version":"1.0","type":"field_telemetry","node_id":"field-node-a","zone_id":"A","timestamp_ms":123456,"soil_moisture_raw":2510,"soil_moisture_pct":24.3,"temperature_c":30.6,"humidity_pct":62.4,"pressure_pa":97481.0,"gas_resistance_ohm":null,"sraw":null,"battery_voltage_v":null,"battery_pct":null,"signal_rssi_dbm":null}
```

Unavailable channels are JSON `null`; `nan`, infinities, invented zeroes, debug
text, and cross-zone substitutions are not emitted. Default ESP32 DevKit wiring
is BME280 SDA GPIO 21, SCL GPIO 22, and capacitive soil ADC1 GPIO 34, all
overridable per field-node build. BME280 discovery tries `0x76` then `0x77`.

Each soil probe must be calibrated independently: record its filtered dry
reference, record its fully wet reference, compile those values as
`VIVAYU_SOIL_DRY_RAW`/`VIVAYU_SOIL_WET_RAW`, and mirror them in the matching
backend `ZONE_*` metadata settings. Until the two references differ, the real
raw ADC is sent but calibrated percentage remains `null`. The index is not VWC.

The field loop uses `millis()` scheduling at 1000 ms, a seven-sample median for
soil, and no long blocking delay. With the existing one-second frontend poll,
the designed visible latency is approximately one to two seconds; physical
cadence/latency is not yet measured.

## Working

- [x] Milestones 1-9 remain frozen and all prior regression tests remain green
- [x] Milestone 9 `field_telemetry`, reconnect, stale-node, A/B isolation, M4
  integration, and independent M7 windows are preserved
- [x] Strict canonical version-1.0 schemas exist for `MIX_WATER`,
  `ADD_FRESH_WATER`, `IRRIGATE_ZONE`, and `STOP_ALL`
- [x] Pump-affecting commands require positive finite volumes and finite bounded
  `max_runtime_s`; STOP contains no positive-action fields
- [x] Unsupported versions/actions, invalid zones/IDs, non-finite values,
  invalid runtime, and unknown fields are rejected before serial write
- [x] Default command IDs use UUIDs; generation is injectable for deterministic
  tests and recent issued IDs are retained in a bounded duplicate guard
- [x] Outbound commands use the same newline-delimited UTF-8 JSON transport as
  inbound telemetry and are serialized into exactly one line
- [x] A dedicated write lock prevents concurrent command bytes from interleaving
- [x] ACK vocabulary is constrained to `accepted`, `duplicate`, `rejected`, and
  `busy`; unknown statuses are never treated as success
- [x] ACK matching is strictly by `command_id`; unknown, stale, premature, and
  conflicting ACKs cannot complete another command
- [x] Command lifecycle is explicit: `CREATED`, `SENT`, `ACKNOWLEDGED`,
  `REJECTED`, `TIMED_OUT`, and `FAILED`
- [x] History stores command/action, created/latest-send/ACK/update timestamps,
  retries, status, confirmation source, and safe error text
- [x] Command history and the recent-ID guard are bounded in memory
- [x] ACK retries are finite/configurable and reuse the exact same command ID and
  serialized packet
- [x] The deterministic lost-ACK integration proves duplicate retry handling:
  `cmd-001` is sent twice while mock physical action count remains exactly one
- [x] Strict inbound `controller_status` supports `IDLE`, `MIXING`, `IRRIGATING`,
  `EMERGENCY_STOP`, and `FAULT`, with emergency-flag consistency validation
- [x] Canonical controller safety truth is separate from telemetry-gateway
  connectivity: `SIMULATED`, `DISCONNECTED`, `UNKNOWN`, `IDLE`, `ACTIVE`,
  `EMERGENCY_STOP`, or `FAULT`
- [x] Only a genuine controller `IDLE` report sets `controller.ready=true`
- [x] `STOP_ALL` bypasses normal readiness/pending-command gates and is next in
  the locked write order even when another command awaits ACK
- [x] `emergency_stop()` safely sends or queues STOP in hardware mode
- [x] `POST /api/v1/system/stop-all` is the only public controller-command
  endpoint; there is no irrigation/start/execute endpoint
- [x] Simulation rejects emergency-stop command I/O explicitly, remains labelled
  `SIMULATED`, opens no serial port, and keeps all six scenarios
- [x] ACK timeout or uncertain disconnect marks controller execution unknown,
  requires STOP, and never assumes the original physical action did not start
- [x] Reconnect sends a queued STOP before normal commands can be accepted
- [x] STOP ACK alone does not clear uncertainty; controller `IDLE` is required
- [x] The fail-safe integration proves `command -> timeout -> UNKNOWN -> STOP ->
  EMERGENCY_STOP -> IDLE -> safe`
- [x] Hardware mode still starts from null/unavailable values and never falls
  back to demo data
- [x] M4/M5/M6 outputs are not connected to command transport and water banks are
  not deducted
- [x] The dashboard shows telemetry gateway and controller readiness separately
- [x] Hardware mode adds a deliberate two-click emergency STOP control with a
  five-second confirmation window; it exposes no irrigation-start control
- [x] FastAPI lifespan still owns clean bridge startup, handle closure, and thread
  shutdown
- [x] The dashboard information architecture is now split into five focused
  destinations: Overview, Zones, Water, Insights, and System
- [x] Overview answers the farmer's immediate questions first: what needs
  attention, which field is affected, whether water is available, and whether
  the system is connected
- [x] The farm visual is a functional Zone A/Zone B selector backed by canonical
  telemetry and backend decision results; it contains no invented field values
- [x] Zones displays one selected field at a time, with independent moisture,
  crop/stage, environment, M4 plan, M5 plan, M6 allocation, and M7 research state
- [x] Water visualizes source banks, the safe blend, predicted-versus-target TDS,
  measured-TDS unavailability, freshwater allocation, and safe-ratio preservation
- [x] Insights presents human-readable backend reasons first and keeps technical
  reason/warning codes behind progressive disclosure
- [x] System contains provenance, gateway/controller separation, power/weather
  availability, independent sensor channels, six simulation controls, command
  history, and the hardware-only two-click STOP control
- [x] Responsive layouts were verified at 1440, 1024, 768, 430, and 390 pixels;
  mobile uses a five-item 54-pixel bottom navigation with no horizontal overflow
- [x] Loading, disconnected, stale-data, simulation, hardware, research-only,
  pending-hardware, and unavailable/null states remain explicit

## Configuration

- `DATA_MODE=simulation|hardware`
- `SERIAL_PORT` (blank/unset by default)
- `SERIAL_BAUD=115200`
- `SERIAL_READ_TIMEOUT_S=0.25`
- `SERIAL_RECONNECT_INTERVAL_S=2`
- `SERIAL_MAX_LINE_BYTES=8192`
- `COMMAND_ACK_TIMEOUT_S=1.5`
- `COMMAND_MAX_RETRIES=2`
- `COMMAND_MAX_RUNTIME_S=120`
- `COMMAND_HISTORY_LIMIT=100`
- `ZONE_STALE_SECONDS=10`
- `FIELD_TELEMETRY_INTERVAL_S=1`
- `ZONE_A_SOIL_DRY_RAW`, `ZONE_A_SOIL_WET_RAW`, `ZONE_A_SOIL_ADC_PIN`
- `ZONE_A_BME280_I2C_ADDRESS`, `ZONE_A_I2C_SDA_PIN`, `ZONE_A_I2C_SCL_PIN`
- equivalent `ZONE_B_*` sensor settings

The exact packet, command, ACK, duplicate, timeout, reconnect, controller-state,
and firmware safety obligations are frozen in `docs/HARDWARE_CONTRACT.md`.

## Files completed for Milestone 10

- `.env.example`: command timeout/retry/runtime/history defaults
- `backend/app/config.py`: environment-backed M10 settings
- `backend/app/schemas.py`: strict action commands, ACK/status packets, lifecycle
  history, controller safety state, and additive `SystemState.controller`
- `backend/app/services/serial_bridge.py`: locked writes, command IDs/history,
  ACK dispatch, retries/timeouts, controller status, disconnect uncertainty, and
  priority STOP behavior while preserving M9 telemetry
- `backend/app/services/actuation_service.py`: explicit later-milestone execution
  boundary
- `backend/app/state.py`: canonical controller-state publication and mode safety
- `backend/app/api/controller.py`: emergency-stop-only API
- `backend/app/main.py`: controller router registration
- `backend/tests/test_controller_protocol.py`: 29 focused protocol/safety tests
- `backend/tests/test_serial_bridge.py`: M9 duplex-factory expectation retained
- `backend/tests/test_state_api.py`: additive controller state and simulation-stop
  API assertions
- `frontend/src/types/index.ts`: exact command/controller response types
- `frontend/src/lib/api.ts`: emergency-stop API call
- `frontend/src/hooks/use-dashboard-data.ts`: explicit stop action/refresh state
- `frontend/src/components/dashboard/emergency-stop-control.tsx`: deliberate
  hardware-only two-stage STOP control
- `frontend/src/components/dashboard/system-summary.tsx`: separate gateway and
  controller truth
- `frontend/src/components/dashboard/dashboard.tsx`: hardware safety control and
  no-start boundary
- `frontend/src/app/globals.css`: responsive controller/STOP presentation
- `docs/HARDWARE_CONTRACT.md`: frozen M9+M10 serial safety contract
- `docs/STATUS.md`: this completion record

## Files completed for the dashboard redesign

- `frontend/src/components/dashboard/dashboard.tsx`: focused view routing,
  selected-zone state, truthful loading/offline states, and shared app shell
- `frontend/src/components/shell/`: branded responsive shell and desktop/mobile
  product navigation
- `frontend/src/components/overview/`: contextual hero, interactive two-zone farm
  visual, status strip, and farmer task shortcuts
- `frontend/src/components/zones/`: isolated zone selector and single-zone
  moisture/crop/irrigation/water/health workspace
- `frontend/src/components/water/`: source-to-blend flow, TDS truth, scarcity bank,
  ratio-safety state, and allocation explanation
- `frontend/src/components/insights/`: farmer-readable decision path, M4/M5/M6
  reasons, technical disclosures, and research-only M7 section
- `frontend/src/components/system/`: data provenance, connections, controller,
  power, weather, sensor status, simulations, and command history
- `frontend/src/components/ui/icon.tsx`: lightweight accessible presentation icon
  set with no new runtime dependency
- `frontend/src/lib/presentation.ts`: presentation-only farmer labels and farm
  condition selection; domain calculations remain backend-owned
- `frontend/src/app/globals.css`: complete responsive visual system, layout,
  focus states, touch targets, reduced-motion handling, and breakpoint composition
- `docs/STATUS.md`: redesign scope and verification record

## Files completed for real field telemetry integration

- `.env.example`: field interval and per-zone physical sensor provenance
- `firmware/common/field_telemetry_frame.h`: explicit fixed ESP-NOW payload
- `firmware/common/telemetry_math.h`: soil-index mapping/clamp and Pa boundary
- `firmware/field_node/field_node.ino`: median soil sampling, BME280 acquisition,
  independent nullable channels, ESP-NOW, and direct USB smoke mode
- `firmware/gateway_node/gateway_node.ino`: validated ESP-NOW receive queue and
  frozen newline-delimited JSON output
- `firmware/tests/test_telemetry_math.cpp`: host-side calibration/pressure tests
- `firmware/README.md`: build configuration, calibration, smoke test, and limits
- `backend/app/config.py`: environment-backed per-zone sensor metadata
- `backend/app/schemas.py`: additive hardware telemetry provenance and isolated
  dashboard snapshot schemas
- `backend/app/state.py`: per-zone packet timing/count plus isolated hardware and
  demo stores
- `backend/app/services/dashboard_snapshot.py`: read-only reuse of frozen M4-M6
  preview functions for an explicitly supplied state
- `backend/app/api/simulation.py`: isolated demo list/load/reset/snapshot API
- `backend/tests/test_hardware_telemetry_integration.py`: physical-channel,
  malformed-value, timing/stale, and demo-isolation coverage
- `backend/tests/test_state_api.py`: visibly simulated snapshot API coverage
- `frontend/src/types/index.ts`, `frontend/src/lib/api.ts`, and
  `frontend/src/hooks/use-dashboard-data.ts`: typed live/demo polling boundary
- `frontend/src/components/dashboard/dashboard.tsx`, shell, Zones, and System
  views plus `frontend/src/app/globals.css`: live/stale/simulated provenance,
  BME280 presentation, hardware diagnostics, and permanent demo labelling
- `scripts/watch_telemetry.py`: backend telemetry smoke watcher

## Safety boundary

An ACK timeout does not prove a pump never started. The backend therefore marks
execution uncertain and prioritizes STOP until the controller reports IDLE.
Every positive command retains `max_runtime_s` because final firmware must stop
outputs locally if the laptop disappears. No physical controller firmware was
implemented or exercised in this milestone, so actual pumps-off behavior is a
documented firmware obligation, not a fabricated software claim.

## Not working / intentionally deferred

- No Milestone 10 software blockers.
- No automatic irrigation decisions, M4/M5/M6 execution wiring, approved
  decision execution, or general start endpoint was added.
- No M11 TDS feedback/correction or physical mixed-water approval exists.
- No M12 irrigation execution, post-soil verification, freshwater deduction,
  adaptive calibration, or event persistence exists.
- No autonomous pump sequencing, firmware, manual pump toggle, or actuator-state
  claim was added.
- No crop/weather/water/Vivayu calculation was duplicated or changed.
- No model retraining, frozen legacy-file change, or SQLite expansion was made.
- No API contract, backend calculation, irrigation logic, controller behavior,
  scenario data, crop profile, weather adapter, or legacy model semantics changed
  during the dashboard redesign.
- Historical trend charts remain intentionally unavailable because no canonical
  history endpoint exists; the UI states this instead of fabricating a chart.
- Physical field hardware was unavailable in this environment. Firmware has not
  been flashed, and ESP-NOW delivery, BME280 wiring/address, soil calibration,
  USB serial device selection, and real packet cadence remain unverified.
- `arduino-cli`/PlatformIO is not installed in this workspace, so the full ESP32
  sketches were not compiled against board libraries here. Host-side pure C++
  telemetry math compilation passed.

## Tests and verification

- Focused Milestone 10 protocol/safety suite: `29 passed`
- Focused real telemetry/state API suite: `19 passed`
- Complete backend regression suite: `286 passed`
- Python compilation: passed (`.venv/bin/python -m compileall -q app tests`)
- Firmware telemetry math host compile/run: passed
  (`c++ -std=c++17 firmware/tests/test_telemetry_math.cpp ...`)
- Frontend lint: passed (`npm run lint`)
- Frontend production build and TypeScript check: passed (`npm run build`)
- Patch whitespace/error validation: passed (`git diff --check`)
- Physical controller: not connected; deterministic injectable duplex serial and
  mock-controller contracts were used
- In-app browser functional QA: passed against live local frontend/backend for
  Overview, Zone A/B selection, Water, Insights, System, all six scenario
  controls, research-only boundaries, pending-hardware/null labels, and technical
  disclosure
- Real telemetry UI browser QA: passed with a hardware-mode backend and no serial
  device: live hardware showed null/offline sensor truth, Zones showed BME280
  channels as unavailable, the isolated freshwater-shortage scenario displayed
  a permanent `DEMO MODE · SIMULATED DATA` banner, and return-to-live restored
  the unchanged hardware state
- Responsive browser QA: passed at 1440, 1024, 768, 430, and 390 pixels with no
  horizontal document overflow; desktop, tablet, and mobile navigation states
  were verified

## Last critical integration runs

```text
cmd-001 sent
  -> ACK lost
  -> cmd-001 retried unchanged
  -> mock duplicate-ID cache returns duplicate
  -> physical action count = 1

IRRIGATE_ZONE sent
  -> ACK timeout
  -> controller UNKNOWN / execution uncertain
  -> STOP_ALL written with priority
  -> STOP ACK does not clear uncertainty
  -> controller EMERGENCY_STOP report
  -> controller IDLE report
  -> ready/safe state restored
```

A/B field telemetry isolation, null handling, M4 flow, M7 rolling windows,
simulation separation, reconnect handling, clean shutdown, no automatic writes,
and no water deduction remain covered by the complete suite.

## Next exact task

1. Keep Milestone 10 and the farmer-first dashboard redesign frozen.
2. Install/select the ESP32 board toolchain and required Arduino libraries, then
   compile both field-node variants and the gateway sketch.
3. Flash one direct-USB field node first, record real dry/wet values for that
   exact probe, configure the same metadata in the backend, and verify all
   nullable channel/disconnect/stale behaviors with `scripts/watch_telemetry.py`.
4. Flash distinct Zone A and Zone B nodes plus the ESP-NOW gateway and complete
   the isolation/demo-return/dashboard physical acceptance checklist in
   `firmware/README.md`. Only then freeze the real telemetry integration.
5. When controller hardware is available, perform a contract smoke test for
   newline framing, duplicate-ID cache, local `max_runtime_s`, STOP priority, and
   IDLE recovery without changing M10 semantics.
6. Begin Milestone 11 only when explicitly authorized: MIX -> VERIFY_TDS ->
   bounded fresh correction/retry -> approve/fault.
7. Do not add irrigation execution, post-soil verification, freshwater
   deduction, or adaptive calibration until Milestone 12 is separately approved.
