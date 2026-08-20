"""Pure, explainable prototype irrigation-need calculations.

This module deliberately stops at a read-only water-need preview. It does not
select water quality, allocate freshwater, create commands, or actuate hardware.
"""

from __future__ import annotations

from math import isfinite

from app.config import Settings, settings
from app.schemas import (
    IrrigationNeedPolicy,
    IrrigationNeedResult,
    IrrigationUrgencyComponents,
    WeatherState,
    ZoneState,
)


PROTOTYPE_VOLUME_WARNING = (
    "requested volume uses per-zone prototype field-response calibration and is not "
    "a universal farm-scale irrigation equation"
)


def irrigation_policy_from_settings(app_settings: Settings = settings) -> IrrigationNeedPolicy:
    """Create the validated, API-visible policy from environment-backed settings."""

    return IrrigationNeedPolicy(
        stale_telemetry_after_s=app_settings.irrigation_stale_telemetry_after_s,
        strong_rain_probability_pct=app_settings.irrigation_strong_rain_probability_pct,
        meaningful_rain_6h_mm=app_settings.irrigation_meaningful_rain_6h_mm,
        high_et0_6h_mm=app_settings.irrigation_high_et0_6h_mm,
        soil_deficit_weight=app_settings.irrigation_soil_deficit_weight,
        critical_moisture_boost=app_settings.irrigation_critical_moisture_boost,
        high_stage_sensitivity_boost=app_settings.irrigation_high_stage_sensitivity_boost,
        moderate_stage_sensitivity_boost=(
            app_settings.irrigation_moderate_stage_sensitivity_boost
        ),
        high_et0_boost=app_settings.irrigation_high_et0_boost,
    )


def base_water_need_ml(
    current_moisture_pct: float,
    target_moisture_pct: float,
    ml_per_moisture_point: float,
) -> tuple[float, float]:
    """Return moisture deficit and prototype water volume without hidden modifiers."""

    if not all(isfinite(value) for value in (current_moisture_pct, target_moisture_pct)):
        raise ValueError("moisture inputs must be finite")
    if not 0 <= current_moisture_pct <= 100 or not 0 <= target_moisture_pct <= 100:
        raise ValueError("moisture inputs must be between 0 and 100")
    if not isfinite(ml_per_moisture_point) or ml_per_moisture_point <= 0:
        raise ValueError("ml_per_moisture_point must be finite and positive")
    moisture_deficit_pct = max(0.0, target_moisture_pct - current_moisture_pct)
    return moisture_deficit_pct, moisture_deficit_pct * ml_per_moisture_point


