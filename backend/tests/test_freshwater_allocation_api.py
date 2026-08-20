import asyncio
from typing import Any

import httpx

from app.main import app


async def request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def api_request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    return asyncio.run(request(method, path, **kwargs))


IRRIGATION_PARAMETERS = {
    "target_moisture_pct": 45.0,
    "critical_moisture_pct": 25.0,
    "ml_per_moisture_point": 20.0,
    "calibration_basis": "prototype_field_response",
}
QUALITY_CONSTRAINT = {
    "max_irrigation_tds_ppm": 450.0,
    "constraint_basis": "prototype_or_sourced",
}


def configure_zone(zone_id: str) -> None:
    assert api_request(
        "PUT",
        f"/api/v1/zones/{zone_id}/irrigation-parameters",
        json=IRRIGATION_PARAMETERS,
    ).status_code == 200
    assert api_request(
        "PUT",
        f"/api/v1/water/zones/{zone_id}/constraint",
        json=QUALITY_CONSTRAINT,
    ).status_code == 200


def update_fresh_availability(available_l: float) -> None:
    source = api_request("GET", "/api/v1/water").json()["fresh"]
    payload = {
        "tds_ppm": source["tds_ppm"],
        "temperature_c": source["temperature_c"],
        "available_l": available_l,
        "last_measured_at": source["last_measured_at"],
    }
    assert api_request(
        "PUT", "/api/v1/water/sources/fresh", json=payload
    ).status_code == 200


def test_allocation_preview_fully_serves_both_zones_when_banks_are_sufficient() -> None:
    configure_zone("A")
    configure_zone("B")

    response = api_request("GET", "/api/v1/water/allocation-preview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["zones"]["A"]["status"] == "FULLY_SERVED"
    assert payload["zones"]["B"]["status"] == "FULLY_SERVED"
    assert payload["freshwater_available_ml"] == 1000.0
    assert payload["marginal_available_ml"] == 2500.0
    assert payload["scarcity_active"] is False


def test_preview_is_idempotent_and_does_not_deduct_source_banks() -> None:
    configure_zone("A")
    configure_zone("B")
    state_before = api_request("GET", "/api/v1/state").json()

    first = api_request("GET", "/api/v1/water/allocation-preview").json()
    second = api_request("GET", "/api/v1/water/allocation-preview").json()
    state_after = api_request("GET", "/api/v1/state").json()

    assert first == second
    assert state_after == state_before
    assert state_after["water"]["fresh"]["available_l"] == 1.0
    assert "NO_WATER_DEDUCTED_PREVIEW" in first["warning_codes"]
    assert "decision" not in state_after
    assert "actuation" not in state_after


def test_freshwater_shortage_scenario_exercises_real_allocator() -> None:
    assert api_request(
        "POST",
        "/api/v1/simulation/load",
        json={"scenario_id": "freshwater_shortage"},
    ).status_code == 200
    configure_zone("A")
    configure_zone("B")

    payload = api_request("GET", "/api/v1/water/allocation-preview").json()

    assert payload["freshwater_available_ml"] == 250.0
    assert payload["freshwater_required_for_full_service_ml"] > 250.0
    assert payload["scarcity_active"] is True
    assert payload["zones"]["A"]["irrigation_status"] == "CRITICAL"
    assert payload["zones"]["A"]["critical_minimum_met"] is True
    assert payload["total_deliverable_water_ml"] < payload["total_requested_water_ml"]
    for zone in payload["zones"].values():
        if zone["deliverable_water_ml"] > 0:
            assert zone["safe_ratio_preserved"] is True
            assert zone["allocated_marginal_fraction"] <= (
                zone["required_marginal_fraction"] + 0.000001
            )


def test_scenario_reset_restores_bank_and_does_not_leak_allocation() -> None:
    api_request(
        "POST",
        "/api/v1/simulation/load",
        json={"scenario_id": "freshwater_shortage"},
    )
    configure_zone("A")
    configure_zone("B")
    scarce = api_request("GET", "/api/v1/water/allocation-preview").json()

    reset = api_request("POST", "/api/v1/simulation/reset").json()
    after = api_request("GET", "/api/v1/water/allocation-preview").json()

    assert scarce["freshwater_available_ml"] == 250.0
    assert reset["water"]["fresh"]["available_l"] == 1.0
    assert reset["active_scenario_id"] is None
    assert after["freshwater_available_ml"] == 1000.0
    assert after["total_deliverable_water_ml"] == 0.0


def test_zone_configuration_isolation_is_preserved_in_preview() -> None:
    configure_zone("A")
    zone_b_before = api_request("GET", "/api/v1/zones/B").json()

    payload = api_request("GET", "/api/v1/water/allocation-preview").json()

    assert payload["zones"]["A"]["status"] == "FULLY_SERVED"
    assert payload["zones"]["B"]["status"] == "BLOCKED"
    assert api_request("GET", "/api/v1/zones/B").json() == zone_b_before


def test_only_bank_change_alters_delivery_not_crop_soil_weather_or_tds() -> None:
    configure_zone("A")
    configure_zone("B")
    state_before = api_request("GET", "/api/v1/state").json()
    abundant = api_request("GET", "/api/v1/water/allocation-preview").json()

    update_fresh_availability(0.1)
    scarce = api_request("GET", "/api/v1/water/allocation-preview").json()
    state_after = api_request("GET", "/api/v1/state").json()

    assert state_after["zones"] == state_before["zones"]
    assert state_after["weather"] == state_before["weather"]
    assert state_after["water"]["fresh"]["tds_ppm"] == (
        state_before["water"]["fresh"]["tds_ppm"]
    )
    assert state_after["water"]["marginal"] == state_before["water"]["marginal"]
    assert abundant["total_requested_water_ml"] == scarce["total_requested_water_ml"]
    assert abundant["total_deliverable_water_ml"] > scarce["total_deliverable_water_ml"]
    assert scarce["freshwater_allocated_ml"] <= 100.0
    assert scarce["scarcity_active"] is True


def test_default_unconfigured_preview_is_explainably_blocked() -> None:
    response = api_request("GET", "/api/v1/water/allocation-preview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["zones"]["A"]["status"] == "BLOCKED"
    assert payload["zones"]["B"]["status"] == "BLOCKED"
    assert payload["freshwater_allocated_ml"] == 0.0
    assert payload["marginal_allocated_ml"] == 0.0
    assert "IRRIGATION_INPUT_BLOCKED" in payload["reason_codes"]
