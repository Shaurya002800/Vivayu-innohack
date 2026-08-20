from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.schemas import VivayuSensorConfiguration, ZoneTelemetry
from app.services.vivayu_health_service import VivayuHealthService


COMPATIBLE = VivayuSensorConfiguration(
    environment_sensor="BME680",
    voc_sensor="SGP40_COMPATIBLE",
)


def telemetry(
    zone_id: str = "A",
    *,
    sequence: int = 1,
    gas_resistance_ohm: float | None = 40_000.0,
    sraw: int | None = 29_000,
) -> ZoneTelemetry:
    return ZoneTelemetry(
        zone_id=zone_id,
        timestamp_ms=1_000 + sequence,
        temperature_c=30.0,
        humidity_pct=60.0,
        pressure_pa=97_000.0,
        gas_resistance_ohm=gas_resistance_ohm,
        sraw=sraw,
        received_at=(
            datetime(2026, 8, 21, tzinfo=timezone.utc)
            + timedelta(seconds=sequence)
        ),
    )


def add(
    service: VivayuHealthService,
    zone_id: str,
    reading: ZoneTelemetry,
    config: VivayuSensorConfiguration = COMPATIBLE,
):
    return service.add_zone_reading(
        zone_id,
        reading,
        config,
        data_mode="simulation",
    )


def test_valid_legacy_reading_enters_collecting_window() -> None:
    service = VivayuHealthService()

    health = add(service, "A", telemetry())

    assert health.status == "COLLECTING"
    assert health.available is True
    assert health.readings_received == 1
    assert health.readings_required == 5
    assert health.readings_in_window == 1
    assert health.model_name == "gas_threshold"
    assert health.source_mode == "SIMULATION"


def test_first_four_readings_report_exact_collecting_progress() -> None:
    service = VivayuHealthService()

    states = [add(service, "A", telemetry(sequence=index)) for index in range(1, 5)]

    assert [state.status for state in states] == ["COLLECTING"] * 4
    assert [state.readings_received for state in states] == [1, 2, 3, 4]
    assert [state.reason for state in states] == [
        "collecting compatible readings: 1/5",
        "collecting compatible readings: 2/5",
        "collecting compatible readings: 3/5",
        "collecting compatible readings: 4/5",
    ]


def test_fifth_reading_returns_pinned_research_result() -> None:
    service = VivayuHealthService()

    for index in range(1, 6):
        health = add(service, "A", telemetry(sequence=index))

    assert health.status == "READY"
    assert health.pattern == "elevated_voc_pattern"
    assert health.risk_level == "high"
    assert health.research_score == pytest.approx(0.9982)
    assert health.confidence_pct == pytest.approx(99.6)
    assert health.confidence_note == (
        "Decision separation only; not calibrated field confidence."
    )
    assert health.research_only is True
    assert health.readings_in_window == 5
    assert "disease_pattern_probability" not in health.model_dump()
    assert "not a diagnosis or irrigation trigger" in health.warnings[0]


def test_sixth_reading_rolls_window_without_growing_it() -> None:
    service = VivayuHealthService()
    for index in range(1, 6):
        first = add(service, "A", telemetry(sequence=index))
    assert first.research_score is not None

    sixth = add(
        service,
        "A",
        telemetry(sequence=6, gas_resistance_ohm=200_000.0),
    )

    assert sixth.status == "READY"
    assert sixth.readings_in_window == 5
    assert sixth.readings_received == 5
    assert sixth.research_score is not None
    assert sixth.research_score < first.research_score


def test_zone_a_and_b_predictor_windows_are_independent() -> None:
    service = VivayuHealthService()
    for index in range(1, 5):
        add(service, "A", telemetry("A", sequence=index))
    for index in range(1, 3):
        add(service, "B", telemetry("B", sequence=index))

    assert service.get_zone_health("A").readings_in_window == 4
    assert service.get_zone_health("B").readings_in_window == 2
    assert service.get_zone_health("A").status == "COLLECTING"
    assert service.get_zone_health("B").status == "COLLECTING"


