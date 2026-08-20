# Implementation Status

## Current milestone

Milestone 7 - Legacy Vivayu research wrapper (complete)

## Working

- [x] The frozen legacy snapshot remains unchanged and is loaded only through a controlled backend wrapper
- [x] The pinned `gas_threshold` research candidate loads from a configurable model path
- [x] Zone A and Zone B own completely independent five-reading rolling predictors
- [x] Compatible zones report deterministic `COLLECTING` progress from `1/5` through `4/5`, then `READY` on reading 5
- [x] Additional readings preserve the frozen five-reading rolling-window behavior
- [x] The exact legacy six-field signature is enforced: timestamp, temperature, humidity, pressure, BME680 gas resistance, and original SGP40-style `sraw`
- [x] Missing values remain `null`; the wrapper never fabricates or silently substitutes a sensor channel
- [x] BME280 is explicitly rejected because it has no compatible BME680 gas-resistance channel
- [x] AGS10 values are explicitly rejected as substitutes for original SGP40-style `sraw` semantics
- [x] Missing, non-finite, and out-of-range readings produce explicit unavailable/error states without crashing the application
- [x] Legacy model import, load, and inference failures are contained behind the wrapper and leave irrigation intelligence operational
- [x] Public output exposes the historical model value as `research_score`, not as a validated disease probability
- [x] All outputs are labelled `research_only: true` and include the frozen confidence disclaimer where a result is ready
- [x] Legacy pattern and risk labels are preserved rather than reinterpreted or medically/agronomically upgraded
- [x] Simulation scenarios feed their telemetry and sensor provenance through the same wrapper; health output is not hard-coded
- [x] The `legacy_ml_unavailable` scenario makes Zone B explicitly unavailable while Zone A remains independent
- [x] Updating or resetting one zone cannot alter the other zone's predictor window or health state
- [x] M4 irrigation need, M5 water-source selection, and M6 freshwater allocation remain independent of Vivayu health
- [x] A zone with unavailable Vivayu health can still receive a valid irrigation, water-quality, and allocation result from soil, crop/stage, weather, TDS, and source availability

## API surface completed in Milestone 7

- `GET /api/v1/zones/{zone_id}/vivayu-health`
- `GET /api/v1/state` includes the canonical Vivayu health state for both zones
- Existing Milestone 2–6 endpoints and contracts remain compatible through additive schema fields
- No prediction-trigger, diagnosis, execute, reset, command, or actuation endpoint was added

## Canonical Vivayu health contract

- Status: `UNAVAILABLE`, `COLLECTING`, `READY`, or `ERROR`
- Progress: `readings_received`, `readings_required`, and `readings_in_window`
- Ready result: legacy `pattern`, `risk_level`, `research_score`, confidence metadata, and model name
- Provenance: `source_mode`, `last_updated_at`, and explicit zone sensor configuration
- Explainability: stable `reason_code`, human-readable `reason`, and research/sensor warnings
- Safety label: `research_only` is always `true`
- Confidence disclaimer: `Decision separation only; not calibrated field confidence.`

## Sensor compatibility boundary

- Accepted environment provenance: compatible `BME680` gas-resistance readings
- Accepted VOC provenance: compatible original `SGP40`-style raw `sraw` readings
- `BME280`, `AGS10`, unknown provenance, absent channels, and incompatible values are not coerced into the legacy signature
- Compatibility is configured independently for each zone in `ZoneConfig.vivayu_sensors`

## Configuration

- `VIVAYU_MODEL_PATH` selects the pinned legacy joblib artifact
- A relative path is resolved from the repository root; the default remains `legacy/vivayu/models/vivayu_research_candidate.joblib`

## Legacy semantics preserved

- The snapshot's `elevated_voc_pattern` boundary begins at a score of `0.5`
- The snapshot's `watch` risk range ends below `0.5`; therefore an elevated pattern is paired with `elevated` or `high`, not `watch`
- This pairing is intentionally not changed in the wrapper because Milestone 7 freezes legacy behavior
- The output is a VOC-pattern research signal, not disease diagnosis and not an irrigation input

## Not working / intentionally deferred

- No Milestone 7 blockers.
- No dashboard expansion, serial ingestion, controller communication, firmware, pumps, valves, ACKs, or actuation was added.
- No Vivayu result influences crop/stage, weather, irrigation need, TDS strategy, blending, or freshwater allocation.
- No model retraining, calibration, threshold editing, artifact replacement, or legacy-file cleanup was performed.
- Physical mixed-TDS verification/correction remains deferred to Milestone 11.
- Full decision orchestration remains deferred.

## Files/features completed

- `backend/app/schemas.py`: canonical health statuses/results, reason vocabulary, progress, provenance, warnings, validation, and per-zone sensor compatibility configuration
- `backend/app/services/vivayu_health_service.py`: controlled legacy import/model load, independent predictors, sensor gate, rolling inference, public result mapping, resets, and safe failure handling
- `backend/app/state.py`: per-zone predictor lifecycle, scenario/reset integration, telemetry ingestion, and canonical health-state synchronization
- `backend/app/api/zones.py`: read-only per-zone Vivayu health endpoint
- `backend/app/config.py`, `.env.example`: configurable legacy model path
- `backend/app/data/demo_scenarios.json`: explicit compatible baseline provenance and an incompatible Zone B scenario derived through the wrapper
- `backend/tests/test_vivayu_health_service.py`: unit coverage for progress, readiness, rolling behavior, isolation, resets, sensor compatibility, invalid inputs, model failure, and research labelling
- `backend/tests/test_vivayu_integration.py`: state/API/scenario integration, isolation, safe failure, read-only API, and M4/M5/M6 noninterference
- `backend/tests/test_simulation.py`: updated canonical unavailable-state assertions
- `legacy/vivayu/**`: intentionally unchanged

## Tests and verification

- Complete backend suite: `222 passed` (`.venv/bin/pytest -q`)
- New tests prove `1/5 -> 2/5 -> 3/5 -> 4/5 -> READY`, frozen five-reading rolling behavior, Zone A/B isolation, per-zone reset isolation, BME280/AGS10 rejection, missing/null/non-finite/out-of-range handling, model-load and inference containment, canonical API/state integration, scenario behavior, and research-only labelling.
- Regression tests prove Vivayu-only changes do not change M4, M5, or M6 results, and an incompatible zone's irrigation pipeline remains operational.
- Python compilation: passed (`.venv/bin/python -m compileall -q app tests`)
- Patch whitespace/error validation: passed (`git diff --check`)
- Frontend and firmware were not changed in Milestone 7.

## Last end-to-end run

- Mode: simulation API integration plus the pinned legacy research model
- Result: Zone A can progress independently from collecting to a research-only VOC result while Zone B remains explicitly unavailable; both zones retain the frozen irrigation intelligence chain
- Failure: none

## Next exact task

1. Freeze Milestone 7 until Milestone 8 is explicitly approved.
2. Milestone 8 should implement only the approved dashboard/UI scope using existing canonical read-only state and decision-preview APIs.
3. Do not add serial/controller I/O, firmware, actuation, model retraining, physical TDS correction, or full decision orchestration unless separately authorized.
