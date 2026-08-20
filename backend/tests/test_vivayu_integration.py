import asyncio
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx

from app.main import app
from app.schemas import (
    PrototypeIrrigationParameters,
    PrototypeWaterQualityParameters,
    VivayuHealthState,
    ZoneAllocationInput,
    ZoneTelemetry,
)
from app.services.freshwater_allocator import (
    allocate_freshwater,
    freshwater_allocation_policy,
)
from app.services.irrigation_need import calculate_irrigation_need, irrigation_need_policy
from app.services.vivayu_health_service import VivayuHealthService
from app.services.water_quality import calculate_water_quality_strategy, water_quality_policy
from app.state import ApplicationStateStore


async def request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def api_request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    return asyncio.run(request(method, path, **kwargs))


def next_compatible_telemetry(
    base: ZoneTelemetry,
    sequence: int,
) -> ZoneTelemetry:
    payload = base.model_dump()
    payload.update(
        {
            "timestamp_ms": (base.timestamp_ms or 0) + sequence,
            "gas_resistance_ohm": 40_000.0 + sequence,
            "sraw": 29_000 + sequence,
        }
    )
    return ZoneTelemetry.model_validate(payload)


def configured_store() -> ApplicationStateStore:
    store = ApplicationStateStore()
    for zone_id in ("A", "B"):
        store.update_irrigation_parameters(
            zone_id,
            PrototypeIrrigationParameters(
                target_moisture_pct=45.0,
                critical_moisture_pct=25.0,
                ml_per_moisture_point=20.0,
            ),
        )
        store.update_water_quality_parameters(
            zone_id,
            PrototypeWaterQualityParameters(max_irrigation_tds_ppm=450.0),
        )
    return store


def pipeline_results(state, *, alternate_a_health: VivayuHealthState | None = None):
    zones = dict(state.zones)
    if alternate_a_health is not None:
        zones["A"] = zones["A"].model_copy(
            update={"vivayu_health": alternate_a_health},
            deep=True,
        )
    irrigation = {
        zone_id: calculate_irrigation_need(
            zones[zone_id], state.weather, irrigation_need_policy
        )
        for zone_id in ("A", "B")
    }
    quality = {}
    for zone_id in ("A", "B"):
        context = zones[zone_id].crop_context
        quality[zone_id] = calculate_water_quality_strategy(
            zone_id=zone_id,
            requested_water_ml=irrigation[zone_id].requested_water_ml,
            fresh_source=state.water.fresh,
            marginal_source=state.water.marginal,
            configured_max_tds_ppm=(
                context.max_irrigation_tds_ppm if context is not None else None
            ),
            policy=water_quality_policy,
        )
    allocation = allocate_freshwater(
        freshwater_available_ml=state.water.fresh.available_l * 1000,
        marginal_available_ml=state.water.marginal.available_l * 1000,
        zone_inputs={
            zone_id: ZoneAllocationInput(
                zone_id=zone_id,
                irrigation_need=irrigation[zone_id],
                water_quality=quality[zone_id],
            )
            for zone_id in ("A", "B")
        },
        policy=freshwater_allocation_policy,
    )
    return irrigation, quality, allocation


def test_simulation_scenario_can_drive_zone_a_to_five_reading_result() -> None:
    store = ApplicationStateStore()
    state = store.load_scenario("zone_a_critical")
    assert state.zones["A"].vivayu_health.status == "COLLECTING"
    assert state.zones["A"].vivayu_health.readings_received == 1

    for sequence in range(2, 6):
        zone = store.get_zone("A")
        updated = store.update_zone_telemetry(
            "A",
            next_compatible_telemetry(zone.telemetry, sequence),
        )

    assert updated.vivayu_health.status == "READY"
    assert updated.vivayu_health.source_mode == "SIMULATION"
    assert updated.vivayu_health.pattern in {
        "baseline_like_pattern",
        "elevated_voc_pattern",
    }
    assert updated.vivayu_health.research_only is True


def test_legacy_ml_unavailable_scenario_is_explicit_and_does_not_fabricate() -> None:
    state = ApplicationStateStore().load_scenario("legacy_ml_unavailable")
    zone_b = state.zones["B"]

    assert zone_b.telemetry.gas_resistance_ohm is None
    assert zone_b.telemetry.sraw is None
    assert zone_b.vivayu_health.status == "UNAVAILABLE"
    assert zone_b.vivayu_health.reason_code == "BME280_GAS_RESISTANCE_UNAVAILABLE"
    assert zone_b.vivayu_health.pattern is None
    assert zone_b.vivayu_health.research_score is None


