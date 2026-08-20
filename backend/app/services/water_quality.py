"""Pure single-zone TDS strategy calculations with no actuation or allocation."""

from __future__ import annotations

from math import floor, isfinite

from app.config import Settings, settings
from app.schemas import (
    WaterQualityPolicy,
    WaterQualityResult,
    WaterSourceState,
    ZoneId,
)


PHYSICAL_VERIFICATION_WARNING = (
    "predicted TDS is not a measured final value and must later be verified by the "
    "physical post-mix sensor"
)
TDS_PROXY_WARNING = (
    "TDS is an incoming-water quality proxy and does not prove long-term root-zone salinity safety"
)


def water_quality_policy_from_settings(
    app_settings: Settings = settings,
) -> WaterQualityPolicy:
    return WaterQualityPolicy(
        tds_safety_margin_ppm=app_settings.tds_safety_margin_ppm,
        source_stale_after_s=app_settings.tds_source_stale_minutes * 60,
        volume_rounding_decimals=app_settings.tds_volume_rounding_decimals,
        volume_tolerance_ml=app_settings.tds_volume_tolerance_ml,
        predicted_tds_tolerance_ppm=app_settings.tds_prediction_tolerance_ppm,
    )


def predicted_blend_tds_ppm(
    fresh_ml: float,
    fresh_tds_ppm: float,
    marginal_ml: float,
    marginal_tds_ppm: float,
) -> float:
    """Calculate volume-weighted predicted TDS for positive total volume."""

    values = (fresh_ml, fresh_tds_ppm, marginal_ml, marginal_tds_ppm)
    if not all(isfinite(value) for value in values):
        raise ValueError("blend inputs must be finite")
    if fresh_ml < 0 or marginal_ml < 0:
        raise ValueError("source volumes cannot be negative")
    if fresh_tds_ppm < 0 or marginal_tds_ppm < 0:
        raise ValueError("source TDS cannot be negative")
    total_ml = fresh_ml + marginal_ml
    if total_ml <= 0:
        raise ValueError("predicted blend requires positive total volume")
    return (
        fresh_ml * fresh_tds_ppm + marginal_ml * marginal_tds_ppm
    ) / total_ml


