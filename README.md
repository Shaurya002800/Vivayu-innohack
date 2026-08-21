# VIVAYU Aqua

VIVAYU Aqua is a two-zone, scarcity-aware and water-quality-aware irrigation
intelligence platform built for InnoHack 2.0. It combines field telemetry,
crop and growth-stage context, cached weather, freshwater availability, and
source-water TDS to produce transparent irrigation and water-allocation plans.

The central idea is simple: freshwater is treated as a scarce resource, and
water quality is treated as a decision variable. The system determines not
only whether a zone needs water, but also whether that water should come from a
fresh source, a marginal-quality source, or a controlled blend.

> Current status: Milestones 1–10 are implemented and frozen. The real field
> telemetry software path is ready, but physical ESP32, sensor, RF, calibration,
> and pump-controller acceptance is still pending. The application does **not**
> yet autonomously execute irrigation.

[Watch the silent animated end-to-end system flow](demo_video/output/vivayu-aqua-dynamic-flow.mp4)

## System flow

```text
Zone A sensors ─┐
                ├─ ESP-NOW ─ Gateway ESP32 ─ USB serial ─ FastAPI state
Zone B sensors ─┘                                         │
                                                          v
Sensors → Crop + stage → Weather → Irrigation need (M4)
                                          │
                                          v
                         Water strategy / TDS plan (M5)
                                          │
                                          v
                      Scarce freshwater allocation (M6)
                                          │
                                          v
                   Vivayu research health context (M7)
                                          │
                                          v
                          Farmer-first Next.js dashboard
```

The legacy Vivayu result is a research-only monitoring signal. It is displayed
as context and never directly triggers or blocks irrigation.

## What currently works

| Area | Implemented behavior |
| --- | --- |
| Application state | Canonical typed state with completely isolated Zone A and Zone B configuration, telemetry, decisions, and Vivayu windows |
| Simulation | Six deterministic, visibly labelled scenarios with a store isolated from live hardware state |
| Crop intelligence | Crop validation, sowing-date calculation, automatic stage estimation, manual stage override, and source metadata |
| Weather | Six-hour forecast summary, configurable provider/location, caching, stale status, timeout handling, and last-good fallback |
| Irrigation need — M4 | Explainable water-need and priority previews using soil deficit, crop stage, rain, ET0, and critical-moisture rules |
| Water strategy — M5 | `FRESH_ONLY`, `MARGINAL_ONLY`, and `CONTROLLED_BLEND` previews with source limits, predicted TDS, safety margin, reasons, and warnings |
| Allocation — M6 | Deterministic two-zone freshwater allocation that never exceeds the bank and preserves the safe fresh:marginal ratio when a plan is scaled down |
| Vivayu — M7 | One five-reading legacy predictor per compatible zone, explicit collecting/unavailable states, and research-only output |
| Dashboard — M8 | Responsive Overview, Zones, Water, Insights, and System views with progressive disclosure and explicit null/provenance states |
| Serial telemetry — M9 | Strict versioned line-delimited JSON parsing, reconnect handling, freshness tracking, malformed-line recovery, and per-zone routing |
| Controller protocol — M10 | Typed commands, unique IDs, ACK matching, bounded retry/history, uncertainty tracking, and priority `STOP_ALL` behavior |
| Field firmware | BME280 plus capacitive-soil field nodes, seven-sample soil median, explicit node/zone identity, ESP-NOW gateway, and direct-USB smoke mode |

Unavailable real sensors remain `null`. Hardware mode never falls back to
simulation data, and opening a demo scenario never overwrites live telemetry.

## Deliberate safety boundary

The repository currently exposes decision and allocation **previews**, not an
automatic irrigation start path.

- Pumps and valves are expected to default OFF.
- The only public controller command endpoint is the emergency safety action
  `POST /api/v1/system/stop-all`.
- Missing or stale telemetry, unsafe/missing TDS, invalid crop configuration,
  controller disconnect, and malformed commands block future automatic
  actuation.
- An ACK timeout is treated as uncertain execution, not proof that a pump never
  started. The backend prioritizes STOP and requires a genuine controller
  `IDLE` report before clearing uncertainty.
- Simulation mode opens no serial port and cannot issue controller commands.
- Power, solar, TDS, VOC, battery, or other unavailable hardware channels are
  shown as unavailable rather than populated with invented values.

Not yet implemented or physically accepted:

- Milestone 11 mixed-water TDS feedback and bounded correction state machine;
- Milestone 12 irrigation execution, post-soil verification, freshwater
  deduction, adaptive field-response updates, and event persistence;