def test_incompatible_zone_irrigation_pipeline_still_uses_non_vivayu_inputs() -> None:
    store = ApplicationStateStore()
    store.load_scenario("legacy_ml_unavailable")
    for zone_id in ("A", "B"):
        store.update_irrigation_parameters(
            zone_id,
            PrototypeIrrigationParameters(
                target_moisture_pct=45.0,
                critical_moisture_pct=25.0,
                ml_per_moisture_point=20.0,
            ),
        )
        store.update_water_quality_parameters(
            zone_id,
            PrototypeWaterQualityParameters(max_irrigation_tds_ppm=450.0),
        )
    state = store.get_state()

    irrigation, quality, allocation = pipeline_results(state)

    assert state.zones["B"].vivayu_health.status == "UNAVAILABLE"
    assert irrigation["B"].actionable is True
    assert quality["B"].safe is True
    assert allocation.zones["B"].status == "FULLY_SERVED"


def test_state_reset_and_zone_reset_preserve_predictor_isolation() -> None:
    store = ApplicationStateStore()
    for sequence in range(2, 4):
        for zone_id in ("A", "B"):
            zone = store.get_zone(zone_id)
            store.update_zone_telemetry(
                zone_id,
                next_compatible_telemetry(zone.telemetry, sequence),
            )
    assert store.get_vivayu_health("A").readings_in_window == 3
    assert store.get_vivayu_health("B").readings_in_window == 3

    store.reset_zone_vivayu_predictor("A")

    assert store.get_vivayu_health("A").readings_in_window == 0
    assert store.get_vivayu_health("B").readings_in_window == 3
    reset = store.reset()
    assert reset.zones["A"].vivayu_health.readings_in_window == 1
    assert reset.zones["B"].vivayu_health.readings_in_window == 1


def test_health_api_returns_canonical_research_state() -> None:
    response = api_request("GET", "/api/v1/zones/A/vivayu-health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "COLLECTING"
    assert payload["readings_received"] == 1
    assert payload["readings_required"] == 5
    assert payload["research_only"] is True
    assert payload["source_mode"] == "SIMULATION"


def test_model_loading_failure_does_not_crash_health_api(
    tmp_path: Path,
    monkeypatch,
) -> None:
    failed = ApplicationStateStore(
        vivayu_service=VivayuHealthService(model_path=tmp_path / "missing.joblib")
    )
    import app.api.zones as zones_api

    monkeypatch.setattr(zones_api, "application_state", failed)
    response = api_request("GET", "/api/v1/zones/A/vivayu-health")

    assert response.status_code == 200
    assert response.json()["status"] == "ERROR"
    assert response.json()["reason_code"] == "LEGACY_MODEL_UNAVAILABLE"
    assert response.json()["research_only"] is True


def test_vivayu_only_change_cannot_change_m4_m5_or_m6_results() -> None:
    state = configured_store().get_state()
    ready = VivayuHealthState(
        status="READY",
        available=True,
        risk_level="high",
        pattern="elevated_voc_pattern",
        research_score=0.99,
        research_score_note="test research score",
        confidence_pct=98.0,
        confidence_note="test separation only",
        model_name="gas_threshold",
        readings_received=5,
        readings_required=5,
        readings_in_window=5,
        source_mode="SIMULATION",
        reason_code="LEGACY_RESEARCH_WINDOW_READY",
        reason="test ready research state",
        warnings=("research only",),
    )

    baseline_irrigation, baseline_quality, baseline_allocation = pipeline_results(state)
    changed_irrigation, changed_quality, changed_allocation = pipeline_results(
        state,
        alternate_a_health=ready,
    )

    assert changed_irrigation == baseline_irrigation
    assert changed_quality == baseline_quality
    assert changed_allocation == baseline_allocation


def test_health_api_is_read_only() -> None:
    before = api_request("GET", "/api/v1/state").json()

    first = api_request("GET", "/api/v1/zones/A/vivayu-health").json()
    second = api_request("GET", "/api/v1/zones/A/vivayu-health").json()
    after = api_request("GET", "/api/v1/state").json()

    assert first == second
    assert after == before
    assert "decision" not in after
    assert "actuation" not in after
