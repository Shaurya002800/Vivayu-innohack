from datetime import datetime, timezone

import pytest

from app.schemas import (
    FreshwaterAllocationPolicy,
    IrrigationNeedResult,
    IrrigationUrgencyComponents,
    VivayuHealthState,
    WaterQualityPolicy,
    WaterSourceState,
    ZoneAllocationInput,
)
from app.services.freshwater_allocator import allocate_freshwater
from app.services.irrigation_need import irrigation_need_policy
from app.services.water_quality import calculate_water_quality_strategy


POLICY = FreshwaterAllocationPolicy(
    critical_minimum_delivery_fraction=0.25,
    volume_rounding_decimals=6,
    volume_tolerance_ml=0.000001,
    ratio_tolerance=0.000001,
)
QUALITY_POLICY = WaterQualityPolicy(
    tds_safety_margin_ppm=50.0,
    source_stale_after_s=900.0,
    volume_rounding_decimals=6,
    volume_tolerance_ml=0.000001,
    predicted_tds_tolerance_ppm=0.000001,
)


def irrigation(
    zone_id: str,
    *,
    requested_ml: float | None = 500.0,
    status: str = "NEEDED",
    urgency_score: float = 0.5,
) -> IrrigationNeedResult:
    if status in {"CONFIG_REQUIRED", "SENSOR_UNAVAILABLE"}:
        return IrrigationNeedResult.model_validate(
            {
                "zone_id": zone_id,
                "status": status,
                "urgency": "blocked",
                "needs_irrigation": False,
                "actionable": False,
                "weather_status": "SIMULATED",
                "weather_assistance_available": True,
                "policy": irrigation_need_policy,
                "reason_codes": ["CROP_CONTEXT_INVALID"],
                "reasons": ["test blocked irrigation input"],
            }
        )
    if status in {"NOT_NEEDED", "DEFER_FOR_RAIN"}:
        return IrrigationNeedResult.model_validate(
            {
                "zone_id": zone_id,
                "status": status,
                "urgency": "none",
                "urgency_score": 0.0,
                "urgency_components": IrrigationUrgencyComponents(),
                "needs_irrigation": False,
                "actionable": False,
                "current_moisture_pct": 40.0,
                "target_moisture_pct": 40.0,
                "critical_moisture_pct": 25.0,
                "moisture_deficit_pct": 0.0,
                "ml_per_moisture_point": 20.0,
                "base_requested_ml": 0.0,
                "requested_water_ml": 0.0,
                "telemetry_age_s": 1.0,
                "crop_context_status": "READY",
                "weather_status": "SIMULATED",
                "weather_assistance_available": True,
                "rain_deferral_applied": status == "DEFER_FOR_RAIN",
                "policy": irrigation_need_policy,
                "reason_codes": [
                    "RAIN_DEFERRED" if status == "DEFER_FOR_RAIN" else "AT_OR_ABOVE_TARGET"
                ],
                "reasons": ["test no-irrigation input"],
            }
        )
    assert requested_ml is not None and requested_ml > 0
    critical = status == "CRITICAL"
    return IrrigationNeedResult.model_validate(
        {
            "zone_id": zone_id,
            "status": status,
            "urgency": "high" if critical else "moderate",
            "urgency_score": urgency_score,
            "urgency_components": IrrigationUrgencyComponents(),
            "needs_irrigation": True,
            "actionable": True,
            "current_moisture_pct": 20.0 if critical else 30.0,
            "target_moisture_pct": 40.0,
            "critical_moisture_pct": 25.0,
            "moisture_deficit_pct": 20.0 if critical else 10.0,
            "ml_per_moisture_point": 20.0,
            "base_requested_ml": requested_ml,
            "requested_water_ml": requested_ml,
            "telemetry_age_s": 1.0,
            "crop_context_status": "READY",
            "growth_stage": "mid",
            "stage_sensitivity": "high",
            "weather_status": "SIMULATED",
            "weather_assistance_available": True,
            "policy": irrigation_need_policy,
            "reason_codes": ["AT_OR_BELOW_CRITICAL" if critical else "BELOW_TARGET"],
            "reasons": ["test actionable irrigation input"],
        }
    )


