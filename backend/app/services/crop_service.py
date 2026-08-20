"""Source-backed crop profiles and deterministic growth-stage derivation."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from app.schemas import CropContext, CropProfile, CropStageProfile, ZoneConfig


CROP_PROFILES_PATH = Path(__file__).resolve().parents[1] / "data" / "crop_profiles.json"


class UnknownCropError(ValueError):
    """Raised when a configured crop ID is absent from the canonical database."""


class FutureSowingDateError(ValueError):
    """Raised when a zone has a sowing date later than the evaluation date."""


class CropProfileDocumentError(ValueError):
    """Raised when the crop profile document is structurally invalid."""


class CropService:
    """Load crop evidence once and derive immutable, zone-specific contexts."""

    def __init__(self, profile_path: Path = CROP_PROFILES_PATH) -> None:
        document: dict[str, Any] = json.loads(profile_path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "1.0":
            raise CropProfileDocumentError("unsupported crop profile schema_version")

        profiles = TypeAdapter(tuple[CropProfile, ...]).validate_python(document.get("profiles"))
        self._profiles: dict[str, CropProfile] = {}
        for profile in profiles:
            if profile.crop_id in self._profiles:
                raise CropProfileDocumentError(f"duplicate crop profile id: {profile.crop_id}")
            self._profiles[profile.crop_id] = profile

    def list_profiles(self) -> tuple[CropProfile, ...]:
        return tuple(profile.model_copy(deep=True) for profile in self._profiles.values())

    def get_profile(self, crop_id: str) -> CropProfile:
        try:
            return self._profiles[crop_id].model_copy(deep=True)
        except KeyError as error:
            raise UnknownCropError(f"unknown crop_id: {crop_id}") from error

    def derive_context(self, config: ZoneConfig, *, on_date: date | None = None) -> CropContext:
        evaluation_date = on_date or date.today()
        days_after_sowing = self._days_after_sowing(config.sowing_date, evaluation_date)
        if config.crop_id is None:
            return CropContext(
                zone_id=config.zone_id,
                sowing_date=config.sowing_date,
                days_after_sowing=days_after_sowing,
                status="CROP_UNCONFIGURED",
                warnings=("crop_id is not configured",),
            )

        profile = self.get_profile(config.crop_id)
        source_ids = tuple(source.source_id for source in profile.sources)

        if config.growth_stage_mode == "MANUAL":
            stage_name = config.manual_growth_stage
            stage = self._find_stage(profile, stage_name)
            warnings: tuple[str, ...] = ()
            if stage is None:
                warnings = ("manual growth stage is not defined in the crop profile",)
            return self._context(
                config,
                profile,
                days_after_sowing=days_after_sowing,
                stage_name=stage_name,
                stage=stage,
                stage_source="MANUAL",
                status="READY",
                source_ids=source_ids,
                warnings=warnings,
            )

        if config.sowing_date is None:
            return self._context(
                config,
                profile,
                days_after_sowing=None,
                stage_name=None,
                stage=None,
                stage_source=None,
                status="SOWING_DATE_MISSING",
                source_ids=source_ids,
                warnings=("automatic growth-stage estimation requires sowing_date",),
            )

        stage = self._stage_for_day(profile, days_after_sowing)
        if stage is None:
            return self._context(
                config,
                profile,
                days_after_sowing=days_after_sowing,
                stage_name=None,
                stage=None,
                stage_source="AUTO",
                status="OUTSIDE_REFERENCE_CALENDAR",
                source_ids=source_ids,
                warnings=("days after sowing are outside the source-backed stage calendar",),
            )

        return self._context(
            config,
            profile,
            days_after_sowing=days_after_sowing,
            stage_name=stage.stage_id,
            stage=stage,
            stage_source="AUTO",
            status="READY",
            source_ids=source_ids,
            warnings=(),
        )

    @staticmethod
    def _days_after_sowing(sowing_date: date | None, evaluation_date: date) -> int | None:
        if sowing_date is None:
            return None
        days = (evaluation_date - sowing_date).days
        if days < 0:
            raise FutureSowingDateError("sowing_date cannot be in the future")
        return days

    @staticmethod
    def _stage_for_day(profile: CropProfile, days_after_sowing: int | None) -> CropStageProfile | None:
        if days_after_sowing is None:
            return None
        return next(
            (
                stage
                for stage in profile.stages
                if stage.start_day is not None
                and stage.end_day is not None
                and stage.start_day <= days_after_sowing <= stage.end_day
            ),
            None,
        )

    @staticmethod
    def _find_stage(profile: CropProfile, stage_name: str | None) -> CropStageProfile | None:
        if stage_name is None:
            return None
        normalized = stage_name.strip().casefold()
        return next(
            (
                stage
                for stage in profile.stages
                if normalized in {stage.stage_id.casefold(), stage.name.casefold()}
            ),
            None,
        )

    @staticmethod
    def _context(
        config: ZoneConfig,
        profile: CropProfile,
        *,
        days_after_sowing: int | None,
        stage_name: str | None,
        stage: CropStageProfile | None,
        stage_source: str | None,
        status: str,
        source_ids: tuple[str, ...],
        warnings: tuple[str, ...],
    ) -> CropContext:
        return CropContext.model_validate(
            {
                "zone_id": config.zone_id,
                "crop_id": profile.crop_id,
                "crop_name": profile.display_name,
                "sowing_date": config.sowing_date,
                "days_after_sowing": days_after_sowing,
                "growth_stage": stage_name,
                "stage_source": stage_source,
                "status": status,
                "crop_coefficient_kc": stage.crop_coefficient_kc if stage else None,
                "water_stress_sensitivity": stage.water_stress_sensitivity if stage else None,
                "target_moisture_pct": profile.moisture.target_moisture_pct,
                "critical_moisture_pct": profile.moisture.critical_moisture_pct,
                "max_irrigation_tds_ppm": profile.salinity.max_irrigation_tds_ppm,
                "source_ids": source_ids,
                "warnings": warnings,
            }
        )


crop_service = CropService()
