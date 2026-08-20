from datetime import datetime, timedelta, timezone

from pydantic import ValidationError
import pytest

from app.schemas import (
    PrototypeIrrigationParameters,
    VivayuHealthState,
    WaterQualityPolicy,
    WaterSourceState,
    WaterSourceUpdateRequest,
)
from app.services.irrigation_need import calculate_irrigation_need, irrigation_need_policy
from app.services.water_quality import (
    calculate_water_quality_strategy,
    predicted_blend_tds_ppm,
)
from app.state import ApplicationStateStore


POLICY = WaterQualityPolicy(
    tds_safety_margin_ppm=50.0,
    source_stale_after_s=900.0,
    volume_rounding_decimals=6,
    volume_tolerance_ml=0.000001,
    predicted_tds_tolerance_ppm=0.000001,
)


def source(
    source_id: str,
    tds_ppm: float | None,
    *,
    available_l: float | None = 10.0,
    status: str = "SIMULATED",
    age_s: float | None = 0.0,
) -> WaterSourceState:
    return WaterSourceState.model_validate(
        {
            "source_id": source_id,
            "display_name": f"{source_id.title()} water",
            "tds_ppm": tds_ppm,
            "available_l": available_l,
            "last_measured_at": (
                datetime(2026, 8, 21, tzinfo=timezone.utc)
                if tds_ppm is not None
                else None
            ),
            "measurement_age_s": age_s if tds_ppm is not None else None,
            "quality_status": status if tds_ppm is not None else "UNKNOWN",
        }
    )


def strategy(
    *,
    requested_ml: float | None = 400.0,
    fresh_tds: float | None = 220.0,
    marginal_tds: float | None = 820.0,
    max_tds: float | None = 500.0,
    policy: WaterQualityPolicy = POLICY,
    fresh: WaterSourceState | None = None,
    marginal: WaterSourceState | None = None,
):
    return calculate_water_quality_strategy(
        zone_id="A",
        requested_water_ml=requested_ml,
        fresh_source=fresh or source("fresh", fresh_tds),
        marginal_source=marginal or source("marginal", marginal_tds),
        configured_max_tds_ppm=max_tds,
        policy=policy,
    )


@pytest.mark.parametrize("marginal_tds", [400.0, 450.0])
def test_marginal_at_or_below_target_uses_marginal_only(marginal_tds: float) -> None:
    result = strategy(marginal_tds=marginal_tds)

    assert result.strategy == "MARGINAL_ONLY"
    assert result.fresh_ml == 0.0
    assert result.marginal_ml == 400.0
    assert result.predicted_tds_ppm == marginal_tds
    assert result.safe is True


def test_controlled_blend_maximizes_marginal_fraction_safely() -> None:
    result = strategy()

    assert result.strategy == "CONTROLLED_BLEND"
    assert result.marginal_fraction == pytest.approx((450.0 - 220.0) / 600.0)
    assert result.marginal_ml == pytest.approx(153.333333)
    assert result.fresh_ml == pytest.approx(246.666667)
    assert result.fresh_ml + result.marginal_ml == pytest.approx(400.0)
    assert result.predicted_tds_ppm <= 450.0 + POLICY.predicted_tds_tolerance_ppm
    assert result.measured_tds_ppm is None
    assert result.physical_verification_required is True


def test_fresh_only_when_fresh_is_at_target_and_marginal_is_unsafe() -> None:
    result = strategy(fresh_tds=450.0)

    assert result.strategy == "FRESH_ONLY"
    assert result.fresh_ml == 400.0
    assert result.marginal_ml == 0.0
    assert result.predicted_tds_ppm == 450.0


def test_even_fresh_water_above_target_is_not_feasible() -> None:
    result = strategy(fresh_tds=451.0)

    assert result.strategy == "NOT_FEASIBLE"
    assert result.safe is False
    assert "NO_SOURCE_MEETS_TARGET" in result.reason_codes


def test_missing_crop_limit_or_safety_margin_requires_configuration() -> None:
    missing_limit = strategy(max_tds=None)
    no_margin = strategy(
        policy=POLICY.model_copy(update={"tds_safety_margin_ppm": None})
    )

    assert missing_limit.strategy == "CONFIG_REQUIRED"
    assert "CROP_TDS_LIMIT_MISSING" in missing_limit.reason_codes
    assert no_margin.strategy == "CONFIG_REQUIRED"
    assert "SAFETY_MARGIN_MISSING" in no_margin.reason_codes


@pytest.mark.parametrize("missing_source", ["fresh", "marginal"])
def test_missing_source_tds_never_returns_safe(missing_source: str) -> None:
    kwargs = {f"{missing_source}_tds": None}
    result = strategy(**kwargs)

    assert result.strategy == "SOURCE_QUALITY_UNKNOWN"
    assert result.safe is False


def test_stale_measured_source_never_returns_safe() -> None:
    stale_fresh = source("fresh", 220.0, status="STALE", age_s=901.0)

    result = strategy(fresh=stale_fresh)

    assert result.strategy == "SOURCE_QUALITY_UNKNOWN"
    assert "SOURCE_QUALITY_STALE" in result.reason_codes


