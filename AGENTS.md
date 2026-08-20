# VIVAYU Aqua - Codex Instructions

Read `docs/CODEX_MASTER_REFERENCE.md` completely before implementing anything.
Treat it as the source of truth for the InnoHack build.

## Operating rules

- Work milestone-by-milestone; do not implement the whole project in one pass.
- After every milestone, run tests/build checks and update `docs/STATUS.md`.
- Preserve `legacy/vivayu` as the original research snapshot; do not casually refactor it.
- Do not change the semantics of the existing Vivayu model.
- The legacy Vivayu result is research-only and must not directly trigger irrigation.
- Zone A and Zone B must have isolated telemetry, crop config, rolling ML windows, decisions, and history.
- Never fabricate missing sensors. Use `null`/unavailable states.
- Simulation data must be clearly labelled and must never silently actuate hardware.
- Pumps/valves default OFF. Stale telemetry, unsafe/missing TDS, controller disconnect, invalid crop config, or invalid commands must block automatic actuation.
- Every irrigation decision must include machine-readable `reasons` and `warnings`.
- Use line-delimited, versioned JSON for controller/serial communication.
- Keep units in field names (`_ml`, `_l`, `_ppm`, `_pct`, `_c`, `_w`).
- Use pure/testable functions for irrigation need, priority, and water-quality calculations.
- Keep hardware I/O behind adapters so simulation and hardware modes share the same domain schemas.
- Do not add P2 features until all P0 acceptance criteria pass.

## Required implementation order

1. Repository scaffold + backend/frontend boot.
2. Simulation mode + independent Zone A/B state.
3. Crop/sowing-date/stage + weather cache.
4. Irrigation-need engine.
5. TDS/water-quality strategy engine.
6. Multi-zone freshwater allocation.
7. Legacy Vivayu wrapper, one predictor per compatible zone.
8. Judge-facing dashboard.
9. Serial adapter.
10. Command/ACK protocol and fail-safe stop.
11. TDS feedback/correction state machine.
12. Irrigation + post-soil verification/adaptive calibration.
13. Repeated demo hardening only; no architectural expansion.

Do not proceed to the next milestone if the current milestone's acceptance
criteria are not met.
