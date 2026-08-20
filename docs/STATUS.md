# Implementation Status

## Current milestone

Milestone 2 - Typed application state and independent Zone A/B simulation (complete)

## Working

- [x] Canonical Pydantic schemas for zone configuration, telemetry, derived zone state, water, weather, power, Vivayu health, and complete system state
- [x] Exactly two canonical zones with matching map, config, and telemetry identities
- [x] Lock-protected state store that returns deep copies and isolates Zone A from Zone B
- [x] Per-zone crop, sowing date, and manual stage configuration persists in memory
- [x] Simulation mode is explicit in health and complete state responses
- [x] Hardware mode starts with unavailable real telemetry, water, weather, and power measurements as `null`/offline
- [x] Six data-driven scenarios load from `backend/app/data/demo_scenarios.json`
- [x] Scenario loading always rebuilds from baseline, preventing cross-scenario state leakage
- [x] `GET /api/v1/state` returns the canonical complete state
- [x] Zone read/config/stage-override endpoints operate independently
- [x] Simulation list, activate/load, and reset endpoints work
- [x] Existing frontend continues to display the prominent `SIMULATION` badge

## Not working / blocked

- No Milestone 2 blockers.
- Growth-stage estimation and crop-profile validation are intentionally deferred to Milestone 3.
- Weather values are static simulation fixtures only; no weather API/cache exists yet.
- Water values are state fixtures only; no irrigation need, priority, TDS mixing, or allocation logic exists.
- Legacy Vivayu is represented only by typed unavailable state; no model is loaded.
- Serial, firmware, controller commands, TDS correction, actuation, and dashboard expansion remain untouched.

## Hardware assumptions

- Two logical zones remain mandatory regardless of physical ESP32 topology.
- The physical topology (one shared field node vs. one node per zone) remains unresolved and does not block simulation.
- Hardware mode never inherits simulated readings.
- No pump or valve actuation path exists.

## Tests

- Backend: 35 passed
- Coverage includes schema correctness, null handling, Zone A/B isolation, all six scenarios, simulation labelling, reset behavior, invalid zone/scenario rejection, configuration persistence, API responses, and hardware-safe initialization.
- Frontend: not changed in Milestone 2; Milestone 1 lint/build results remain valid.

## Last end-to-end run

- Mode: simulation
- Result: state store and API scenario lifecycle passed automated tests
- Failure: none

## Next exact task

1. Stop here until Milestone 3 is explicitly approved.
2. In Milestone 3, add sourced crop profiles and sowing-date growth-stage estimation with manual override preservation.
3. Then add the weather adapter/cache with live, cached, and offline states and tests.