def source(source_id: str, tds_ppm: float) -> WaterSourceState:
    return WaterSourceState.model_validate(
        {
            "source_id": source_id,
            "display_name": source_id,
            "tds_ppm": tds_ppm,
            "available_l": 100.0,
            "last_measured_at": datetime(2026, 8, 21, tzinfo=timezone.utc),
            "measurement_age_s": 0.0,
            "quality_status": "SIMULATED",
        }
    )


def zone_input(
    zone_id: str,
    *,
    requested_ml: float = 500.0,
    strategy: str = "CONTROLLED_BLEND",
    irrigation_status: str = "NEEDED",
    urgency_score: float = 0.5,
) -> ZoneAllocationInput:
    need = irrigation(
        zone_id,
        requested_ml=(None if irrigation_status in {"CONFIG_REQUIRED", "SENSOR_UNAVAILABLE"} else requested_ml),
        status=irrigation_status,
        urgency_score=urgency_score,
    )
    if strategy == "CONTROLLED_BLEND":
        fresh_tds, marginal_tds, max_tds = 200.0, 700.0, 450.0
    elif strategy == "FRESH_ONLY":
        fresh_tds, marginal_tds, max_tds = 400.0, 700.0, 450.0
    elif strategy == "MARGINAL_ONLY":
        fresh_tds, marginal_tds, max_tds = 200.0, 350.0, 450.0
    elif strategy == "BLOCKED":
        fresh_tds, marginal_tds, max_tds = 200.0, 700.0, None
    else:
        raise ValueError("unsupported test strategy")
    quality = calculate_water_quality_strategy(
        zone_id=zone_id,
        requested_water_ml=need.requested_water_ml,
        fresh_source=source("fresh", fresh_tds),
        marginal_source=source("marginal", marginal_tds),
        configured_max_tds_ppm=max_tds,
        policy=QUALITY_POLICY,
    )
    return ZoneAllocationInput.model_validate(
        {
            "zone_id": zone_id,
            "irrigation_need": need,
            "water_quality": quality,
        }
    )


def no_irrigation(zone_id: str) -> ZoneAllocationInput:
    return zone_input(
        zone_id,
        requested_ml=0.0,
        strategy="CONTROLLED_BLEND",
        irrigation_status="NOT_NEEDED",
        urgency_score=0.0,
    )


def allocate(
    zone_a: ZoneAllocationInput,
    zone_b: ZoneAllocationInput | None = None,
    *,
    fresh_ml: float | None = 10_000.0,
    marginal_ml: float | None = 10_000.0,
):
    return allocate_freshwater(
        freshwater_available_ml=fresh_ml,
        marginal_available_ml=marginal_ml,
        zone_inputs={"A": zone_a, "B": zone_b or no_irrigation("B")},
        policy=POLICY,
    )


def test_enough_source_capacity_fully_serves_both_zones() -> None:
    result = allocate(zone_input("A"), zone_input("B"))

    assert result.zones["A"].status == "FULLY_SERVED"
    assert result.zones["B"].status == "FULLY_SERVED"
    assert result.total_deliverable_water_ml == 1000.0
    assert result.scarcity_active is False


def test_combined_freshwater_shortage_is_deterministic() -> None:
    result = allocate(
        zone_input("A", urgency_score=0.7),
        zone_input("B", urgency_score=0.4),
        fresh_ml=450.0,
    )

    assert result.scarcity_active is True
    assert result.zones["A"].status == "FULLY_SERVED"
    assert result.zones["B"].status == "PARTIALLY_SERVED"
    assert result.freshwater_allocated_ml <= 450.0


def test_critical_zone_is_protected_before_noncritical_zone() -> None:
    result = allocate(
        zone_input("A", irrigation_status="CRITICAL", urgency_score=0.9),
        zone_input("B", urgency_score=0.8),
        fresh_ml=300.0,
        marginal_ml=1000.0,
    )

    assert result.critical_phase_order == ("A",)
    assert result.zones["A"].status == "FULLY_SERVED"
    assert result.zones["A"].critical_minimum_met is True
    assert result.zones["B"].status == "DEFERRED_NO_FRESHWATER"


def test_both_critical_zones_receive_phase_one_minimum_when_resources_permit() -> None:
    result = allocate(
        zone_input("A", irrigation_status="CRITICAL", urgency_score=0.8),
        zone_input("B", irrigation_status="CRITICAL", urgency_score=0.7),
        fresh_ml=150.0,
        marginal_ml=100.0,
    )

    assert result.critical_phase_order == ("A", "B")
    assert result.zones["A"].deliverable_water_ml == 125.0
    assert result.zones["B"].deliverable_water_ml == 125.0
    assert result.zones["A"].critical_minimum_met is True
    assert result.zones["B"].critical_minimum_met is True


