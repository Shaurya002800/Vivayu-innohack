from datetime import date

from pydantic import ValidationError
import pytest

from app.schemas import (
    IrrigationNeedPolicy,
    PrototypeIrrigationParameters,
    VivayuHealthState,
    WeatherState,
    ZoneConfig,
    ZoneState,
    ZoneTelemetry,
)
from app.services.crop_service import FutureSowingDateError
from app.services.irrigation_need import base_water_need_ml, calculate_irrigation_need
from app.state import ApplicationStateStore


TODAY = date(2026, 8, 21)


@pytest.fixture
def policy() -> IrrigationNeedPolicy:
    return IrrigationNeedPolicy(
        stale_telemetry_after_s=10.0,
        strong_rain_probability_pct=70.0,
        meaningful_rain_6h_mm=2.0,
        high_et0_6h_mm=1.0,
        soil_deficit_weight=0.60,
        critical_moisture_boost=0.25,
        high_stage_sensitivity_boost=0.10,
        moderate_stage_sensitivity_boost=0.05,
        high_et0_boost=0.05,
    )


def configured_zone(
    *,
    moisture_pct: float | None = 30.0,
    target_pct: float | None = 40.0,
    critical_pct: float | None = 25.0,
    ml_per_point: float | None = 20.0,
    telemetry_age_s: float | None = 1.0,
    online: bool = True,
    manual_stage: str | None = None,
) -> tuple[ZoneState, WeatherState]:
    store = ApplicationStateStore(today_provider=lambda: TODAY)
    if manual_stage is not None:
        store.set_manual_stage("A", manual_stage)
    store.update_irrigation_parameters(
        "A",
        PrototypeIrrigationParameters(
            target_moisture_pct=target_pct,
            critical_moisture_pct=critical_pct,
            ml_per_moisture_point=ml_per_point,
        ),
    )
    base_zone = store.get_zone("A")
    telemetry = ZoneTelemetry.model_validate(
        {**base_zone.telemetry.model_dump(), "soil_moisture_pct": moisture_pct}
    )
    zone = ZoneState(
        zone_id="A",
        config=base_zone.config,
        telemetry=telemetry,
        growth_stage=base_zone.growth_stage,
        days_after_sowing=base_zone.days_after_sowing,
        crop_context=base_zone.crop_context,
        telemetry_age_s=telemetry_age_s,
        online=online,
        vivayu_health=base_zone.vivayu_health,
    )
    return zone, store.get_state().weather


def weather(
    *,
    rain_probability: float | None = 10.0,
    rain_mm: float | None = 0.0,
    et0_mm: float | None = 0.5,
) -> WeatherState:
    return WeatherState(
        status="SIMULATED",
        rain_probability_6h_pct=rain_probability,
        rain_6h_mm=rain_mm,
        et0_6h_mm=et0_mm,
        fetched_at="2026-08-21T10:00:00+00:00",
        stale=False,
        provider="test",
        provider_status="SIMULATED",
    )


def test_base_water_need_uses_exact_prototype_formula() -> None:
    deficit, requested = base_water_need_ml(22.0, 40.0, 20.0)

    assert deficit == 18.0
    assert requested == 360.0


@pytest.mark.parametrize("calibration", [0.0, -1.0, float("nan")])
def test_base_water_need_rejects_invalid_calibration(calibration: float) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        base_water_need_ml(22.0, 40.0, calibration)


@pytest.mark.parametrize("moisture_pct", [40.0, 55.0])
def test_no_irrigation_at_or_above_target(
    moisture_pct: float,
    policy: IrrigationNeedPolicy,
) -> None:
    zone, _ = configured_zone(moisture_pct=moisture_pct)

    result = calculate_irrigation_need(zone, weather(), policy)

    assert result.status == "NOT_NEEDED"
    assert result.needs_irrigation is False
    assert result.moisture_deficit_pct == 0.0
    assert result.base_requested_ml == 0.0
    assert result.requested_water_ml == 0.0
    assert result.urgency_score == 0.0
    assert result.reason_codes == ("AT_OR_ABOVE_TARGET",)