- real pump/valve controller firmware and physical exactly-once behavior;
- physical wiring, calibration, RF-range, packet-cadence, and end-to-end field
  acceptance.

See [Implementation Status](docs/STATUS.md) for the exact acceptance record and
current blockers.

## Repository layout

```text
backend/          FastAPI API, typed schemas, state, domain services, and tests
frontend/         Next.js/TypeScript farmer- and judge-facing dashboard
firmware/         ESP32 field-node/gateway code and controller safety boundary
legacy/vivayu/    Pinned upstream research pipeline and model snapshot
scripts/          Demo, calibration, and canonical telemetry watcher utilities
demo_video/       Silent animated flow demo and its deterministic renderer
docs/             Master specification, status, contracts, decisions, runbook
runtime/          Ignored local runtime data and logs
```

Do not casually modify `legacy/vivayu`. Its custom model class and saved joblib
bundle must remain compatible with the pinned research runtime.

## Quick start: simulation mode

Simulation is the safe default and requires no hardware.

### Prerequisites

- Python 3.11 or newer
- Node.js 20 or newer
- npm

### 1. Start the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2. Start the frontend in a second terminal

```bash
cd frontend
npm ci
npm run dev
```

Open:

- Dashboard: <http://localhost:3000>
- API documentation: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/api/v1/health>
- Canonical state: <http://localhost:8000/api/v1/state>

The frontend uses `http://localhost:8000` by default. Override it before
starting Next.js when needed:

```bash
export NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev
```

## Simulation scenarios

The System view can load all scenarios without touching hardware state.

| Scenario | Demonstrates |
| --- | --- |
| Zone A critical | Critical Zone A priority under low near-term rain |
| Rain soon | Moderate dryness deferred or reduced by forecast rain |
| TDS correction | An intentionally high final mix reading for the future correction workflow |
| Freshwater shortage | Two-zone scarcity allocation and proportional safe-ratio scaling |
| Sensor offline | Stale Zone A telemetry and blocked automatic action |
| Legacy ML unavailable | Zone B irrigation intelligence continuing without compatible VOC channels |

List or load scenarios directly:

```bash
curl http://localhost:8000/api/v1/simulation/scenarios

curl -X POST http://localhost:8000/api/v1/simulation/load \
  -H 'Content-Type: application/json' \
  -d '{"scenario_id":"freshwater_shortage"}'

curl -X POST http://localhost:8000/api/v1/simulation/reset
```

Every scenario remains permanently labelled as simulated. Scenario outputs are
decision previews and never silently actuate hardware.

## Hardware telemetry mode

The hardware telemetry path supports one identified ESP32 field node per zone,
a shared ESP-NOW gateway, and the same canonical backend state used by
simulation. The current field-node build reads:

- capacitive soil probe on an ESP32 ADC1 pin;
- BME280 temperature, humidity, and pressure;
- unavailable gas resistance, `sraw`, battery, and signal channels as `null`.

BME280-only nodes cannot run the legacy Vivayu gas-resistance model. The
dashboard correctly reports that research signal as unavailable while the
soil/crop/weather/TDS intelligence remains usable.

To start the backend in hardware mode, export the actual USB port and settings
in the same terminal before running Uvicorn:

```bash
export DATA_MODE=hardware
export SERIAL_PORT=/dev/cu.usbserial-0001
export SERIAL_BAUD=115200

cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Settings are read from process environment variables; `.env.example` is the
complete configuration template but is not loaded automatically.

Watch the backend's canonical state without opening a second serial parser:

```bash
python3 scripts/watch_telemetry.py
```

Before connecting devices, follow the calibration, build-macro, direct-USB,
ESP-NOW, and disconnect checklist in [Firmware Setup](firmware/README.md). The
complete serial and fail-safe requirements are frozen in the
[Hardware Contract](docs/HARDWARE_CONTRACT.md).

## Important configuration

Safe defaults and every supported setting are documented in
[`.env.example`](.env.example). The most important groups are:

```text
DATA_MODE=simulation|hardware
SERIAL_PORT=<actual USB serial device>
SERIAL_BAUD=115200
ZONE_STALE_SECONDS=10
FIELD_TELEMETRY_INTERVAL_S=1

FARM_LATITUDE=<farm latitude>
FARM_LONGITUDE=<farm longitude>
WEATHER_PROVIDER=open-meteo
WEATHER_CACHE_MINUTES=15

ZONE_A_SOIL_DRY_RAW=<measured reference>
ZONE_A_SOIL_WET_RAW=<measured reference>
ZONE_B_SOIL_DRY_RAW=<measured reference>
ZONE_B_SOIL_WET_RAW=<measured reference>