def test_identical_priority_uses_zone_id_tie_break() -> None:
    result = allocate(
        zone_input("A", urgency_score=0.5),
        zone_input("B", urgency_score=0.5),
        fresh_ml=300.0,
        marginal_ml=200.0,
    )

    assert result.remaining_phase_order == ("A", "B")
    assert result.zones["A"].status == "FULLY_SERVED"
    assert result.zones["B"].status == "DEFERRED_NO_FRESHWATER"
    assert "DETERMINISTIC_ZONE_ID_TIE_BREAK" in result.zones["A"].reason_codes


def test_marginal_only_zone_does_not_consume_scarce_freshwater() -> None:
    result = allocate(
        zone_input("A", strategy="MARGINAL_ONLY", urgency_score=0.4),
        zone_input("B", strategy="CONTROLLED_BLEND", urgency_score=0.8),
        fresh_ml=0.0,
        marginal_ml=1000.0,
    )

    assert result.zones["A"].status == "FULLY_SERVED"
    assert result.zones["A"].allocated_fresh_ml == 0.0
    assert result.zones["A"].allocated_marginal_ml == 500.0
    assert result.zones["B"].status == "DEFERRED_NO_FRESHWATER"
    assert result.freshwater_allocated_ml == 0.0


def test_fresh_only_zone_uses_one_fresh_ml_per_delivered_ml() -> None:
    result = allocate(
        zone_input("A", strategy="FRESH_ONLY"),
        fresh_ml=300.0,
    )

    zone = result.zones["A"]
    assert zone.status == "PARTIALLY_SERVED"
    assert zone.allocated_fresh_ml == zone.deliverable_water_ml == 300.0
    assert zone.allocated_marginal_ml == 0.0


def test_partial_controlled_blend_preserves_ratio_and_scales_both_sources() -> None:
    result = allocate(
        zone_input("A", requested_ml=500.0, strategy="CONTROLLED_BLEND"),
        fresh_ml=150.0,
        marginal_ml=1000.0,
    )

    zone = result.zones["A"]
    assert zone.full_request_fresh_ml == 300.0
    assert zone.full_request_marginal_ml == 200.0
    assert zone.allocated_fresh_ml == pytest.approx(150.0)
    assert zone.allocated_marginal_ml == pytest.approx(100.0)
    assert zone.deliverable_water_ml == pytest.approx(250.0)
    assert zone.safe_ratio_preserved is True
    assert zone.allocated_marginal_fraction == pytest.approx(0.4)


def test_reducing_freshwater_never_keeps_full_marginal_volume() -> None:
    full = allocate(zone_input("A"), fresh_ml=300.0, marginal_ml=200.0)
    half = allocate(zone_input("A"), fresh_ml=150.0, marginal_ml=200.0)

    assert full.zones["A"].allocated_marginal_ml == 200.0
    assert half.zones["A"].allocated_marginal_ml == pytest.approx(100.0)
    assert half.zones["A"].deliverable_water_ml == pytest.approx(250.0)


def test_zero_marginal_water_blocks_controlled_blend_without_substitution() -> None:
    result = allocate(zone_input("A"), fresh_ml=1000.0, marginal_ml=0.0)

    assert result.zones["A"].status == "DEFERRED_NO_SAFE_WATER"
    assert result.zones["A"].deliverable_water_ml == 0.0


def test_both_sources_insufficient_never_overallocates_either_bank() -> None:
    result = allocate(
        zone_input("A", urgency_score=0.7),
        zone_input("B", urgency_score=0.4),
        fresh_ml=90.0,
        marginal_ml=60.0,
    )

    assert result.freshwater_allocated_ml <= 90.0
    assert result.marginal_allocated_ml <= 60.0
    assert result.total_deliverable_water_ml <= 150.0


def test_no_irrigation_and_blocked_quality_never_enter_actionable_pool() -> None:
    result = allocate(
        no_irrigation("A"),
        zone_input("B", strategy="BLOCKED"),
    )

    assert result.zones["A"].status == "NO_IRRIGATION"
    assert result.zones["B"].status == "BLOCKED"
    assert result.total_deliverable_water_ml == 0.0


