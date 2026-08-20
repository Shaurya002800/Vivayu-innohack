# Implementation Status

## Current milestone

Milestone 8 - Judge-facing VIVAYU Aqua dashboard (complete)

## Working

- [x] The Milestone 1 placeholder has been replaced with a polished responsive dark-agritech dashboard
- [x] The dashboard uses strongly typed frontend contracts matching the frozen backend state, M4, M5, M6, M7, and simulation responses
- [x] A centralized API client polls the canonical read-only previews approximately once per second
- [x] Backend request timeouts, initial loading, connection failure, and last-known-state interruption states are explicit
- [x] An unavailable backend never defaults the data mode to simulation and never supplies fallback sensor values
- [x] The header shows VIVAYU Aqua branding, backend-derived SIMULATION/LIVE mode, active scenario, update time, and connectivity
- [x] The farm overview shows both source banks/TDS values, six-hour rain, ET0, temperature, controller status, and power status
- [x] Controller and power remain explicitly `Not connected`; no fake solar watts, battery state, pump, valve, or completion state is shown
- [x] Zone A and Zone B render as independent cards with crop, growth stage, days after sowing, node status, soil moisture, configured target/critical thresholds, and environmental telemetry
- [x] M4 cards show backend irrigation status, prototype request, urgency label/score, and no frontend water-need calculation
- [x] M5 cards show backend strategy, safe source volumes/fractions, source-ratio visualization, and explicitly `Predicted TDS`
- [x] Physical mix TDS remains `Pending hardware`; scenario fixture values are not presented as completed physical verification
- [x] M6 cards show allocation status, source allocations, deliverable/requested water, and service fraction
- [x] The global allocation panel shows freshwater availability, full-service requirement, allocated/remaining water, marginal allocation, scarcity, total requested/deliverable water, and both zone service fractions
- [x] Partial delivery visualizes the frozen safe ratio rather than retaining excess marginal water
- [x] M7 cards support `COLLECTING`, `READY`, `UNAVAILABLE`, and `ERROR` canonical states
- [x] Every Vivayu card displays `RESEARCH ONLY` and states that the VOC-pattern signal neither diagnoses disease nor controls irrigation
- [x] Vivayu patterns are displayed verbatim and are never relabelled as confirmed disease or infection
- [x] The explainability panel displays backend reason codes, reasons, and warnings for M4, M5, per-zone M6, and global allocation
- [x] The frontend does not invent explanations or recalculate backend policy
- [x] Six simulation controls load existing scenarios and apply explicit backend prototype calibration for judge-ready planning previews
- [x] Scenario controls are labelled simulation-only and state that no hardware command is sent
- [x] Reset uses the existing simulation reset API and restores the canonical unconfigured baseline
- [x] The primary 1366–1920px laptop layout is compact; 1440px and 900px browser checks show no horizontal overflow

## Frontend architecture

- `frontend/src/types/index.ts`: canonical response interfaces with nullable unavailable fields and no `any` for core state
- `frontend/src/lib/api.ts`: centralized timeout-protected API client, parallel dashboard snapshot reads, and simulation actions
- `frontend/src/lib/formatting.ts`: null-safe display formatting and semantic status tones
- `frontend/src/hooks/use-dashboard-data.ts`: one-second polling, stale snapshot retention, action states, and error recovery
- `frontend/src/components/dashboard/dashboard.tsx`: dashboard composition plus loading/offline states
- `frontend/src/components/dashboard/dashboard-header.tsx`: branding, mode, scenario, update, and connectivity
- `frontend/src/components/dashboard/system-summary.tsx`: source, weather, controller, and power truth
- `frontend/src/components/dashboard/zone-card.tsx`: independent zone context, moisture, M4/M5/M6, and M7 composition
- `frontend/src/components/dashboard/irrigation-panel.tsx`: backend M4 preview
- `frontend/src/components/dashboard/water-strategy.tsx`: backend M5 strategy and predicted TDS
- `frontend/src/components/dashboard/allocation-overview.tsx`: global M6 resource accounting
- `frontend/src/components/dashboard/vivayu-health-card.tsx`: all canonical research-health render states
- `frontend/src/components/dashboard/explanation-panel.tsx`: backend-authored explanations and warnings
- `frontend/src/components/dashboard/simulation-controls.tsx`: six scenario actions and reset
- `frontend/src/components/dashboard/status-pill.tsx`: accessible semantic state vocabulary
- `frontend/src/app/globals.css`: responsive visual system, status colors, bars, cards, and accessibility motion fallback
- `frontend/src/app/page.tsx`: final dashboard entry point
- The obsolete `frontend/src/components/health-status.tsx` placeholder was removed

