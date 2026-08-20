from datetime import date

import pytest

from app.schemas import CropContext, ZoneConfig, ZoneState
from pydantic import ValidationError
from app.services.crop_service import CropService, FutureSowingDateError, UnknownCropError
from app.state import ApplicationStateStore


EVALUATION_DATE = date(2026, 8, 20)


def tomato_config(*, sowing_date: date, mode: str = "AUTO", manual: str | None = None) -> ZoneConfig:
    return ZoneConfig.model_validate(
        {
            "zone_id": "A",
            "name": "Zone A",
            "crop_id": "tomato",
            "sowing_date": sowing_date,
            "growth_stage_mode": mode,
            "manual_growth_stage": manual,
        }
    )


def test_crop_database_is_valid_source_backed_and_non_fabricated() -> None:
    profiles = CropService().list_profiles()

    assert {profile.crop_id for profile in profiles} == {"tomato", "chilli", "okra"}
    assert all(profile.sources for profile in profiles)
    assert all(source.url.startswith("https://") for profile in profiles for source in profile.sources)
    assert all(profile.moisture.target_moisture_pct is None for profile in profiles)
    assert all(profile.moisture.critical_moisture_pct is None for profile in profiles)
    assert all(profile.salinity.max_irrigation_tds_ppm is None for profile in profiles)


def test_unknown_crop_is_rejected() -> None:
    with pytest.raises(UnknownCropError, match="unknown crop_id"):
        CropService().get_profile("dragon-fruit")


def test_days_after_sowing_is_calendar_day_difference() -> None:
    context = CropService().derive_context(
        tomato_config(sowing_date=date(2026, 8, 10)),
        on_date=EVALUATION_DATE,
    )

    assert context.days_after_sowing == 10
    assert context.sowing_date == date(2026, 8, 10)


@pytest.mark.parametrize(
    ("days_after_sowing", "expected_stage"),
    [
        (0, "initial"),
        (29, "initial"),
        (30, "development"),
        (69, "development"),
        (70, "mid_season"),
        (114, "mid_season"),
        (115, "late_season"),
        (144, "late_season"),
    ],
)
def test_stage_boundaries_are_inclusive_and_contiguous(
    days_after_sowing: int, expected_stage: str
) -> None:
    context = CropService().derive_context(
        tomato_config(sowing_date=EVALUATION_DATE.fromordinal(EVALUATION_DATE.toordinal() - days_after_sowing)),
        on_date=EVALUATION_DATE,
    )

    assert context.status == "READY"
    assert context.growth_stage == expected_stage
    assert context.stage_source == "AUTO"


def test_days_beyond_sourced_calendar_are_not_guessed() -> None:
    context = CropService().derive_context(
        tomato_config(sowing_date=date(2026, 3, 28)),
        on_date=EVALUATION_DATE,
    )

    assert context.days_after_sowing == 145
    assert context.status == "OUTSIDE_REFERENCE_CALENDAR"
    assert context.growth_stage is None
    assert context.crop_coefficient_kc is None


def test_manual_stage_override_wins_over_sowing_date_estimate() -> None:
    context = CropService().derive_context(
        tomato_config(
            sowing_date=date(2026, 8, 10),
            mode="MANUAL",
            manual="mid_season",
        ),
        on_date=EVALUATION_DATE,
    )

    assert context.days_after_sowing == 10
    assert context.growth_stage == "mid_season"
    assert context.stage_source == "MANUAL"
    assert context.crop_coefficient_kc == 1.15
    assert context.water_stress_sensitivity == "high"


def test_unmapped_manual_stage_is_preserved_without_inventing_stage_values() -> None:
    context = CropService().derive_context(
        tomato_config(
            sowing_date=date(2026, 8, 10),
            mode="MANUAL",
            manual="farmer-observed flowering",
        ),
        on_date=EVALUATION_DATE,
    )

    assert context.status == "READY"
    assert context.growth_stage == "farmer-observed flowering"
    assert context.crop_coefficient_kc is None
    assert context.water_stress_sensitivity is None
    assert context.warnings


def test_future_sowing_date_is_rejected() -> None:
    with pytest.raises(FutureSowingDateError, match="future"):
        CropService().derive_context(
            tomato_config(sowing_date=date(2026, 8, 21)),
            on_date=EVALUATION_DATE,
        )


def test_future_sowing_date_is_rejected_even_without_a_crop() -> None:
    config = ZoneConfig(
        zone_id="A",
        name="Zone A",
        crop_id=None,
        sowing_date=date(2026, 8, 21),
    )

    with pytest.raises(FutureSowingDateError, match="future"):
        CropService().derive_context(config, on_date=EVALUATION_DATE)


def test_auto_stage_requires_sowing_date_but_does_not_fabricate_it() -> None:
    config = tomato_config(sowing_date=EVALUATION_DATE).model_copy(update={"sowing_date": None})
    context = CropService().derive_context(config, on_date=EVALUATION_DATE)

    assert context.status == "SOWING_DATE_MISSING"
    assert context.days_after_sowing is None
    assert context.growth_stage is None


def test_zone_crop_context_updates_are_isolated() -> None:
    store = ApplicationStateStore(today_provider=lambda: EVALUATION_DATE)
    zone_b_before = store.get_zone("B")
    config = tomato_config(sowing_date=date(2026, 8, 20))

    updated = store.update_zone_config("A", config)

    assert updated.crop_context is not None
    assert updated.crop_context.days_after_sowing == 0
    assert updated.crop_context.growth_stage == "initial"
    assert store.get_zone("B") == zone_b_before


def test_zone_schema_rejects_crop_context_from_another_zone() -> None:
    store = ApplicationStateStore(today_provider=lambda: EVALUATION_DATE)
    zone_a = store.get_zone("A")
    assert zone_a.crop_context is not None
    wrong_context = CropContext.model_validate(
        {**zone_a.crop_context.model_dump(), "zone_id": "B"}
    )

    with pytest.raises(ValidationError, match="crop context does not match"):
        ZoneState.model_validate(
            {**zone_a.model_dump(), "crop_context": wrong_context}
        )