COMMAND_ACK_TIMEOUT_S=1.5
COMMAND_MAX_RETRIES=2
COMMAND_MAX_RUNTIME_S=120
```

Each soil probe must be calibrated independently. Until its dry and wet
references are distinct, firmware publishes the real raw ADC value but keeps
the percentage `null`. The displayed result is a prototype calibrated moisture
index, not universal volumetric water content.

## Primary API endpoints

All endpoints use the `/api/v1` prefix.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Backend and configured data-mode health |
| `GET` | `/state` | Complete canonical application state |
| `GET` | `/zones` | Independent Zone A and Zone B state |
| `PUT` | `/zones/{zone_id}/config` | Update crop, sowing date, or stage configuration |
| `GET` | `/zones/{zone_id}/irrigation-need` | M4 irrigation-need preview |
| `GET` | `/water/zones/{zone_id}/strategy` | M5 source-water strategy preview |
| `GET` | `/water/allocation-preview` | M6 two-zone scarcity allocation |
| `GET` | `/weather` | Current simulation or cached live forecast state |
| `GET` | `/simulation/scenarios` | List the six deterministic demos |
| `POST` | `/simulation/load` | Load a scenario into the isolated demo store |
| `POST` | `/simulation/reset` | Reset the demo store |
| `GET` | `/simulation/snapshot` | Read the complete isolated demo preview |
| `POST` | `/system/stop-all` | Hardware-only emergency STOP/queue action |

Swagger at <http://localhost:8000/docs> is the authoritative interactive API
reference for request and response schemas.

## Tests and quality checks

Run the complete backend suite:

```bash
cd backend
source .venv/bin/activate
pytest -q
python -m compileall -q app tests
```

Run frontend checks:

```bash
cd frontend
npm run lint
npm run build
```

Run the host-side pure firmware math test:

```bash
c++ -std=c++17 firmware/tests/test_telemetry_math.cpp \
  -o /tmp/vivayu-telemetry-math-test
/tmp/vivayu-telemetry-math-test
```

Last recorded full verification:

- backend: **286 passed**;
- frontend lint: passed;
- frontend production build and TypeScript check: passed;
- firmware telemetry-math host compile/run: passed;
- responsive browser QA: passed at 1440, 1024, 768, 430, and 390 pixels;
- physical ESP32/sensor/controller acceptance: **pending**.

## Scientific and product boundaries

- TDS is a practical dissolved-solids/salinity proxy; it does not identify
  individual ions or prove long-term root-zone safety.
- Crop salinity and moisture values are configurable and carry source/prototype
  metadata; they are not presented as universal agronomic guarantees.
- Soil percentages are sensor/probe calibration indices unless independently
  validated for a specific soil.
- The pinned Vivayu model comes from a small tomato experiment. Its output is
  not a diagnosis, treatment recommendation, or calibrated field probability.
- BME680, SGP40, AGS10, and BME280 channels are not interchangeable in the
  legacy model.
- The project makes no water-saving percentage claim without a measured
  baseline.

## Project documentation

- [Codex Master Reference](docs/CODEX_MASTER_REFERENCE.md) — source of truth and milestone specification
- [Implementation Status](docs/STATUS.md) — exact completed work, tests, blockers, and next task
- [Hardware Contract](docs/HARDWARE_CONTRACT.md) — telemetry, command, ACK, timeout, and fail-safe protocol
- [Firmware Setup](firmware/README.md) — wiring assumptions, calibration, build configuration, and bench checklist
- [Architecture Decisions](docs/DECISIONS.md) — accepted design boundaries
- [Demo Runbook](docs/DEMO_RUNBOOK.md) — deterministic demo flow notes
- [Legacy Vivayu Upstream](legacy/vivayu/UPSTREAM.md) — pinned research snapshot provenance

## Next work

1. Compile and flash the field-node and gateway sketches with the ESP32 Arduino
   toolchain and required libraries.
2. Calibrate each physical soil probe and complete direct-USB, ESP-NOW,
   disconnect, cadence, and Zone A/B isolation acceptance.
3. Validate the command/ACK/duplicate/STOP contract against real controller
   hardware when available.
4. Begin Milestone 11 only when explicitly authorized: mix, verify final TDS,
   perform bounded fresh correction, and approve or fault.
5. Keep irrigation execution and post-soil verification deferred until
   Milestone 12 is separately authorized.

---

**VIVAYU Aqua:** real field signals, explicit uncertainty, explainable water
decisions, and safer use of scarce freshwater.
