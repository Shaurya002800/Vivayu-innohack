# Implementation Status

## Current milestone

Milestone 4 - Pure, explainable irrigation-need engine (complete)

## Working

- [x] Milestones 2–3 canonical `ZoneConfig`, `ZoneState`, `CropContext`, `WeatherState`, and `SystemState` are extended rather than duplicated
- [x] Each zone has independent nullable `target_moisture_pct`, `critical_moisture_pct`, and `ml_per_moisture_point` prototype parameters inside its canonical `ZoneConfig`
- [x] Parameter schema enforces `0 <= critical < target <= 100`, finite values, and positive `ml_per_moisture_point`
- [x] No agronomic soil-moisture target, critical threshold, or field-response calibration is supplied implicitly; missing values return `CONFIG_REQUIRED`
- [x] Per-zone thresholds flow into the existing derived `CropContext`; crop-profile values remain the fallback only when a sourced value exists
- [x] Pure `base_water_need_ml` implements exactly `max(0, target - current) * ml_per_moisture_point`
- [x] Pure `calculate_irrigation_need` returns typed `NOT_NEEDED`, `NEEDED`, `CRITICAL`, `DEFER_FOR_RAIN`, `CONFIG_REQUIRED`, or `SENSOR_UNAVAILABLE` results
- [x] Every preview exposes stable reason/warning codes, human-readable explanations, urgency label/score/components, input values, policy constants, and requested-water fields
- [x] Prototype water volume is never modified by crop stage, ET0, or hidden multipliers
- [x] Growth-stage sensitivity affects only the visible urgency component; missing stage sensitivity adds a warning rather than a guessed value
- [x] High ET0 affects only visible urgency metadata and never changes requested volume
- [x] Configured strong/meaningful rain may defer a non-critical deficit; soil moisture at or below critical is never blindly deferred for rain
- [x] Offline, stale, or incomplete rainfall assistance does not crash calculation; valid local soil/crop inputs are evaluated with a weather-unavailable warning
- [x] Null soil moisture, offline telemetry, unknown telemetry age, or telemetry older than the configured limit returns `SENSOR_UNAVAILABLE` with no calculated water request
- [x] Invalid/missing crop context, disabled zone, missing moisture thresholds, or missing calibration returns `CONFIG_REQUIRED`
- [x] Future sowing dates remain rejected before state mutation or irrigation preview
- [x] Zone A and Zone B parameter/configuration updates remain completely isolated
- [x] Vivayu health/VOC fields are not read by the irrigation engine and cannot change its output when true irrigation inputs are identical
- [x] Irrigation preview is calculated explicitly on request and does not mutate `SystemState`, store stale results, create a decision record, or actuate anything
- [x] All six Milestone 2 simulation scenarios and all crop/weather behavior from Milestone 3 remain operational

## API surface completed in Milestone 4

- `GET /api/v1/zones/{zone_id}/irrigation-parameters`
- `PUT /api/v1/zones/{zone_id}/irrigation-parameters`
- `GET /api/v1/zones/{zone_id}/irrigation-need`
- Existing full-zone and `/api/v1/state` responses include the additive per-zone parameter object
- No decision execution or actuation endpoint was added

## Explainable prototype policy defaults

The following are environment-configurable prototype operating-policy defaults, not claimed agronomic truths. Every preview returns the active values in its `policy` field.

- Telemetry stale after: `10 s`
- Strong-rain probability threshold: `70%`
- Meaningful next-six-hour precipitation threshold: `2 mm`
- High next-six-hour ET0 context threshold: `1 mm`
- Soil-deficit urgency weight: `0.60`
- Critical-moisture urgency boost: `0.25`
- High/moderate stage-sensitivity boosts: `0.10` / `0.05`
- High-ET0 urgency boost: `0.05`
- Maximum possible configured urgency component sum is schema-limited to `1.0`

## Scientific and implementation assumptions

- Soil moisture is a calibrated prototype sensor index, not universal volumetric water content.
- Requested millilitres represent per-zone pot/field-response calibration only and are not a universal farm-scale irrigation-volume equation.
- Target/critical values must be explicitly measured/configured for the prototype or supplied by a supported sourced profile; current demo crop profiles intentionally provide no such defaults.
- Rain and ET0 policy values are explainable demo control settings and must be calibrated before field deployment.
- Rain deferral requires both probability and precipitation thresholds; probability alone does not defer.
- Weather unavailability never substitutes zero precipitation or ET0.
- `DEFER_FOR_RAIN` keeps the calculated base deficit/volume visible but sets the immediate requested volume to `0`.
- `CONFIG_REQUIRED` and `SENSOR_UNAVAILABLE` keep calculated deficit, water volume, and urgency outputs `null`.

## Not working / blocked

- No Milestone 4 blockers.
- TDS/water-quality strategy, source selection, blending, freshwater allocation, and decision orchestration remain intentionally deferred.
- Vivayu ML loading, firmware, serial/controller commands, actuation, persistence, and dashboard expansion remain untouched.
- No preview is automatically executed or persisted.

## Files/features completed

- `backend/app/schemas.py`: prototype parameters, irrigation policy, urgency components, result/status/reason schemas, and finite/ordered validation
- `backend/app/config.py`, `.env.example`: visible environment-backed rain, ET0, freshness, and urgency policy constants
- `backend/app/services/crop_service.py`: zone-configured moisture thresholds integrated into the existing `CropContext`
- `backend/app/services/irrigation_need.py`: pure formula, configuration/sensor fail-safe handling, weather rules, urgency components, and explanations
- `backend/app/state.py`: isolated per-zone parameter read/update using the existing lock-protected state
- `backend/app/api/irrigation.py`, `backend/app/main.py`: parameter read/write and side-effect-free preview routes
- `backend/tests/test_irrigation_need.py`: pure-engine boundaries, fail-safe behavior, explainability, isolation, and Vivayu non-interference
- `backend/tests/test_irrigation_api.py`: parameter and preview API behavior, scenario behavior, isolation, validation, and no-state-mutation checks
- `backend/app/api/decisions.py`: intentionally unchanged

## Tests and verification

- Complete backend suite: `112 passed` (`.venv/bin/python -m pytest -q`)
- Python compilation: passed (`.venv/bin/python -m compileall -q app tests`)
- Patch whitespace/error validation: passed (`git diff --check`)
- Coverage includes all Milestone 2–3 regressions plus exact target/critical boundaries, above/below target behavior, rain deferral, critical rain override, offline weather fallback, ET0 urgency, invalid/future crop handling, missing parameters, invalid calibration/thresholds/policy, stale/null telemetry, manual stage sensitivity, Zone A/B isolation, deterministic explanations, non-negative water requests, API previews, and Vivayu health non-interference.
- Frontend was not changed in Milestone 4.

## Last end-to-end run

- Mode: simulation for API integration; pure engine also exercised against hardware-safe canonical state fixtures
- Result: explicit parameter configuration produces deterministic per-zone previews without state mutation or actuation
- Failure: none

## Next exact task

1. Freeze Milestone 4 until Milestone 5 is explicitly approved.
2. Milestone 5 should implement only the pure TDS/water-quality strategy engine: `FRESH_ONLY`, `MARGINAL_ONLY`, `CONTROLLED_BLEND`, source availability, weighted predicted TDS, and configurable safety margin.
3. Do not add freshwater allocation, Vivayu ML, firmware, actuation, or dashboard expansion as part of Milestone 5 unless separately authorized.