def test_zero_request_is_explicit_and_negative_request_is_rejected() -> None:
    zero = strategy(requested_ml=0.0)

    assert zero.strategy == "NO_IRRIGATION_REQUEST"
    assert zero.fresh_ml == zero.marginal_ml == 0.0
    with pytest.raises(ValueError, match="non-negative"):
        strategy(requested_ml=-1.0)


@pytest.mark.parametrize("invalid_tds", [-1.0, float("inf"), float("nan")])
def test_invalid_source_tds_is_rejected_by_canonical_schema(invalid_tds: float) -> None:
    with pytest.raises(ValidationError):
        source("fresh", invalid_tds)


def test_equal_source_tds_is_handled_without_division_by_zero() -> None:
    safe = strategy(fresh_tds=300.0, marginal_tds=300.0)
    unsafe = strategy(fresh_tds=600.0, marginal_tds=600.0)

    assert safe.strategy == "MARGINAL_ONLY"
    assert "EQUAL_SOURCE_TDS" in safe.reason_codes
    assert unsafe.strategy == "NOT_FEASIBLE"
    assert "EQUAL_SOURCE_TDS" in unsafe.reason_codes


def test_reversed_source_quality_is_never_silently_normalized() -> None:
    result = strategy(fresh_tds=820.0, marginal_tds=220.0)

    assert result.strategy == "NOT_FEASIBLE"
    assert "SOURCE_ORDER_ANOMALY" in result.reason_codes
    assert "SOURCE_LABEL_ORDER_ANOMALY" in result.warning_codes


def test_safety_margin_at_or_above_crop_limit_is_not_feasible() -> None:
    result = strategy(
        policy=POLICY.model_copy(update={"tds_safety_margin_ppm": 500.0})
    )

    assert result.strategy == "NOT_FEASIBLE"
    assert "SAFETY_TARGET_INVALID" in result.reason_codes


def test_weighted_prediction_equation_is_exact() -> None:
    predicted = predicted_blend_tds_ppm(250.0, 200.0, 150.0, 800.0)

    assert predicted == 425.0


def test_rounding_boundary_remains_conservative_and_conserves_volume() -> None:
    result = strategy(
        requested_ml=1.000001,
        fresh_tds=200.0,
        marginal_tds=700.0,
        max_tds=450.000001,
    )

    assert result.strategy == "CONTROLLED_BLEND"
    assert result.fresh_ml + result.marginal_ml == pytest.approx(1.000001, abs=1e-6)
    assert result.predicted_tds_ppm <= (
        result.safety_target_tds_ppm + POLICY.predicted_tds_tolerance_ppm
    )


def test_sub_quantum_positive_request_safely_falls_back_to_fresh_only() -> None:
    result = strategy(requested_ml=0.0000001)

    assert result.strategy == "FRESH_ONLY"
    assert result.fresh_ml == 0.0000001
    assert result.marginal_ml == 0.0
    assert result.safe is True


@pytest.mark.parametrize(
    ("available_l", "expected_sufficient"),
    [(10.0, True), (0.01, False), (None, None)],
)
def test_availability_reports_single_zone_satisfiability_only(
    available_l: float | None,
    expected_sufficient: bool | None,
) -> None:
    result = strategy(
        fresh=source("fresh", 220.0, available_l=available_l),
        marginal=source("marginal", 820.0, available_l=available_l),
    )

    assert result.source_volume_sufficient is expected_sufficient
    assert result.currently_satisfiable is (expected_sufficient is True)


def test_strategy_pipeline_is_independent_of_vivayu_health_state() -> None:
    store = ApplicationStateStore()
    store.update_irrigation_parameters(
        "A",
        PrototypeIrrigationParameters(
            target_moisture_pct=40.0,
            critical_moisture_pct=25.0,
            ml_per_moisture_point=20.0,
        ),
    )
    state = store.get_state()
    zone = state.zones["A"]
    altered_zone = zone.model_copy(
        update={
            "vivayu_health": VivayuHealthState(
                available=True,
                risk_level="high",
                pattern="test-pattern",
                confidence_pct=99.0,
                research_only=True,
                reason="test-only unrelated research signal",
            )
        },
        deep=True,
    )
    first_request = calculate_irrigation_need(
        zone, state.weather, irrigation_need_policy
    ).requested_water_ml
    second_request = calculate_irrigation_need(
        altered_zone, state.weather, irrigation_need_policy
    ).requested_water_ml

    first = strategy(requested_ml=first_request)
    second = strategy(requested_ml=second_request)

    assert first_request == second_request
    assert first == second


def test_hardware_source_age_is_exposed_and_old_measurement_is_stale() -> None:
    store = ApplicationStateStore(data_mode="hardware")
    measured_at = datetime.now(timezone.utc) - timedelta(hours=5)

    updated = store.update_water_source(
        "fresh",
        WaterSourceUpdateRequest(
            tds_ppm=220.0,
            available_l=1.0,
            last_measured_at=measured_at,
        ),
    )
    snapshot = store.get_state().water.fresh

    assert updated.quality_status == "STALE"
    assert snapshot.quality_status == "STALE"
    assert snapshot.measurement_age_s is not None
    assert snapshot.measurement_age_s >= 5 * 60 * 60