def calculate_irrigation_need(
    zone: ZoneState,
    weather: WeatherState,
    policy: IrrigationNeedPolicy,
) -> IrrigationNeedResult:
    """Evaluate one immutable zone snapshot using deterministic transparent rules."""

    context = zone.crop_context
    parameters = zone.config.irrigation_parameters
    target = context.target_moisture_pct if context is not None else parameters.target_moisture_pct
    critical = (
        context.critical_moisture_pct
        if context is not None
        else parameters.critical_moisture_pct
    )
    calibration = parameters.ml_per_moisture_point
    weather_assistance_available = _rain_inputs_available(weather)

    config_codes: list[str] = []
    config_reasons: list[str] = []
    if not zone.config.enabled:
        config_codes.append("ZONE_DISABLED")
        config_reasons.append("zone configuration is disabled")
    if context is None or context.status != "READY":
        config_codes.append("CROP_CONTEXT_INVALID")
        context_status = context.status if context is not None else "missing"
        config_reasons.append(f"crop context is not ready: {context_status}")
    if target is None:
        config_codes.append("TARGET_MOISTURE_MISSING")
        config_reasons.append("target_moisture_pct is not configured for this zone")
    if critical is None:
        config_codes.append("CRITICAL_MOISTURE_MISSING")
        config_reasons.append("critical_moisture_pct is not configured for this zone")
    if calibration is None:
        config_codes.append("CALIBRATION_MISSING")
        config_reasons.append("ml_per_moisture_point prototype calibration is not configured")
    if config_reasons:
        return IrrigationNeedResult.model_validate(
            {
                **_common_result_fields(zone, weather, policy, weather_assistance_available),
                "status": "CONFIG_REQUIRED",
                "urgency": "blocked",
                "needs_irrigation": False,
                "actionable": False,
                "current_moisture_pct": zone.telemetry.soil_moisture_pct,
                "target_moisture_pct": target,
                "critical_moisture_pct": critical,
                "ml_per_moisture_point": calibration,
                "reason_codes": config_codes,
                "reasons": config_reasons,
            }
        )

    current = zone.telemetry.soil_moisture_pct
    sensor_codes: list[str] = []
    sensor_reasons: list[str] = []
    if current is None:
        sensor_codes.append("SOIL_SENSOR_MISSING")
        sensor_reasons.append("soil-moisture telemetry is unavailable")
    if (
        not zone.online
        or zone.telemetry_age_s is None
        or zone.telemetry_age_s > policy.stale_telemetry_after_s
    ):
        sensor_codes.append("TELEMETRY_STALE")
        sensor_reasons.append(
            "zone telemetry is offline, has unknown age, or exceeds the configured stale limit"
        )
    if sensor_reasons:
        return IrrigationNeedResult.model_validate(
            {
                **_common_result_fields(zone, weather, policy, weather_assistance_available),
                "status": "SENSOR_UNAVAILABLE",
                "urgency": "blocked",
                "needs_irrigation": False,
                "actionable": False,
                "current_moisture_pct": current,
                "target_moisture_pct": target,
                "critical_moisture_pct": critical,
                "ml_per_moisture_point": calibration,
                "reason_codes": sensor_codes,
                "reasons": sensor_reasons,
            }
        )

    # These values are proven non-null by the structured configuration/sensor checks above.
    assert current is not None
    assert target is not None
    assert critical is not None
    assert calibration is not None

    moisture_deficit, base_requested = base_water_need_ml(current, target, calibration)
    is_critical = current <= critical
    strong_rain_expected = _strong_meaningful_rain_expected(weather, policy)
    high_et0 = _high_et0(weather, policy)

    stage_component = 0.0
    stage_sensitivity = context.water_stress_sensitivity if context is not None else None
    if stage_sensitivity == "high":
        stage_component = policy.high_stage_sensitivity_boost
    elif stage_sensitivity == "moderate":
        stage_component = policy.moderate_stage_sensitivity_boost

    components = IrrigationUrgencyComponents(
        soil_deficit=round(
            min(1.0, moisture_deficit / target) * policy.soil_deficit_weight,
            6,
        ),
        critical_moisture=policy.critical_moisture_boost if is_critical else 0.0,
        stage_sensitivity=stage_component if moisture_deficit > 0 else 0.0,
        high_et0=policy.high_et0_boost if high_et0 and moisture_deficit > 0 else 0.0,
    )
    urgency_score = round(
        components.soil_deficit
        + components.critical_moisture
        + components.stage_sensitivity
        + components.high_et0,
        6,
    )

    reason_codes: list[str] = []
    reasons: list[str] = []
    warning_codes: list[str] = ["PROTOTYPE_VOLUME_CALIBRATION"]
    warnings: list[str] = [PROTOTYPE_VOLUME_WARNING]

    if current >= target:
        status = "NOT_NEEDED"
        urgency = "none"
        requested_water_ml = 0.0
        reason_codes.append("AT_OR_ABOVE_TARGET")
        reasons.append("soil moisture is at or above the configured target")
    elif is_critical:
        status = "CRITICAL"
        urgency = "high"
        requested_water_ml = base_requested
        reason_codes.append("AT_OR_BELOW_CRITICAL")
        reasons.append("soil moisture is at or below the configured critical threshold")
    elif strong_rain_expected:
        status = "DEFER_FOR_RAIN"
        urgency = "low"
        requested_water_ml = 0.0
        reason_codes.extend(("BELOW_TARGET", "RAIN_DEFERRED"))
        reasons.extend(
            (
                "soil moisture is below the configured target",
                "configured strong-rain probability and meaningful-precipitation thresholds are met",
            )
        )
    else:
        status = "NEEDED"
        urgency = "high" if stage_sensitivity == "high" or high_et0 else "moderate"
        requested_water_ml = base_requested
        reason_codes.append("BELOW_TARGET")
        reasons.append("soil moisture is below the configured target")

    stage_urgency_applied = moisture_deficit > 0 and stage_component > 0
    if stage_urgency_applied:
        reason_codes.append("SENSITIVE_STAGE")
        reasons.append(
            f"crop context reports {stage_sensitivity} water-stress sensitivity; "
            f"configured urgency boost is {stage_component:.3f}"
        )
    elif moisture_deficit > 0 and stage_sensitivity is None:
        warning_codes.append("STAGE_SENSITIVITY_UNAVAILABLE")
        warnings.append("crop-stage sensitivity is unavailable and adds no urgency")

    rain_deferral_applied = status == "DEFER_FOR_RAIN"
    if is_critical and strong_rain_expected:
        reason_codes.append("CRITICAL_OVERRIDES_RAIN")
        reasons.append("critical soil moisture takes priority over forecast rainfall")
    elif moisture_deficit > 0 and weather_assistance_available and not strong_rain_expected:
        reason_codes.append("NO_MEANINGFUL_RAIN")
        reasons.append("strong meaningful rainfall is not expected under the configured policy")

    et0_urgency_applied = high_et0 and moisture_deficit > 0
    if et0_urgency_applied:
        reason_codes.append("HIGH_ET0")
        reasons.append(
            f"six-hour ET0 meets the configured {policy.high_et0_6h_mm:.3f} mm "
            f"threshold; urgency boost is {policy.high_et0_boost:.3f}"
        )

    if not weather_assistance_available:
        warning_codes.append("WEATHER_ASSISTANCE_UNAVAILABLE")
        warnings.append(
            "rainfall assistance is unavailable or stale; result uses valid local soil and crop configuration"
        )

    return IrrigationNeedResult.model_validate(
        {
            **_common_result_fields(zone, weather, policy, weather_assistance_available),
            "status": status,
            "urgency": urgency,
            "urgency_score": urgency_score,
            "urgency_components": components,
            "needs_irrigation": status in {"NEEDED", "CRITICAL"},
            "actionable": status in {"NEEDED", "CRITICAL"},
            "current_moisture_pct": current,
            "target_moisture_pct": target,
            "critical_moisture_pct": critical,
            "moisture_deficit_pct": moisture_deficit,
            "ml_per_moisture_point": calibration,
            "base_requested_ml": base_requested,
            "requested_water_ml": requested_water_ml,
            "rain_deferral_applied": rain_deferral_applied,
            "et0_urgency_applied": et0_urgency_applied,
            "stage_urgency_applied": stage_urgency_applied,
            "reason_codes": reason_codes,
            "reasons": reasons,
            "warning_codes": warning_codes,
            "warnings": warnings,
        }
    )


