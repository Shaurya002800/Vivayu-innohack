# Implementation Status

## Current milestone

Milestone 5 - Pure water-quality/TDS strategy engine (complete)

## Working

- [x] Milestones 2–4 canonical `ZoneConfig`, `CropContext`, `WaterState`, and `SystemState` are extended rather than duplicated
- [x] Each zone has an isolated, nullable `max_irrigation_tds_ppm` prototype constraint; no crop limit is invented when unsupported
- [x] Canonical fresh and marginal source state exposes source identity, display name, nullable TDS/temperature/availability, measurement timestamp/age, and quality status
- [x] Simulation readings are explicitly labelled `SIMULATED`; hardware readings become `MEASURED`, `STALE`, or `UNKNOWN` from timestamp/data validity
- [x] Pure `calculate_water_quality_strategy` consumes the Milestone 4 requested-water volume and returns typed, deterministic results
- [x] Supported strategies are `MARGINAL_ONLY`, `CONTROLLED_BLEND`, `FRESH_ONLY`, `NOT_FEASIBLE`, `CONFIG_REQUIRED`, `SOURCE_QUALITY_UNKNOWN`, and `NO_IRRIGATION_REQUEST`
- [x] Safety target is calculated as configured crop maximum minus the configurable positive safety margin; the engine never intentionally targets the hard crop limit
- [x] Controlled blends use the volume-weighted TDS equation and conservatively floor marginal volume to the configured precision
- [x] Source volumes conserve the requested amount within the explicit tolerance, and predicted TDS cannot validate above the safety target plus its explicit tolerance
- [x] Missing/stale source TDS, missing crop constraints, invalid safety targets, equal qualities, reversed source qualities, invalid numbers, and zero/negative requests are handled explicitly and conservatively
- [x] Reversed source qualities are not silently normalized; they return `NOT_FEASIBLE` with a source-label anomaly reason/warning
- [x] Results separate `predicted_tds_ppm` from future `measured_tds_ppm`; the latter remains `null` throughout Milestone 5
- [x] Every result contains structured reason codes/messages, warning codes/messages, the active policy, inputs, source fractions/volumes when safe, and current single-zone source sufficiency
- [x] Availability reporting evaluates only the selected zone's computed volumes; it does not reserve water or compare Zone A with Zone B
- [x] Water-quality preview is independent of Vivayu health/VOC state and never mutates state, persists a decision, or actuates hardware
- [x] Changing only source-water TDS can change the chosen water-quality strategy while soil, crop, weather, and irrigation need remain unchanged
- [x] Water updates, scenario loads, and resets preserve source identity and do not leak mutated source state
- [x] Zone A and Zone B constraint updates remain fully isolated
- [x] All six simulation scenarios and all Milestone 2–4 contracts remain operational

## API surface completed in Milestone 5

- `GET /api/v1/water`
- `PUT /api/v1/water/sources/{source_id}`
- `GET /api/v1/water/zones/{zone_id}/constraint`
- `PUT /api/v1/water/zones/{zone_id}/constraint`
- `GET /api/v1/water/zones/{zone_id}/strategy`
- Existing `GET /api/v1/state` and zone responses include the additive canonical source metadata and per-zone water-quality constraint
- No allocation, decision execution, correction, or actuation endpoint was added

## Configurable prototype policy defaults

These are visible operating-policy settings, not agronomic claims. Every strategy result returns the active values in its `policy` field.

- TDS safety margin: `50 ppm`
- Source measurement stale threshold: `240 minutes`
- Source-volume precision: `6 decimal places`
- Volume-conservation tolerance: `0.000001 ml`
- Predicted-TDS comparison tolerance: `0.000001 ppm`

## Assumptions and warnings