def calculate_water_quality_strategy(
    *,
    zone_id: ZoneId,
    requested_water_ml: float | None,
    fresh_source: WaterSourceState,
    marginal_source: WaterSourceState,
    configured_max_tds_ppm: float | None,
    policy: WaterQualityPolicy,
) -> WaterQualityResult:
    """Choose the safest quality strategy for one zone without allocating shared water."""

    if requested_water_ml is None:
        return _result(
            zone_id=zone_id,
            strategy="CONFIG_REQUIRED",
            requested_water_ml=None,
            fresh_source=fresh_source,
            marginal_source=marginal_source,
            configured_max_tds_ppm=configured_max_tds_ppm,
            safety_target_tds_ppm=None,
            policy=policy,
            reason_codes=["IRRIGATION_REQUEST_UNAVAILABLE"],
            reasons=["Milestone 4 did not produce an actionable irrigation-water request"],
        )
    if not isfinite(requested_water_ml) or requested_water_ml < 0:
        raise ValueError("requested_water_ml must be finite and non-negative")
    if requested_water_ml == 0:
        return _result(
            zone_id=zone_id,
            strategy="NO_IRRIGATION_REQUEST",
            requested_water_ml=0.0,
            fresh_source=fresh_source,
            marginal_source=marginal_source,
            configured_max_tds_ppm=configured_max_tds_ppm,
            safety_target_tds_ppm=None,
            policy=policy,
            fresh_ml=0.0,
            marginal_ml=0.0,
            reason_codes=["NO_IRRIGATION_REQUEST"],
            reasons=["the current irrigation-need preview requests zero water"],
        )

    if configured_max_tds_ppm is None:
        return _result(
            zone_id=zone_id,
            strategy="CONFIG_REQUIRED",
            requested_water_ml=requested_water_ml,
            fresh_source=fresh_source,
            marginal_source=marginal_source,
            configured_max_tds_ppm=None,
            safety_target_tds_ppm=None,
            policy=policy,
            reason_codes=["CROP_TDS_LIMIT_MISSING"],
            reasons=["max_irrigation_tds_ppm is not configured for this zone"],
        )
    if not isfinite(configured_max_tds_ppm) or configured_max_tds_ppm <= 0:
        raise ValueError("configured_max_tds_ppm must be finite and positive")
    if policy.tds_safety_margin_ppm is None:
        return _result(
            zone_id=zone_id,
            strategy="CONFIG_REQUIRED",
            requested_water_ml=requested_water_ml,
            fresh_source=fresh_source,
            marginal_source=marginal_source,
            configured_max_tds_ppm=configured_max_tds_ppm,
            safety_target_tds_ppm=None,
            policy=policy,
            reason_codes=["SAFETY_MARGIN_MISSING"],
            reasons=["TDS safety margin is not configured"],
        )

    safety_target = configured_max_tds_ppm - policy.tds_safety_margin_ppm
    if safety_target <= 0:
        return _result(
            zone_id=zone_id,
            strategy="NOT_FEASIBLE",
            requested_water_ml=requested_water_ml,
            fresh_source=fresh_source,
            marginal_source=marginal_source,
            configured_max_tds_ppm=configured_max_tds_ppm,
            safety_target_tds_ppm=None,
            policy=policy,
            reason_codes=["SAFETY_TARGET_INVALID"],
            reasons=[
                "configured TDS safety margin is greater than or equal to the crop maximum"
            ],
        )

    source_codes: list[str] = []
    source_reasons: list[str] = []
    if not _source_quality_usable(fresh_source, policy):
        source_codes.append("FRESH_TDS_UNKNOWN")
        source_reasons.append("fresh source TDS is missing, stale, invalid, or unusable")
    if not _source_quality_usable(marginal_source, policy):
        source_codes.append("MARGINAL_TDS_UNKNOWN")
        source_reasons.append("marginal source TDS is missing, stale, invalid, or unusable")
    if fresh_source.quality_status == "STALE" or marginal_source.quality_status == "STALE":
        source_codes.append("SOURCE_QUALITY_STALE")
        source_reasons.append("at least one source-quality measurement is explicitly stale")
    if source_codes:
        return _result(
            zone_id=zone_id,
            strategy="SOURCE_QUALITY_UNKNOWN",
            requested_water_ml=requested_water_ml,
            fresh_source=fresh_source,
            marginal_source=marginal_source,
            configured_max_tds_ppm=configured_max_tds_ppm,
            safety_target_tds_ppm=safety_target,
            policy=policy,
            reason_codes=source_codes,
            reasons=source_reasons,
        )

    fresh_tds = fresh_source.tds_ppm
    marginal_tds = marginal_source.tds_ppm
    assert fresh_tds is not None
    assert marginal_tds is not None
    tolerance = policy.predicted_tds_tolerance_ppm

    if fresh_tds > marginal_tds + tolerance:
        return _result(
            zone_id=zone_id,
            strategy="NOT_FEASIBLE",
            requested_water_ml=requested_water_ml,
            fresh_source=fresh_source,
            marginal_source=marginal_source,
            configured_max_tds_ppm=configured_max_tds_ppm,
            safety_target_tds_ppm=safety_target,
            policy=policy,
            reason_codes=["SOURCE_ORDER_ANOMALY"],
            reasons=[
                "the source labelled fresh has higher measured TDS than the source labelled marginal"
            ],
            warning_codes=["SOURCE_LABEL_ORDER_ANOMALY"],
            warnings=["source labels and measured quality conflict; no strategy is selected silently"],
        )

    equal_sources = abs(fresh_tds - marginal_tds) <= tolerance
    if marginal_tds <= safety_target + tolerance:
        codes = ["MARGINAL_WITHIN_TARGET"]
        reasons = ["marginal source TDS is at or below the configured safety target"]
        if equal_sources:
            codes.insert(0, "EQUAL_SOURCE_TDS")
            reasons.insert(0, "fresh and marginal source TDS values are equal within tolerance")
        return _safe_result(
            zone_id=zone_id,
            strategy="MARGINAL_ONLY",
            requested_water_ml=requested_water_ml,
            fresh_ml=0.0,
            marginal_ml=requested_water_ml,
            fresh_source=fresh_source,
            marginal_source=marginal_source,
            configured_max_tds_ppm=configured_max_tds_ppm,
            safety_target_tds_ppm=safety_target,
            predicted_tds_ppm=marginal_tds,
            policy=policy,
            reason_codes=codes,
            reasons=reasons,
        )

    if equal_sources:
        return _result(
            zone_id=zone_id,
            strategy="NOT_FEASIBLE",
            requested_water_ml=requested_water_ml,
            fresh_source=fresh_source,
            marginal_source=marginal_source,
            configured_max_tds_ppm=configured_max_tds_ppm,
            safety_target_tds_ppm=safety_target,
            policy=policy,
            reason_codes=["EQUAL_SOURCE_TDS", "NO_SOURCE_MEETS_TARGET"],
            reasons=[
                "fresh and marginal source TDS values are equal within tolerance",
                "both source TDS values exceed the configured safety target",
            ],
        )

    if fresh_tds > safety_target + tolerance:
        return _result(
            zone_id=zone_id,
            strategy="NOT_FEASIBLE",
            requested_water_ml=requested_water_ml,
            fresh_source=fresh_source,
            marginal_source=marginal_source,
            configured_max_tds_ppm=configured_max_tds_ppm,
            safety_target_tds_ppm=safety_target,
            policy=policy,
            reason_codes=["NO_SOURCE_MEETS_TARGET"],
            reasons=["even the lower-TDS fresh source exceeds the configured safety target"],
        )

    if fresh_tds >= safety_target - tolerance:
        return _safe_result(
            zone_id=zone_id,
            strategy="FRESH_ONLY",
            requested_water_ml=requested_water_ml,
            fresh_ml=requested_water_ml,
            marginal_ml=0.0,
            fresh_source=fresh_source,
            marginal_source=marginal_source,
            configured_max_tds_ppm=configured_max_tds_ppm,
            safety_target_tds_ppm=safety_target,
            predicted_tds_ppm=fresh_tds,
            policy=policy,
            reason_codes=["MARGINAL_EXCEEDS_TARGET", "FRESH_ONLY_SAFE"],
            reasons=[
                "marginal source TDS exceeds the configured safety target",
                "fresh source is acceptable but no marginal fraction can be added safely within tolerance",
            ],
        )

    marginal_fraction = (safety_target - fresh_tds) / (marginal_tds - fresh_tds)
    marginal_fraction = min(1.0, max(0.0, marginal_fraction))
    scale = 10**policy.volume_rounding_decimals
    marginal_ml = floor(requested_water_ml * marginal_fraction * scale) / scale
    fresh_ml = requested_water_ml - marginal_ml

    if marginal_ml <= policy.volume_tolerance_ml:
        return _safe_result(
            zone_id=zone_id,
            strategy="FRESH_ONLY",
            requested_water_ml=requested_water_ml,
            fresh_ml=requested_water_ml,
            marginal_ml=0.0,
            fresh_source=fresh_source,
            marginal_source=marginal_source,
            configured_max_tds_ppm=configured_max_tds_ppm,
            safety_target_tds_ppm=safety_target,
            predicted_tds_ppm=fresh_tds,
            policy=policy,
            reason_codes=["MARGINAL_EXCEEDS_TARGET", "FRESH_ONLY_SAFE"],
            reasons=[
                "marginal source TDS exceeds the configured safety target",
                "the safe marginal volume is below the configured volume tolerance",
            ],
        )

    predicted_tds = predicted_blend_tds_ppm(
        fresh_ml,
        fresh_tds,
        marginal_ml,
        marginal_tds,
    )
    if predicted_tds > safety_target + tolerance:
        quantum = 1 / scale
        marginal_ml = max(0.0, marginal_ml - quantum)
        fresh_ml = requested_water_ml - marginal_ml
        predicted_tds = predicted_blend_tds_ppm(
            fresh_ml,
            fresh_tds,
            marginal_ml,
            marginal_tds,
        )

    return _safe_result(
        zone_id=zone_id,
        strategy="CONTROLLED_BLEND",
        requested_water_ml=requested_water_ml,
        fresh_ml=fresh_ml,
        marginal_ml=marginal_ml,
        fresh_source=fresh_source,
        marginal_source=marginal_source,
        configured_max_tds_ppm=configured_max_tds_ppm,
        safety_target_tds_ppm=safety_target,
        predicted_tds_ppm=predicted_tds,
        policy=policy,
        reason_codes=[
            "MARGINAL_EXCEEDS_TARGET",
            "CONTROLLED_BLEND_SAFE",
            "MAXIMIZED_MARGINAL_FRACTION",
        ],
        reasons=[
            "marginal source TDS exceeds the configured safety target",
            "fresh and marginal source water can form a predicted blend within the safety target",
            "marginal-water fraction is maximized conservatively within rounding tolerance",
        ],
    )