def _common_result_fields(
    zone: ZoneState,
    weather: WeatherState,
    policy: IrrigationNeedPolicy,
    weather_assistance_available: bool,
) -> dict[str, object]:
    context = zone.crop_context
    return {
        "zone_id": zone.zone_id,
        "telemetry_age_s": zone.telemetry_age_s,
        "crop_context_status": context.status if context is not None else None,
        "growth_stage": context.growth_stage if context is not None else None,
        "stage_sensitivity": (
            context.water_stress_sensitivity if context is not None else None
        ),
        "weather_status": weather.status,
        "weather_assistance_available": weather_assistance_available,
        "policy": policy,
    }


def _rain_inputs_available(weather: WeatherState) -> bool:
    return (
        weather.status != "OFFLINE"
        and not weather.stale
        and weather.rain_probability_6h_pct is not None
        and weather.rain_6h_mm is not None
    )


def _strong_meaningful_rain_expected(
    weather: WeatherState,
    policy: IrrigationNeedPolicy,
) -> bool:
    return (
        _rain_inputs_available(weather)
        and weather.rain_probability_6h_pct >= policy.strong_rain_probability_pct
        and weather.rain_6h_mm >= policy.meaningful_rain_6h_mm
    )


def _high_et0(weather: WeatherState, policy: IrrigationNeedPolicy) -> bool:
    return (
        weather.status != "OFFLINE"
        and not weather.stale
        and weather.et0_6h_mm is not None
        and weather.et0_6h_mm >= policy.high_et0_6h_mm
    )


irrigation_need_policy = irrigation_policy_from_settings()