def test_missing_source_bank_is_blocked_instead_of_treated_as_zero() -> None:
    result = allocate(zone_input("A"), fresh_ml=None, marginal_ml=1000.0)

    assert result.zones["A"].status == "BLOCKED"
    assert result.freshwater_available_ml is None
    assert result.scarcity_active is None
    assert "SOURCE_AVAILABILITY_UNKNOWN" in result.reason_codes


def test_rounding_boundary_conserves_volume_without_exceeding_bank() -> None:
    result = allocate(
        zone_input("A"),
        fresh_ml=150.0000004,
        marginal_ml=1000.0,
    )
    zone = result.zones["A"]

    assert zone.allocated_fresh_ml + zone.allocated_marginal_ml == pytest.approx(
        zone.deliverable_water_ml, abs=POLICY.volume_tolerance_ml
    )
    assert result.freshwater_allocated_ml <= 150.0000004
    assert zone.deliverable_water_ml <= zone.requested_water_ml


def test_only_freshwater_bank_change_changes_delivery_with_other_inputs_fixed() -> None:
    inputs = {
        "A": zone_input("A", urgency_score=0.7),
        "B": zone_input("B", urgency_score=0.4),
    }
    abundant = allocate_freshwater(
        freshwater_available_ml=1000.0,
        marginal_available_ml=1000.0,
        zone_inputs=inputs,
        policy=POLICY,
    )
    scarce = allocate_freshwater(
        freshwater_available_ml=300.0,
        marginal_available_ml=1000.0,
        zone_inputs=inputs,
        policy=POLICY,
    )

    assert abundant.total_requested_water_ml == scarce.total_requested_water_ml
    assert abundant.zones["A"].full_request_predicted_tds_ppm == (
        scarce.zones["A"].full_request_predicted_tds_ppm
    )
    assert abundant.total_deliverable_water_ml > scarce.total_deliverable_water_ml
    assert abundant.scarcity_active is False
    assert scarce.scarcity_active is True


def test_allocator_is_independent_of_vivayu_health_state() -> None:
    unavailable = VivayuHealthState(available=False, reason="test unavailable")
    available = VivayuHealthState(
        available=True,
        risk_level="high",
        pattern="test pattern",
        confidence_pct=99.0,
    )
    inputs = {"A": zone_input("A"), "B": no_irrigation("B")}

    first = allocate_freshwater(
        freshwater_available_ml=150.0,
        marginal_available_ml=1000.0,
        zone_inputs=inputs,
        policy=POLICY,
    )
    second = allocate_freshwater(
        freshwater_available_ml=150.0,
        marginal_available_ml=1000.0,
        zone_inputs=inputs,
        policy=POLICY,
    )

    assert unavailable != available
    assert "vivayu_health" not in ZoneAllocationInput.model_fields
    assert first == second


@pytest.mark.parametrize("fresh_bank", [0.0, 0.0000004, 1.0, 50.0, 150.0, 300.0, 999.999999])
@pytest.mark.parametrize("marginal_bank", [0.0, 75.0, 400.0, 2000.0])
def test_property_allocated_freshwater_can_never_exceed_bank(
    fresh_bank: float,
    marginal_bank: float,
) -> None:
    combinations = (
        ("CONTROLLED_BLEND", "CONTROLLED_BLEND"),
        ("FRESH_ONLY", "CONTROLLED_BLEND"),
        ("MARGINAL_ONLY", "FRESH_ONLY"),
    )
    for strategy_a, strategy_b in combinations:
        result = allocate(
            zone_input("A", requested_ml=333.333333, strategy=strategy_a, urgency_score=0.6),
            zone_input("B", requested_ml=777.777777, strategy=strategy_b, urgency_score=0.4),
            fresh_ml=fresh_bank,
            marginal_ml=marginal_bank,
        )
        assert result.freshwater_allocated_ml <= (
            fresh_bank + POLICY.volume_tolerance_ml
        )
        assert result.marginal_allocated_ml <= (
            marginal_bank + POLICY.volume_tolerance_ml
        )
        for zone in result.zones.values():
            assert zone.deliverable_water_ml <= (
                (zone.requested_water_ml or 0.0) + POLICY.volume_tolerance_ml
            )
            assert zone.allocated_fresh_ml + zone.allocated_marginal_ml == pytest.approx(
                zone.deliverable_water_ml,
                abs=POLICY.volume_tolerance_ml,
            )