def test_irrigation_below_target_uses_unmodified_base_volume(
    policy: IrrigationNeedPolicy,
) -> None:
    zone, _ = configured_zone(moisture_pct=30.0)

    result = calculate_irrigation_need(zone, weather(), policy)

    assert result.status == "NEEDED"
    assert result.needs_irrigation is True
    assert result.actionable is True
    assert result.moisture_deficit_pct == 10.0
    assert result.base_requested_ml == 200.0
    assert result.requested_water_ml == 200.0
    assert "PROTOTYPE_VOLUME_CALIBRATION" in result.warning_codes


@pytest.mark.parametrize("moisture_pct", [25.0, 20.0])
def test_at_or_below_critical_is_critical(
    moisture_pct: float,
    policy: IrrigationNeedPolicy,
) -> None:
    zone, _ = configured_zone(moisture_pct=moisture_pct)

    result = calculate_irrigation_need(zone, weather(), policy)

    assert result.status == "CRITICAL"
    assert result.urgency == "high"
    assert result.needs_irrigation is True
    assert "AT_OR_BELOW_CRITICAL" in result.reason_codes
    assert result.urgency_components is not None
    assert result.urgency_components.critical_moisture == 0.25


def test_strong_meaningful_rain_defers_noncritical_irrigation(
    policy: IrrigationNeedPolicy,
) -> None:
    zone, _ = configured_zone(moisture_pct=30.0)

    result = calculate_irrigation_need(
        zone,
        weather(rain_probability=85.0, rain_mm=7.4),
        policy,
    )

    assert result.status == "DEFER_FOR_RAIN"
    assert result.needs_irrigation is False
    assert result.rain_deferral_applied is True
    assert result.base_requested_ml == 200.0
    assert result.requested_water_ml == 0.0
    assert "RAIN_DEFERRED" in result.reason_codes


def test_rain_probability_alone_does_not_defer(
    policy: IrrigationNeedPolicy,
) -> None:
    zone, _ = configured_zone(moisture_pct=30.0)

    result = calculate_irrigation_need(
        zone,
        weather(rain_probability=90.0, rain_mm=0.5),
        policy,
    )

    assert result.status == "NEEDED"
    assert result.rain_deferral_applied is False


def test_critical_zone_is_not_blindly_deferred_for_rain(
    policy: IrrigationNeedPolicy,
) -> None:
    zone, _ = configured_zone(moisture_pct=22.0)

    result = calculate_irrigation_need(
        zone,
        weather(rain_probability=95.0, rain_mm=12.0),
        policy,
    )

    assert result.status == "CRITICAL"
    assert result.requested_water_ml == 360.0
    assert result.rain_deferral_applied is False
    assert "CRITICAL_OVERRIDES_RAIN" in result.reason_codes


def test_weather_unavailable_falls_back_to_valid_local_inputs(
    policy: IrrigationNeedPolicy,
) -> None:
    zone, _ = configured_zone(moisture_pct=30.0)
    offline = WeatherState(
        status="OFFLINE",
        stale=True,
        provider="test",
        provider_status="ERROR",
        error="provider unavailable",
    )

    result = calculate_irrigation_need(zone, offline, policy)

    assert result.status == "NEEDED"
    assert result.requested_water_ml == 200.0
    assert result.weather_assistance_available is False
    assert "WEATHER_ASSISTANCE_UNAVAILABLE" in result.warning_codes


def test_et0_changes_urgency_context_but_not_water_volume(
    policy: IrrigationNeedPolicy,
) -> None:
    zone, _ = configured_zone(moisture_pct=30.0)

    low = calculate_irrigation_need(zone, weather(et0_mm=0.5), policy)
    high = calculate_irrigation_need(zone, weather(et0_mm=1.0), policy)

    assert high.requested_water_ml == low.requested_water_ml == 200.0
    assert high.urgency_score == pytest.approx(low.urgency_score + 0.05)
    assert high.et0_urgency_applied is True
    assert high.urgency_components is not None
    assert high.urgency_components.high_et0 == 0.05
    assert "HIGH_ET0" in high.reason_codes