## Demo calibration boundary

- Existing backend endpoints remain unchanged.
- When a judge activates a scenario, the client loads it through `/api/v1/simulation/load`, then explicitly configures both zones with the prototype values already exercised by backend tests: target `45%`, critical `25%`, `20 mL` per moisture point, and maximum incoming-water TDS `450 ppm`.
- These are visibly prototype/configured values, not fabricated sensor readings or universal agronomic claims.
- All irrigation amount, rain response, source strategy, predicted TDS, and scarcity allocation remain backend calculations.

## Browser QA completed

- Baseline: explicit `CONFIG_REQUIRED` M4/M5 and blocked M6 with no invented values
- Zone A critical: Zone A `CRITICAL`, Zone B `NEEDED`, both independently served
- Rain soon: Zone A `DEFER_FOR_RAIN` with `0 mL` backend request
- TDS correction fixture: controlled-blend predicted TDS remains labelled predicted; measured mix stays `Pending hardware`
- Freshwater shortage: scarcity active, Zone A partially served at `85%`, Zone B deferred at `0%`, bank accounting visible
- Sensor offline: Zone A node offline and M4 sensor unavailable while Zone B remains online
- Legacy ML unavailable: Zone A collecting independently; Zone B unavailable for the explicit BME280 compatibility reason while M4/M5 remain operational
- All six scenario buttons, active-state treatment, and reset were exercised through the rendered UI
- Browser console: no warnings or errors
- Responsive checks: no horizontal overflow at 1440px or 900px
- The `READY` Vivayu render path is type-checked in the production build against the frozen canonical contract; the current public simulation API exposes collecting/unavailable states because telemetry ingestion remains deferred to Milestone 9, while backend M7 tests cover the five-reading ready result

## Not working / intentionally deferred

- No Milestone 8 blockers.
- No serial communication, WebSockets, firmware, controller command, ACK, stop command, pump/valve control, or actuation was added.
- No physical mix verification or correction loop exists; measured mix remains pending hardware.
- No irrigation execution/completion, source-bank deduction, persistent decision orchestration, or SQLite expansion was added.
- No crop, weather, irrigation, TDS, blending, allocation, or Vivayu model logic was duplicated in TypeScript.
- No model retraining, threshold changes, or legacy Vivayu files were touched.
- The dashboard is a polling-based planning interface; serial ingestion begins only in Milestone 9.

## Tests and verification

- Frontend lint: passed (`npm run lint`)
- Frontend production build: passed (`npm run build`, Next.js Webpack builder)
- TypeScript production checking: passed as part of the Next.js build
- Complete backend regression suite: `222 passed` (`.venv/bin/pytest -q`)
- Patch whitespace/error validation: passed (`git diff --check`)
- Scope review: only frontend files and `docs/STATUS.md` changed; backend, firmware, and frozen legacy files remain untouched

## Last end-to-end run

- Mode: simulation, one-second frontend polling, canonical read-only M4/M5/M6/M7 previews
- Result: `SENSORS -> crop/stage -> weather -> irrigation amount -> water strategy -> scarcity allocation -> research-only Vivayu` is understandable from the judge dashboard with backend explanations
- Failure: none

## Next exact task

1. Freeze Milestone 8 until Milestone 9 is explicitly approved.
2. Milestone 9 should implement only the line-delimited serial adapter and reconnect/stale-node behavior behind the existing canonical state boundary.
3. Do not add controller commands, ACK/stop protocol, firmware actuation, TDS correction, irrigation execution, or decision orchestration unless separately authorized by their milestone.