def _source_quality_usable(source: WaterSourceState, policy: WaterQualityPolicy) -> bool:
    if source.tds_ppm is None or source.quality_status in {"UNKNOWN", "INVALID", "STALE"}:
        return False
    if source.quality_status == "SIMULATED":
        return True
    return (
        source.quality_status == "MEASURED"
        and source.measurement_age_s is not None
        and source.measurement_age_s <= policy.source_stale_after_s
    )


def _safe_result(
    *,
    zone_id: ZoneId,
    strategy: str,
    requested_water_ml: float,
    fresh_ml: float,
    marginal_ml: float,
    fresh_source: WaterSourceState,
    marginal_source: WaterSourceState,
    configured_max_tds_ppm: float,
    safety_target_tds_ppm: float,
    predicted_tds_ppm: float,
    policy: WaterQualityPolicy,
    reason_codes: list[str],
    reasons: list[str],
) -> WaterQualityResult:
    source_volume_sufficient, availability_code, availability_reason = (
        _source_volume_sufficiency(
            fresh_ml,
            marginal_ml,
            fresh_source,
            marginal_source,
        )
    )
    reason_codes = [*reason_codes, availability_code]
    reasons = [*reasons, availability_reason]
    warning_codes = [
        "PREDICTION_REQUIRES_PHYSICAL_VERIFICATION",
        "TDS_IS_QUALITY_PROXY",
    ]
    warnings = [PHYSICAL_VERIFICATION_WARNING, TDS_PROXY_WARNING]
    if source_volume_sufficient is None:
        warning_codes.append("SOURCE_AVAILABILITY_UNKNOWN")
        warnings.append("source availability is unknown; current satisfiability cannot be confirmed")
    elif not source_volume_sufficient:
        warning_codes.append("SOURCE_VOLUME_INSUFFICIENT")
        warnings.append(
            "the single-zone quality strategy is valid but current source volume is insufficient"
        )

    total = fresh_ml + marginal_ml
    return _result(
        zone_id=zone_id,
        strategy=strategy,
        requested_water_ml=requested_water_ml,
        fresh_source=fresh_source,
        marginal_source=marginal_source,
        configured_max_tds_ppm=configured_max_tds_ppm,
        safety_target_tds_ppm=safety_target_tds_ppm,
        policy=policy,
        fresh_ml=fresh_ml,
        marginal_ml=marginal_ml,
        fresh_fraction=fresh_ml / total,
        marginal_fraction=marginal_ml / total,
        predicted_tds_ppm=predicted_tds_ppm,
        safe=True,
        physical_verification_required=True,
        source_volume_sufficient=source_volume_sufficient,
        currently_satisfiable=source_volume_sufficient is True,
        reason_codes=reason_codes,
        reasons=reasons,
        warning_codes=warning_codes,
        warnings=warnings,
    )


