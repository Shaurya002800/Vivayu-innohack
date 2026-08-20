# Implementation Status

## Current milestone

Milestone 6 - Multi-zone freshwater allocation under scarcity (complete)

## Working

- [x] The allocator consumes canonical frozen `IrrigationNeedResult` and `WaterQualityResult` objects; it does not recalculate crop water demand, urgency, TDS, or blend formulas
- [x] Allocation operates across exactly Zone A and Zone B with a canonical typed input/result contract
- [x] Phase 1 gives critically dry actionable zones a configurable prototype minimum delivery where safe source capacity permits
- [x] Phase 2 allocates remaining source capacity by the existing Milestone 4 urgency score, then Zone ID for deterministic ties
- [x] No parallel or hidden priority score was introduced; stage sensitivity is preserved as visible M4 context
- [x] `MARGINAL_ONLY`, `FRESH_ONLY`, and `CONTROLLED_BLEND` are handled from their frozen Milestone 5 source fractions
- [x] Partial controlled-blend delivery scales fresh and marginal volumes together; reducing freshwater can never retain the full marginal volume and create a saltier ratio
- [x] Example invariant is enforced and tested: full `300 mL fresh + 200 mL marginal = 500 mL` scaled to `150 mL fresh` becomes `150 + 100 = 250 mL`
- [x] Allocation may be equally safe or slightly fresher within numeric tolerance, but it may never exceed the Milestone 5 marginal fraction
- [x] Both freshwater and marginal-water banks are enforced; neither source can be over-allocated
- [x] Unknown source availability remains `null` and blocks allocation rather than being fabricated as zero
- [x] Unsafe, configuration-required, source-unknown, sensor-blocked, and other non-actionable upstream results never enter the allocation pool
- [x] Canonical zone outcomes are `FULLY_SERVED`, `PARTIALLY_SERVED`, `DEFERRED_NO_FRESHWATER`, `DEFERRED_NO_SAFE_WATER`, `NO_IRRIGATION`, and `BLOCKED`
- [x] Every zone exposes its request, full safe source volumes/fractions, allocated volumes/fractions, deliverable volume, service fraction, critical-minimum status, frozen predicted TDS, and deterministic reasons/warnings
- [x] Global output exposes both bank capacities/requirements/allocations/remainders, scarcity state, requested/deliverable/unserved totals, both phase orders, policy, and deterministic reasons/warnings
- [x] Canonical validators enforce non-negative volumes, per-zone and global conservation, delivery not exceeding request, both source-bank ceilings, exact A/B membership, and the non-saltier ratio invariant
- [x] The allocation preview is pure planning: repeated calls are idempotent and never deduct canonical source availability, persist decisions, or actuate hardware
- [x] The `freshwater_shortage` simulation scenario feeds its real state into M4, M5, and the allocator; it contains no hard-coded allocation output
- [x] Changing only the freshwater bank changes delivery while crop, soil, weather, source TDS, and irrigation requests remain unchanged
- [x] Allocator inputs contain no Vivayu health/VOC signal, and tests prove output is independent of that research-only state
- [x] Zone configuration, scenario reset, source state, and all Milestone 2–5 behavior remain isolated and operational

## API surface completed in Milestone 6

- `GET /api/v1/water/allocation-preview`
- The endpoint evaluates current Zone A/B state through the existing M4 and M5 engines, then calls the pure allocator
- Existing Milestone 2–5 endpoints and state contracts remain compatible
- No execute, allocation commit, decision persistence, correction, or actuation endpoint was added

## Configurable prototype allocation policy

These are visible deterministic demo-policy defaults, not universal agronomic or crop-survival claims. Every allocation result returns the active values.

- Critical minimum delivery fraction: `0.25`
- Allocation volume precision: `6 decimal places`
- Volume accounting tolerance: `0.000001 ml`
- Safe-ratio comparison tolerance: `0.000001`

Environment variables:

- `ALLOCATION_CRITICAL_MINIMUM_FRACTION`
- `ALLOCATION_ROUNDING_DECIMALS`
- `ALLOCATION_VOLUME_TOLERANCE_ML`
- `ALLOCATION_RATIO_TOLERANCE`

## Allocation policy and safety assumptions