def test_invalid_crop_context_propagates_as_config_required(
    policy: IrrigationNeedPolicy,
) -> None:
    zone, _ = configured_zone()
    assert zone.crop_context is not None
    invalid_context = zone.crop_context.model_copy(
        update={"status": "SOWING_DATE_MISSING"},
        deep=True,
    )
    invalid_zone = ZoneState(
        **{**zone.model_dump(), "crop_context": invalid_context}
    )

    result = calculate_irrigation_need(invalid_zone, weather(), policy)

    assert result.status == "CONFIG_REQUIRED"
    assert result.actionable is False
    assert "CROP_CONTEXT_INVALID" in result.reason_codes
    assert result.requested_water_ml is None


def test_future_sowing_config_is_rejected_before_preview(
    policy: IrrigationNeedPolicy,
) -> None:
    store = ApplicationStateStore(today_provider=lambda: TODAY)
    before = store.get_zone("A")
    future_config = ZoneConfig.model_validate(
        {**before.config.model_dump(), "sowing_date": "2026-08-22"}
    )

    with pytest.raises(FutureSowingDateError):
        store.update_zone_config("A", future_config)

    assert store.get_zone("A") == before


def test_missing_thresholds_return_config_required(
    policy: IrrigationNeedPolicy,
) -> None:
    zone, state_weather = configured_zone(
        target_pct=None,
        critical_pct=None,
        ml_per_point=20.0,
    )

    result = calculate_irrigation_need(zone, state_weather, policy)

    assert result.status == "CONFIG_REQUIRED"
    assert result.requested_water_ml is None
    assert result.urgency_score is None
    assert "TARGET_MOISTURE_MISSING" in result.reason_codes
    assert "CRITICAL_MOISTURE_MISSING" in result.reason_codes


def test_missing_calibration_returns_config_required(
    policy: IrrigationNeedPolicy,
) -> None:
    zone, state_weather = configured_zone(ml_per_point=None)

    result = calculate_irrigation_need(zone, state_weather, policy)

    assert result.status == "CONFIG_REQUIRED"
    assert result.base_requested_ml is None
    assert "CALIBRATION_MISSING" in result.reason_codes


@pytest.mark.parametrize("calibration", [0.0, -1.0])
def test_invalid_calibration_is_rejected(calibration: float) -> None:
    with pytest.raises(ValidationError):
        PrototypeIrrigationParameters(
            target_moisture_pct=40.0,
            critical_moisture_pct=25.0,
            ml_per_moisture_point=calibration,
        )


def test_invalid_threshold_order_is_rejected() -> None:
    with pytest.raises(ValidationError, match="lower than target"):
        PrototypeIrrigationParameters(
            target_moisture_pct=25.0,
            critical_moisture_pct=25.0,
            ml_per_moisture_point=20.0,
        )


def test_stale_telemetry_blocks_calculation(policy: IrrigationNeedPolicy) -> None:
    zone, state_weather = configured_zone(telemetry_age_s=10.1)

    result = calculate_irrigation_need(zone, state_weather, policy)

    assert result.status == "SENSOR_UNAVAILABLE"
    assert result.actionable is False
    assert result.requested_water_ml is None
    assert "TELEMETRY_STALE" in result.reason_codes


def test_null_soil_sensor_blocks_calculation(policy: IrrigationNeedPolicy) -> None:
    zone, state_weather = configured_zone(moisture_pct=None)

    result = calculate_irrigation_need(zone, state_weather, policy)

    assert result.status == "SENSOR_UNAVAILABLE"
    assert result.current_moisture_pct is None
    assert "SOIL_SENSOR_MISSING" in result.reason_codes