def _source_volume_sufficiency(
    fresh_ml: float,
    marginal_ml: float,
    fresh_source: WaterSourceState,
    marginal_source: WaterSourceState,
) -> tuple[bool | None, str, str]:
    required_sources = []
    if fresh_ml > 0:
        required_sources.append((fresh_ml, fresh_source.available_l))
    if marginal_ml > 0:
        required_sources.append((marginal_ml, marginal_source.available_l))
    if any(available_l is None for _, available_l in required_sources):
        return None, "SOURCE_VOLUME_UNKNOWN", "required source availability is unknown"
    sufficient = all(
        available_l is not None and available_l * 1000 >= required_ml
        for required_ml, available_l in required_sources
    )
    if sufficient:
        return True, "SOURCE_VOLUME_SUFFICIENT", "current source volumes satisfy this single-zone preview"
    return False, "SOURCE_VOLUME_INSUFFICIENT", "current source volumes cannot satisfy this single-zone preview"


def _result(
    *,
    zone_id: ZoneId,
    strategy: str,
    requested_water_ml: float | None,
    fresh_source: WaterSourceState,
    marginal_source: WaterSourceState,
    configured_max_tds_ppm: float | None,
    safety_target_tds_ppm: float | None,
    policy: WaterQualityPolicy,
    reason_codes: list[str],
    reasons: list[str],
    fresh_ml: float | None = None,
    marginal_ml: float | None = None,
    fresh_fraction: float | None = None,
    marginal_fraction: float | None = None,
    predicted_tds_ppm: float | None = None,
    safe: bool = False,
    physical_verification_required: bool = False,
    source_volume_sufficient: bool | None = None,
    currently_satisfiable: bool = False,
    warning_codes: list[str] | None = None,
    warnings: list[str] | None = None,
) -> WaterQualityResult:
    return WaterQualityResult.model_validate(
        {
            "zone_id": zone_id,
            "strategy": strategy,
            "requested_water_ml": requested_water_ml,
            "fresh_ml": fresh_ml,
            "marginal_ml": marginal_ml,
            "fresh_fraction": fresh_fraction,
            "marginal_fraction": marginal_fraction,
            "fresh_tds_ppm": fresh_source.tds_ppm,
            "marginal_tds_ppm": marginal_source.tds_ppm,
            "configured_max_tds_ppm": configured_max_tds_ppm,
            "safety_margin_ppm": policy.tds_safety_margin_ppm,
            "safety_target_tds_ppm": safety_target_tds_ppm,
            "predicted_tds_ppm": predicted_tds_ppm,
            "measured_tds_ppm": None,
            "safe": safe,
            "physical_verification_required": physical_verification_required,
            "fresh_available_ml": _available_ml(fresh_source),
            "marginal_available_ml": _available_ml(marginal_source),
            "source_volume_sufficient": source_volume_sufficient,
            "currently_satisfiable": currently_satisfiable,
            "policy": policy,
            "reason_codes": reason_codes,
            "reasons": reasons,
            "warning_codes": warning_codes or [],
            "warnings": warnings or [],
        }
    )


def _available_ml(source: WaterSourceState) -> float | None:
    return source.available_l * 1000 if source.available_l is not None else None


water_quality_policy = water_quality_policy_from_settings()
