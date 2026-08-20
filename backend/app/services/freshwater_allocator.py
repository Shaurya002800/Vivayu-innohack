"""Pure two-zone scarcity allocation over frozen Milestone 4/5 results."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor, isfinite
from typing import Mapping

from app.config import Settings, settings
from app.schemas import (
    AllocationReasonCode,
    AllocationWarningCode,
    FreshwaterAllocationPolicy,
    FreshwaterAllocationResult,
    ZoneAllocationInput,
    ZoneId,
    ZoneWaterAllocation,
)


PREVIEW_WARNING = (
    "this is a planning preview; source banks are not deducted until a later committed event"
)
CRITICAL_POLICY_WARNING = (
    "the critical minimum is a configurable prototype delivery policy, not a crop-survival guarantee"
)
PHYSICAL_VERIFICATION_WARNING = (
    "the preserved source ratio remains a prediction and still requires future physical post-mix TDS verification"
)


@dataclass(slots=True)
class _Demand:
    input: ZoneAllocationInput
    eligible: bool
    requested_ml: float | None
    full_fresh_ml: float | None
    full_marginal_ml: float | None
    fresh_fraction: float | None
    marginal_fraction: float | None
    blocked_reason_code: AllocationReasonCode | None = None
    blocked_reason: str | None = None
    allocated_fresh_ml: float = 0.0
    allocated_marginal_ml: float = 0.0
    deliverable_ml: float = 0.0


def allocation_policy_from_settings(
    app_settings: Settings = settings,
) -> FreshwaterAllocationPolicy:
    return FreshwaterAllocationPolicy(
        critical_minimum_delivery_fraction=(
            app_settings.allocation_critical_minimum_fraction
        ),
        volume_rounding_decimals=app_settings.allocation_rounding_decimals,
        volume_tolerance_ml=app_settings.allocation_volume_tolerance_ml,
        ratio_tolerance=app_settings.allocation_ratio_tolerance,
    )


def allocate_freshwater(
    *,
    freshwater_available_ml: float | None,
    marginal_available_ml: float | None,
    zone_inputs: Mapping[ZoneId, ZoneAllocationInput],
    policy: FreshwaterAllocationPolicy,
) -> FreshwaterAllocationResult:
    """Allocate two source banks without recalculating demand or water quality."""

    if set(zone_inputs) != {"A", "B"}:
        raise ValueError("allocator requires exactly Zone A and Zone B")
    for zone_id, zone_input in zone_inputs.items():
        if zone_input.zone_id != zone_id:
            raise ValueError("allocation map key does not match zone input")
    _validate_available("freshwater_available_ml", freshwater_available_ml)
    _validate_available("marginal_available_ml", marginal_available_ml)

    demands = {
        zone_id: _classify_input(zone_inputs[zone_id], policy)
        for zone_id in ("A", "B")
    }
    eligible = [demand for demand in demands.values() if demand.eligible]
    remaining_order = tuple(
        demand.input.zone_id for demand in sorted(eligible, key=_priority_key)
    )
    critical_order = tuple(
        demand.input.zone_id
        for demand in sorted(
            (
                demand
                for demand in eligible
                if demand.input.irrigation_need.status == "CRITICAL"
            ),
            key=_priority_key,
        )
    )

    fresh_required = sum(demand.full_fresh_ml or 0.0 for demand in eligible)
    marginal_required = sum(demand.full_marginal_ml or 0.0 for demand in eligible)
    total_requested = sum(
        demand.requested_ml or 0.0 for demand in demands.values()
    )

    availability_known = (
        freshwater_available_ml is not None and marginal_available_ml is not None
    )
    remaining_fresh = freshwater_available_ml or 0.0
    remaining_marginal = marginal_available_ml or 0.0

    if availability_known:
        for zone_id in critical_order:
            demand = demands[zone_id]
            assert demand.requested_ml is not None
            target = (
                demand.requested_ml * policy.critical_minimum_delivery_fraction
            )
            remaining_fresh, remaining_marginal = _grant(
                demand,
                target,
                remaining_fresh,
                remaining_marginal,
                policy,
            )

        for zone_id in remaining_order:
            demand = demands[zone_id]
            assert demand.requested_ml is not None
            unmet = max(0.0, demand.requested_ml - demand.deliverable_ml)
            remaining_fresh, remaining_marginal = _grant(
                demand,
                unmet,
                remaining_fresh,
                remaining_marginal,
                policy,
            )

    tied_zones = _tied_priority_zones(eligible, policy.volume_tolerance_ml)
    zones = {
        zone_id: _zone_result(
            demands[zone_id],
            policy=policy,
            availability_known=availability_known,
            fresh_bank_exhausted=(
                availability_known
                and remaining_fresh <= policy.volume_tolerance_ml
            ),
            tied_priority=zone_id in tied_zones,
        )
        for zone_id in ("A", "B")
    }

    fresh_allocated = sum(zone.allocated_fresh_ml for zone in zones.values())
    marginal_allocated = sum(zone.allocated_marginal_ml for zone in zones.values())
    total_deliverable = sum(zone.deliverable_water_ml for zone in zones.values())
    fresh_remaining = (
        _nonnegative_residual(freshwater_available_ml, fresh_allocated, policy)
        if freshwater_available_ml is not None
        else None
    )
    marginal_remaining = (
        _nonnegative_residual(marginal_available_ml, marginal_allocated, policy)
        if marginal_available_ml is not None
        else None
    )
    scarcity_active = (
        fresh_required > freshwater_available_ml + policy.volume_tolerance_ml
        if freshwater_available_ml is not None
        else None
    )

    reason_codes: list[AllocationReasonCode] = []
    reasons: list[str] = []
    warning_codes: list[AllocationWarningCode] = ["NO_WATER_DEDUCTED_PREVIEW"]
    warnings = [PREVIEW_WARNING]
    if not availability_known:
        reason_codes.append("SOURCE_AVAILABILITY_UNKNOWN")
        reasons.append("one or both source-bank volumes are unavailable")
        warning_codes.append("SOURCE_AVAILABILITY_UNKNOWN")
        warnings.append("allocation is blocked because missing source volume is not treated as zero")
    else:
        assert freshwater_available_ml is not None
        assert marginal_available_ml is not None
        if scarcity_active:
            reason_codes.append("GLOBAL_FRESHWATER_SCARCITY")
            reasons.append("full-service freshwater demand exceeds the current freshwater bank")
        if marginal_required > marginal_available_ml + policy.volume_tolerance_ml:
            reason_codes.append("GLOBAL_MARGINAL_SCARCITY")
            reasons.append("full-service marginal-water demand exceeds the current marginal bank")
            warning_codes.append("MARGINAL_CAPACITY_LIMITED")
            warnings.append("marginal-water scarcity also limits otherwise safe deliveries")
        for zone_id in ("A", "B"):
            blocked_code = demands[zone_id].blocked_reason_code
            if blocked_code in {
                "IRRIGATION_INPUT_BLOCKED",
                "WATER_QUALITY_INPUT_BLOCKED",
            } and blocked_code not in reason_codes:
                reason_codes.append(blocked_code)
                reasons.append(
                    "at least one zone is excluded because its frozen upstream result is blocked"
                )
        if eligible and not any(
            code in {"GLOBAL_FRESHWATER_SCARCITY", "GLOBAL_MARGINAL_SCARCITY"}
            for code in reason_codes
        ):
            reason_codes.append("SOURCE_CAPACITY_SUFFICIENT")
            reasons.append("both source banks can satisfy all safe full-service strategies")
        elif not eligible and not reason_codes:
            reason_codes.append("NO_IRRIGATION_REQUEST")
            reasons.append("neither zone has an actionable safe irrigation request")
    if critical_order:
        warning_codes.append("PROTOTYPE_MINIMUM_NOT_SURVIVAL_GUARANTEE")
        warnings.append(CRITICAL_POLICY_WARNING)

    return FreshwaterAllocationResult(
        zones=zones,
        freshwater_available_ml=freshwater_available_ml,
        freshwater_required_for_full_service_ml=fresh_required,
        freshwater_allocated_ml=fresh_allocated,
        freshwater_remaining_ml=fresh_remaining,
        marginal_available_ml=marginal_available_ml,
        marginal_required_for_full_service_ml=marginal_required,
        marginal_allocated_ml=marginal_allocated,
        marginal_remaining_ml=marginal_remaining,
        scarcity_active=scarcity_active,
        total_requested_water_ml=total_requested,
        total_deliverable_water_ml=total_deliverable,
        unserved_water_ml=max(0.0, total_requested - total_deliverable),
        critical_phase_order=critical_order,
        remaining_phase_order=remaining_order,
        policy=policy,
        reason_codes=reason_codes,
        reasons=reasons,
        warning_codes=warning_codes,
        warnings=warnings,
    )


def _classify_input(
    zone_input: ZoneAllocationInput,
    policy: FreshwaterAllocationPolicy,
) -> _Demand:
    irrigation = zone_input.irrigation_need
    quality = zone_input.water_quality
    requested = irrigation.requested_water_ml
    if not irrigation.actionable:
        if irrigation.status in {"NOT_NEEDED", "DEFER_FOR_RAIN"}:
            return _Demand(
                input=zone_input,
                eligible=False,
                requested_ml=requested,
                full_fresh_ml=None,
                full_marginal_ml=None,
                fresh_fraction=None,
                marginal_fraction=None,
                blocked_reason_code="NO_IRRIGATION_REQUEST",
                blocked_reason="Milestone 4 produced no current irrigation request",
            )
        return _Demand(
            input=zone_input,
            eligible=False,
            requested_ml=requested,
            full_fresh_ml=None,
            full_marginal_ml=None,
            fresh_fraction=None,
            marginal_fraction=None,
            blocked_reason_code="IRRIGATION_INPUT_BLOCKED",
            blocked_reason="Milestone 4 irrigation input is blocked or unavailable",
        )

    safe_strategies = {"MARGINAL_ONLY", "CONTROLLED_BLEND", "FRESH_ONLY"}
    required = (
        requested,
        quality.requested_water_ml,
        quality.fresh_ml,
        quality.marginal_ml,
        quality.fresh_fraction,
        quality.marginal_fraction,
    )
    if quality.strategy not in safe_strategies or not quality.safe or any(
        value is None for value in required
    ):
        return _Demand(
            input=zone_input,
            eligible=False,
            requested_ml=requested,
            full_fresh_ml=None,
            full_marginal_ml=None,
            fresh_fraction=None,
            marginal_fraction=None,
            blocked_reason_code="WATER_QUALITY_INPUT_BLOCKED",
            blocked_reason="Milestone 5 did not produce a safe actionable source strategy",
        )

    assert requested is not None
    assert quality.requested_water_ml is not None
    assert quality.fresh_ml is not None
    assert quality.marginal_ml is not None
    assert quality.fresh_fraction is not None
    assert quality.marginal_fraction is not None
    tolerance = policy.volume_tolerance_ml
    if requested <= 0:
        raise ValueError("actionable irrigation input requires a positive request")
    if abs(quality.requested_water_ml - requested) > tolerance:
        raise ValueError("Milestone 4 and Milestone 5 requested volumes do not match")
    if abs(quality.fresh_ml + quality.marginal_ml - requested) > tolerance:
        raise ValueError("Milestone 5 source volumes do not conserve the request")
    if abs(quality.fresh_fraction + quality.marginal_fraction - 1.0) > (
        policy.ratio_tolerance
    ):
        raise ValueError("Milestone 5 source fractions do not sum to one")

    return _Demand(
        input=zone_input,
        eligible=True,
        requested_ml=requested,
        full_fresh_ml=quality.fresh_ml,
        full_marginal_ml=quality.marginal_ml,
        fresh_fraction=quality.fresh_fraction,
        marginal_fraction=quality.marginal_fraction,
    )


def _priority_key(demand: _Demand) -> tuple[float, ZoneId]:
    urgency = demand.input.irrigation_need.urgency_score
    if urgency is None:
        raise ValueError("actionable allocation input requires an M4 urgency score")
    return (-urgency, demand.input.zone_id)


def _tied_priority_zones(
    demands: list[_Demand],
    tolerance: float,
) -> set[ZoneId]:
    tied: set[ZoneId] = set()
    for index, left in enumerate(demands):
        left_score = left.input.irrigation_need.urgency_score
        assert left_score is not None
        for right in demands[index + 1 :]:
            right_score = right.input.irrigation_need.urgency_score
            assert right_score is not None
            if abs(left_score - right_score) <= tolerance:
                tied.update({left.input.zone_id, right.input.zone_id})
    return tied


def _grant(
    demand: _Demand,
    desired_delivery_ml: float,
    remaining_fresh_ml: float,
    remaining_marginal_ml: float,
    policy: FreshwaterAllocationPolicy,
) -> tuple[float, float]:
    if desired_delivery_ml <= policy.volume_tolerance_ml:
        return remaining_fresh_ml, remaining_marginal_ml
    assert demand.fresh_fraction is not None
    assert demand.marginal_fraction is not None
    capacity = desired_delivery_ml
    if demand.fresh_fraction > 0:
        capacity = min(capacity, remaining_fresh_ml / demand.fresh_fraction)
    if demand.marginal_fraction > 0:
        capacity = min(capacity, remaining_marginal_ml / demand.marginal_fraction)
    if capacity <= policy.volume_tolerance_ml:
        return remaining_fresh_ml, remaining_marginal_ml

    if capacity + policy.volume_tolerance_ml >= desired_delivery_ml:
        delivery = desired_delivery_ml
    else:
        scale = 10**policy.volume_rounding_decimals
        delivery = floor(capacity * scale) / scale
    if delivery <= policy.volume_tolerance_ml:
        return remaining_fresh_ml, remaining_marginal_ml

    fresh = delivery * demand.fresh_fraction
    marginal = delivery - fresh
    if fresh > remaining_fresh_ml + policy.volume_tolerance_ml:
        raise ValueError("rounded grant exceeds remaining freshwater")
    if marginal > remaining_marginal_ml + policy.volume_tolerance_ml:
        raise ValueError("rounded grant exceeds remaining marginal water")
    demand.allocated_fresh_ml += fresh
    demand.allocated_marginal_ml += marginal
    demand.deliverable_ml += delivery
    return (
        _subtract_capacity(remaining_fresh_ml, fresh, policy),
        _subtract_capacity(remaining_marginal_ml, marginal, policy),
    )


def _zone_result(
    demand: _Demand,
    *,
    policy: FreshwaterAllocationPolicy,
    availability_known: bool,
    fresh_bank_exhausted: bool,
    tied_priority: bool,
) -> ZoneWaterAllocation:
    irrigation = demand.input.irrigation_need
    quality = demand.input.water_quality
    critical = irrigation.status == "CRITICAL"
    reasons: list[str] = []
    reason_codes: list[AllocationReasonCode] = []
    warnings: list[str] = []
    warning_codes: list[AllocationWarningCode] = []

    if not demand.eligible:
        assert demand.blocked_reason_code is not None
        assert demand.blocked_reason is not None
        reason_codes.append(demand.blocked_reason_code)
        reasons.append(demand.blocked_reason)
        status = (
            "NO_IRRIGATION"
            if demand.blocked_reason_code == "NO_IRRIGATION_REQUEST"
            else "BLOCKED"
        )
        return ZoneWaterAllocation(
            zone_id=demand.input.zone_id,
            status=status,
            irrigation_status=irrigation.status,
            water_quality_strategy=quality.strategy,
            urgency_score=irrigation.urgency_score,
            critical=critical,
            stage_sensitivity=irrigation.stage_sensitivity,
            requested_water_ml=demand.requested_ml,
            reason_codes=reason_codes,
            reasons=reasons,
        )

    assert demand.requested_ml is not None
    assert demand.full_fresh_ml is not None
    assert demand.full_marginal_ml is not None
    assert demand.fresh_fraction is not None
    assert demand.marginal_fraction is not None
    reason_codes.append("M4_URGENCY_PRIORITY")
    reasons.append("allocation priority reuses the canonical Milestone 4 urgency score")
    if tied_priority:
        reason_codes.append("DETERMINISTIC_ZONE_ID_TIE_BREAK")
        reasons.append("equal urgency is resolved deterministically by Zone ID")
    if quality.strategy == "MARGINAL_ONLY":
        reason_codes.append("MARGINAL_ONLY_NO_FRESHWATER")
        reasons.append("the safe Milestone 5 strategy consumes no freshwater")

    critical_target = (
        demand.requested_ml * policy.critical_minimum_delivery_fraction
        if critical
        else None
    )
    critical_met = (
        demand.deliverable_ml + policy.volume_tolerance_ml >= critical_target
        if critical_target is not None
        else None
    )
    if critical:
        reason_codes.append("CRITICAL_MINIMUM_PHASE")
        reasons.append("the zone entered phase 1 because Milestone 4 marked it critical")
        if critical_met:
            reason_codes.append("CRITICAL_MINIMUM_MET")
            reasons.append("the configurable prototype minimum delivery was met")
        else:
            reason_codes.append("CRITICAL_MINIMUM_NOT_MET")
            reasons.append("available safe source capacity could not meet the prototype minimum")
            warning_codes.append("CRITICAL_MINIMUM_UNMET")
            warnings.append("the critical prototype minimum could not be supplied safely")
        warning_codes.append("PROTOTYPE_MINIMUM_NOT_SURVIVAL_GUARANTEE")
        warnings.append(CRITICAL_POLICY_WARNING)

    if not availability_known:
        status = "BLOCKED"
        reason_codes.append("SOURCE_AVAILABILITY_UNKNOWN")
        reasons.append("source-bank availability is missing and was not fabricated as zero")
        warning_codes.append("SOURCE_AVAILABILITY_UNKNOWN")
        warnings.append("safe allocation requires known fresh and marginal source volumes")
    elif demand.deliverable_ml <= policy.volume_tolerance_ml:
        if demand.fresh_fraction > 0 and fresh_bank_exhausted:
            status = "DEFERRED_NO_FRESHWATER"
            reason_codes.append("NO_FRESHWATER_AVAILABLE")
            reasons.append("the safe source ratio requires freshwater that is unavailable")
        else:
            status = "DEFERRED_NO_SAFE_WATER"
            reason_codes.append("NO_SAFE_SOURCE_CAPACITY")
            reasons.append("available source capacity cannot deliver the frozen safe strategy")
    elif demand.requested_ml - demand.deliverable_ml <= policy.volume_tolerance_ml:
        status = "FULLY_SERVED"
        reason_codes.append("FULL_REQUEST_ALLOCATED")
        reasons.append("the complete Milestone 4 water request is allocated")
    else:
        status = "PARTIALLY_SERVED"
        reason_codes.append("PARTIAL_REQUEST_ALLOCATED")
        reasons.append("source scarcity permits only a proportional partial delivery")
        warning_codes.append("PARTIAL_DELIVERY")
        warnings.append("the zone receives less than its full irrigation request")

    allocated_fresh_fraction = None
    allocated_marginal_fraction = None
    safe_ratio_preserved = None
    if demand.deliverable_ml > policy.volume_tolerance_ml:
        allocated_fresh_fraction = demand.allocated_fresh_ml / demand.deliverable_ml
        allocated_marginal_fraction = (
            demand.allocated_marginal_ml / demand.deliverable_ml
        )
        safe_ratio_preserved = (
            allocated_fresh_fraction + policy.ratio_tolerance
            >= demand.fresh_fraction
            and allocated_marginal_fraction
            <= demand.marginal_fraction + policy.ratio_tolerance
        )
        reason_codes.append("SAFE_SOURCE_RATIO_PRESERVED")
        reasons.append("fresh and marginal volumes were scaled together at the frozen safe ratio")
        warning_codes.append("PHYSICAL_TDS_VERIFICATION_REQUIRED")
        warnings.append(PHYSICAL_VERIFICATION_WARNING)

    return ZoneWaterAllocation(
        zone_id=demand.input.zone_id,
        status=status,
        irrigation_status=irrigation.status,
        water_quality_strategy=quality.strategy,
        urgency_score=irrigation.urgency_score,
        critical=critical,
        stage_sensitivity=irrigation.stage_sensitivity,
        requested_water_ml=demand.requested_ml,
        full_request_fresh_ml=demand.full_fresh_ml,
        full_request_marginal_ml=demand.full_marginal_ml,
        required_fresh_fraction=demand.fresh_fraction,
        required_marginal_fraction=demand.marginal_fraction,
        allocated_fresh_ml=demand.allocated_fresh_ml,
        allocated_marginal_ml=demand.allocated_marginal_ml,
        deliverable_water_ml=demand.deliverable_ml,
        service_fraction=min(1.0, demand.deliverable_ml / demand.requested_ml),
        allocated_fresh_fraction=allocated_fresh_fraction,
        allocated_marginal_fraction=allocated_marginal_fraction,
        full_request_predicted_tds_ppm=quality.predicted_tds_ppm,
        safe_ratio_preserved=safe_ratio_preserved,
        critical_minimum_target_ml=critical_target,
        critical_minimum_met=critical_met,
        reason_codes=reason_codes,
        reasons=reasons,
        warning_codes=warning_codes,
        warnings=warnings,
    )


def _validate_available(name: str, value: float | None) -> None:
    if value is not None and (not isfinite(value) or value < 0):
        raise ValueError(f"{name} must be finite and non-negative when available")


def _subtract_capacity(
    available: float,
    allocated: float,
    policy: FreshwaterAllocationPolicy,
) -> float:
    remaining = available - allocated
    if remaining < -policy.volume_tolerance_ml:
        raise ValueError("allocation exceeded a source bank")
    return max(0.0, remaining)


def _nonnegative_residual(
    available: float,
    allocated: float,
    policy: FreshwaterAllocationPolicy,
) -> float:
    residual = available - allocated
    if residual < -policy.volume_tolerance_ml:
        raise ValueError("reported allocation exceeded source availability")
    return max(0.0, residual)


freshwater_allocation_policy = allocation_policy_from_settings()