def test_resetting_zone_a_does_not_reset_zone_b() -> None:
    service = VivayuHealthService()
    for index in range(1, 4):
        add(service, "A", telemetry("A", sequence=index))
        add(service, "B", telemetry("B", sequence=index))

    reset_a = service.reset_zone_predictor("A")

    assert reset_a.readings_in_window == 0
    assert reset_a.reason_code == "PREDICTOR_RESET"
    assert service.get_zone_health("B").readings_in_window == 3


def test_missing_bme680_gas_resistance_is_unavailable_without_buffering() -> None:
    service = VivayuHealthService()

    health = add(
        service,
        "A",
        telemetry(gas_resistance_ohm=None),
    )

    assert health.status == "UNAVAILABLE"
    assert health.reason_code == "BME680_GAS_RESISTANCE_CHANNEL_UNAVAILABLE"
    assert health.readings_in_window == 0
    assert health.pattern is None


def test_missing_compatible_sgp40_sraw_is_unavailable_without_fabrication() -> None:
    service = VivayuHealthService()

    health = add(service, "A", telemetry(sraw=None))

    assert health.status == "UNAVAILABLE"
    assert health.reason_code == "SGP40_SRAW_CHANNEL_UNAVAILABLE"
    assert health.readings_in_window == 0
    assert health.research_score is None


def test_bme280_is_rejected_even_if_numeric_gas_value_is_present() -> None:
    service = VivayuHealthService()
    bme280 = VivayuSensorConfiguration(
        environment_sensor="BME280",
        voc_sensor="SGP40_COMPATIBLE",
    )

    health = add(service, "A", telemetry(), bme280)

    assert health.reason_code == "BME280_GAS_RESISTANCE_UNAVAILABLE"
    assert health.readings_in_window == 0


def test_ags10_is_not_silently_mapped_into_sgp40_sraw() -> None:
    service = VivayuHealthService()
    ags10 = VivayuSensorConfiguration(
        environment_sensor="BME680",
        voc_sensor="AGS10",
    )

    health = add(service, "A", telemetry(), ags10)

    assert health.status == "UNAVAILABLE"
    assert health.reason_code == "AGS10_NOT_COMPATIBLE_WITH_SGP40_SRAW"
    assert "cannot be silently substituted" in health.reason
    assert health.readings_in_window == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("temperature_c", 100.0),
        ("humidity_pct", 101.0),
        ("pressure_pa", 20_000.0),
        ("gas_resistance_ohm", float("inf")),
        ("sraw", 70_000),
    ],
)
def test_invalid_or_out_of_range_legacy_payload_is_rejected_safely(
    field: str,
    value: float,
) -> None:
    service = VivayuHealthService()
    invalid = telemetry().model_copy(update={field: value})

    health = add(service, "A", invalid)

    assert health.status == "UNAVAILABLE"
    assert health.reason_code == "LEGACY_READING_INVALID"
    assert health.readings_in_window == 0


def test_missing_model_path_returns_error_without_crashing(tmp_path: Path) -> None:
    service = VivayuHealthService(model_path=tmp_path / "missing.joblib")

    initial = service.get_zone_health("A")
    result = add(service, "A", telemetry())

    assert initial.status == "ERROR"
    assert result.status == "ERROR"
    assert result.available is False
    assert result.reason_code == "LEGACY_MODEL_UNAVAILABLE"
    assert result.research_only is True


def test_predictor_factory_failure_is_contained() -> None:
    def broken_factory(_path: Path):
        raise RuntimeError("test load failure")

    service = VivayuHealthService(predictor_factory=broken_factory)

    assert service.get_zone_health("A").status == "ERROR"
    assert service.get_zone_health("B").status == "ERROR"


def test_every_public_health_state_is_research_only() -> None:
    service = VivayuHealthService()
    collecting = add(service, "A", telemetry())
    unavailable = add(service, "B", telemetry("B", gas_resistance_ohm=None))
    for index in range(2, 6):
        ready = add(service, "A", telemetry(sequence=index))

    assert collecting.research_only is True
    assert unavailable.research_only is True
    assert ready.research_only is True