- `max_irrigation_tds_ppm` must be explicitly configured per zone or come from supported source-backed crop metadata; current demo crop profiles intentionally leave unsupported limits `null`.
- TDS is treated only as a low-cost incoming-water quality proxy and does not prove long-term root-zone salinity safety.
- Predicted blend TDS is mathematical, not a physical measurement. Safe previews always warn that Milestone 11 must verify the actual post-mix TDS.
- The source labelled `fresh` is expected to have no higher TDS than `marginal`; conflicting measured values are treated as a data-quality anomaly rather than silently swapping identities.
- `source_volume_sufficient` describes only whether this one preview can currently be supplied. It is not a reservation, allocation, or multi-zone scarcity decision.
- Simulation TDS remains usable regardless of wall-clock age because it is scenario input explicitly labelled `SIMULATED`; hardware readings obey the configured stale threshold.
- A positive safety margin is required. A margin greater than or equal to the configured crop maximum produces `NOT_FEASIBLE`.

## Not working / intentionally deferred

- No Milestone 5 blockers.
- Multi-zone freshwater competition, reservation, priority, or allocation is intentionally deferred to Milestone 6.
- Physical mix measurement, correction loops, retry limits, and post-mix verification are intentionally deferred to Milestone 11.
- Vivayu ML loading, complete decision orchestration, firmware, serial/controller I/O, actuation, persistence, and dashboard expansion remain untouched.
- Water-quality previews are never automatically executed or persisted.

## Files/features completed

- `backend/app/schemas.py`: canonical source identity/status/update models, per-zone TDS constraint, policy, strategy/result, reasons, warnings, and consistency validation
- `backend/app/config.py`, `.env.example`: environment-backed TDS safety, freshness, volume, and prediction policy
- `backend/app/data/demo_scenarios.json`: explicit canonical source identity and simulated-quality labels without adding fabricated readings
- `backend/app/services/crop_service.py`: zone-configured maximum incoming-water TDS integrated into existing `CropContext`
- `backend/app/services/water_quality.py`: pure safety-target, weighted prediction, strategy, conservative rounding, explainability, and single-zone sufficiency logic
- `backend/app/state.py`: lock-protected source and per-zone constraint updates, hardware measurement aging, simulation labelling, and reset isolation
- `backend/app/api/water.py`, `backend/app/main.py`: source read/write, constraint read/write, and side-effect-free Milestone 4-integrated strategy routes
- `backend/tests/test_water_quality.py`: pure-engine cases, invalid/stale input, numerical boundaries, availability, Milestone 4 integration, and Vivayu non-interference
- `backend/tests/test_water_api.py`: API contracts, canonical state integration, A/B isolation, reset behavior, validation, read-only preview, and TDS-only strategy changes
- `backend/app/api/decisions.py`: intentionally unchanged

## Tests and verification

- Complete backend suite: `145 passed` (`.venv/bin/python -m pytest -q`)
- Python compilation: passed (`.venv/bin/python -m compileall -q app tests`)
- Patch whitespace/error validation: passed (`git diff --check`)
- Coverage includes all Milestone 2–4 regressions plus marginal-below/equal-target, controlled blend, fresh-only, even-fresh-unsafe, missing crop/source data, stale readings, zero/negative requests, invalid/non-finite TDS, equal/reversed qualities, impossible margins, weighted-equation correctness, floating-point/rounding safety, exact volume conservation, source sufficiency, hardware aging, A/B isolation, simulation reset isolation, Milestone 4 request integration, Vivayu independence, and no actuation/state-mutation side effects.
- Frontend was not changed in Milestone 5.

## Last end-to-end run

- Mode: simulation for API integration; hardware mode exercised for safe null source state and stale measurement handling
- Result: explicit irrigation parameters plus a zone TDS constraint produce deterministic, explained source strategies without allocation or actuation
- Failure: none

## Next exact task

1. Freeze Milestone 5 until Milestone 6 is explicitly approved.
2. Milestone 6 should implement only multi-zone freshwater allocation and scarcity-aware priority using the frozen Milestone 4 irrigation request and Milestone 5 water-quality demand.
3. Do not add physical TDS correction, Vivayu ML, firmware, actuation, complete decision orchestration, or dashboard expansion unless separately authorized.