def test_manual_stage_override_affects_only_urgency_metadata(
    policy: IrrigationNeedPolicy,
) -> None:
    ordinary, state_weather = configured_zone(moisture_pct=30.0)
    sensitive, _ = configured_zone(moisture_pct=30.0, manual_stage="mid_season")

    ordinary_result = calculate_irrigation_need(ordinary, state_weather, policy)
    sensitive_result = calculate_irrigation_need(sensitive, state_weather, policy)

    assert sensitive_result.growth_stage == "mid_season"
    assert sensitive_result.stage_sensitivity == "high"
    assert sensitive_result.stage_urgency_applied is True
    assert sensitive_result.requested_water_ml == ordinary_result.requested_water_ml
    assert sensitive_result.urgency_score == pytest.approx(
        ordinary_result.urgency_score + 0.10
    )


def test_zone_parameter_updates_are_isolated() -> None:
    store = ApplicationStateStore(today_provider=lambda: TODAY)
    zone_b_before = store.get_zone("B")
    parameters = PrototypeIrrigationParameters(
        target_moisture_pct=40.0,
        critical_moisture_pct=25.0,
        ml_per_moisture_point=20.0,
    )

    store.update_irrigation_parameters("A", parameters)

    assert store.get_zone("A").config.irrigation_parameters == parameters
    assert store.get_zone("A").crop_context is not None
    assert store.get_zone("A").crop_context.target_moisture_pct == 40.0
    assert store.get_zone("B") == zone_b_before


def test_reasons_and_result_are_deterministic(policy: IrrigationNeedPolicy) -> None:
    zone, state_weather = configured_zone(moisture_pct=30.0, manual_stage="mid_season")

    first = calculate_irrigation_need(zone, state_weather, policy)
    second = calculate_irrigation_need(zone, state_weather, policy)

    assert first == second
    assert first.reason_codes == (
        "BELOW_TARGET",
        "SENSITIVE_STAGE",
        "NO_MEANINGFUL_RAIN",
    )
    assert len(first.reason_codes) == len(first.reasons)


def test_water_request_is_never_negative(policy: IrrigationNeedPolicy) -> None:
    zone, state_weather = configured_zone(moisture_pct=100.0)

    result = calculate_irrigation_need(zone, state_weather, policy)

    assert result.moisture_deficit_pct == 0.0
    assert result.requested_water_ml == 0.0


def test_vivayu_health_cannot_change_irrigation_need(
    policy: IrrigationNeedPolicy,
) -> None:
    zone, state_weather = configured_zone(moisture_pct=30.0)
    alternate_health = VivayuHealthState(
        available=True,
        risk_level="high",
        pattern="alternate_research_pattern",
        confidence_pct=99.0,
        research_only=True,
    )
    alternate_zone = ZoneState(
        **{**zone.model_dump(), "vivayu_health": alternate_health}
    )

    baseline = calculate_irrigation_need(zone, state_weather, policy)
    changed_health = calculate_irrigation_need(alternate_zone, state_weather, policy)

    assert changed_health == baseline


def test_policy_constants_are_exposed_in_result(policy: IrrigationNeedPolicy) -> None:
    zone, state_weather = configured_zone()

    result = calculate_irrigation_need(zone, state_weather, policy)

    assert result.policy == policy
    assert result.policy.soil_deficit_weight == 0.60
    assert result.policy.critical_moisture_boost == 0.25


def test_policy_rejects_hidden_overweight_urgency_components() -> None:
    with pytest.raises(ValidationError, match="sum cannot exceed 1"):
        IrrigationNeedPolicy(
            stale_telemetry_after_s=10.0,
            strong_rain_probability_pct=70.0,
            meaningful_rain_6h_mm=2.0,
            high_et0_6h_mm=1.0,
            soil_deficit_weight=0.80,
            critical_moisture_boost=0.25,
            high_stage_sensitivity_boost=0.10,
            moderate_stage_sensitivity_boost=0.05,
            high_et0_boost=0.05,
        )