- Phase 1 is critical protection, not a guarantee of crop survival. Its fraction must be calibrated for a real deployment.
- Phase 2 is strict deterministic priority order, using M4 urgency descending and Zone A before Zone B only when scores tie.
- Source capacity is not reserved or deducted by a preview. A later committed irrigation event must own real bank mutation.
- When source capacity only supports a partial controlled blend, total delivery is reduced along the frozen M5 ray: `fresh = total × fresh_fraction`, `marginal = total × marginal_fraction`.
- Delivery volume is rounded down only at a scarcity boundary; the residual is left in the source bank deterministically.
- Source splits retain the safe ratio and volume conservation. The allocator does not calculate a new predicted TDS.
- The returned predicted TDS is explicitly the frozen M5 full-request prediction. Physical post-mix verification remains required in Milestone 11.
- `scarcity_active` specifically reports freshwater shortage. Marginal-water shortage is exposed separately through required/available metadata and reasons.
- TDS remains an incoming-water quality proxy and does not prove long-term root-zone salinity safety.

## Not working / intentionally deferred

- No Milestone 6 blockers.
- No source-bank deduction, reservation transaction, irrigation event commit, or persistent decision record exists yet.
- Legacy Vivayu loading/predictors remain deferred to Milestone 7.
- Dashboard expansion, serial communication, firmware, pumps/valves, controller commands, ACKs, and actuation remain untouched.
- Physical mixed-TDS measurement/correction remains deferred to Milestone 11.
- Full decision orchestration remains deferred; this milestone only composes M4/M5 for a read-only allocation preview.

## Files/features completed

- `backend/app/schemas.py`: allocation statuses, policy, input, per-zone output, global result, reason/warning vocabulary, and invariant validation
- `backend/app/config.py`, `.env.example`: configurable critical-minimum fraction, precision, volume tolerance, and ratio tolerance
- `backend/app/services/freshwater_allocator.py`: pure input classification, two-phase priority allocation, two-bank enforcement, ratio-preserving partial delivery, rounding, and explainability
- `backend/app/api/water.py`: idempotent current-state allocation preview integrating the frozen M4/M5 engines
- `backend/tests/test_freshwater_allocator.py`: pure allocator boundaries, exact ratio safety, strategies, priorities, source shortages, rounding, invariants, bank-only change, Vivayu independence, and property-style bank ceilings
- `backend/tests/test_freshwater_allocation_api.py`: full-service integration, idempotency/no deduction, scenario logic/reset, A/B isolation, blocked defaults, bank-only behavior, and no side effects
- `backend/app/state.py`, `backend/app/api/decisions.py`, and all actuation/legacy files: intentionally unchanged in Milestone 6

## Tests and verification

- Complete backend suite: `196 passed` (`.venv/bin/python -m pytest -q`)
- Python compilation: passed (`.venv/bin/python -m compileall -q app tests`)
- Patch whitespace/error validation: passed (`git diff --check`)
- New coverage includes sufficient banks, combined freshwater shortage, critical vs non-critical, both critical, deterministic ties, marginal-only, fresh-only, two controlled blends, exact proportional down-scaling, zero fresh, zero marginal, both banks insufficient, no irrigation, blocked TDS/configuration, marginal-only freshwater independence, bank ceilings, delivery ceilings, conservation, rounding, A/B isolation, idempotency, no deduction, scenario/reset isolation, Vivayu independence, and freshness-bank-only intelligence.
- A parameterized property-style test exercises 84 valid strategy/bank combinations and proves total fresh and marginal allocation never exceeds the configured banks.
- Frontend was not changed in Milestone 6.

## Last end-to-end run

- Mode: simulation API integration plus pure deterministic allocator fixtures
- Result: `SENSORS -> crop/stage -> weather -> M4 amount -> M5 safe source ratio -> M6 scarcity allocation` completes without state mutation or actuation
- Failure: none

## Next exact task

1. Freeze Milestone 6 until Milestone 7 is explicitly approved.
2. Milestone 7 should implement only the legacy Vivayu research wrapper with one isolated predictor per compatible zone and no irrigation/allocation influence.
3. Do not add dashboard expansion, serial/controller I/O, firmware, actuation, physical TDS correction, or full decision orchestration unless separately authorized.
