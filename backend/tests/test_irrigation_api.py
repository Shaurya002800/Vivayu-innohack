import asyncio
from copy import deepcopy
from typing import Any

import httpx

from app.main import app


async def request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def api_request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    return asyncio.run(request(method, path, **kwargs))


PARAMETERS = {
    "target_moisture_pct": 40.0,
    "critical_moisture_pct": 25.0,
    "ml_per_moisture_point": 20.0,
    "calibration_basis": "prototype_field_response",
}


def test_default_preview_requires_explicit_prototype_configuration() -> None:
    parameters = api_request("GET", "/api/v1/zones/A/irrigation-parameters")
    preview = api_request("GET", "/api/v1/zones/A/irrigation-need")

    assert parameters.status_code == 200
    assert parameters.json()["target_moisture_pct"] is None
    assert parameters.json()["critical_moisture_pct"] is None
    assert parameters.json()["ml_per_moisture_point"] is None
    assert preview.status_code == 200
    assert preview.json()["status"] == "CONFIG_REQUIRED"
    assert preview.json()["requested_water_ml"] is None


def test_parameter_api_updates_only_selected_zone_and_canonical_context() -> None:
    zone_b_before = api_request("GET", "/api/v1/zones/B").json()

    updated = api_request(
        "PUT",
        "/api/v1/zones/A/irrigation-parameters",
        json=PARAMETERS,
    )
    zone_a = api_request("GET", "/api/v1/zones/A").json()
    state = api_request("GET", "/api/v1/state").json()

    assert updated.status_code == 200
    assert updated.json() == PARAMETERS
    assert zone_a["config"]["irrigation_parameters"] == PARAMETERS
    assert zone_a["crop_context"]["target_moisture_pct"] == 40.0
    assert zone_a["crop_context"]["critical_moisture_pct"] == 25.0
    assert state["zones"]["A"] == zone_a
    assert api_request("GET", "/api/v1/zones/B").json() == zone_b_before


def test_preview_is_read_only_and_returns_explanations() -> None:
    api_request("PUT", "/api/v1/zones/A/irrigation-parameters", json=PARAMETERS)
    state_before = api_request("GET", "/api/v1/state").json()

    preview = api_request("GET", "/api/v1/zones/A/irrigation-need")
    state_after = api_request("GET", "/api/v1/state").json()

    assert preview.status_code == 200
    payload = preview.json()
    assert payload["status"] == "NEEDED"
    assert payload["base_requested_ml"] == 160.0
    assert payload["requested_water_ml"] == 160.0
    assert payload["reasons"]
    assert payload["reason_codes"]
    assert payload["policy"]["soil_deficit_weight"] == 0.60
    assert state_after == state_before
    assert "irrigation_need" not in state_after["zones"]["A"]


def test_rain_scenario_defers_noncritical_preview() -> None:
    api_request("PUT", "/api/v1/zones/A/irrigation-parameters", json=PARAMETERS)
    api_request(
        "POST",
        "/api/v1/simulation/load",
        json={"scenario_id": "rain_soon"},
    )

    preview = api_request("GET", "/api/v1/zones/A/irrigation-need")

    assert preview.status_code == 200
    assert preview.json()["status"] == "CONFIG_REQUIRED"


def test_configure_after_loading_rain_scenario_defers_noncritical_preview() -> None:
    api_request(
        "POST",
        "/api/v1/simulation/load",
        json={"scenario_id": "rain_soon"},
    )
    api_request("PUT", "/api/v1/zones/A/irrigation-parameters", json=PARAMETERS)

    preview = api_request("GET", "/api/v1/zones/A/irrigation-need")

    assert preview.status_code == 200
    assert preview.json()["status"] == "DEFER_FOR_RAIN"
    assert preview.json()["base_requested_ml"] == 160.0
    assert preview.json()["requested_water_ml"] == 0.0


def test_critical_scenario_is_not_deferred() -> None:
    api_request(
        "POST",
        "/api/v1/simulation/load",
        json={"scenario_id": "zone_a_critical"},
    )
    api_request("PUT", "/api/v1/zones/A/irrigation-parameters", json=PARAMETERS)

    preview = api_request("GET", "/api/v1/zones/A/irrigation-need")

    assert preview.status_code == 200
    assert preview.json()["status"] == "CRITICAL"
    assert preview.json()["requested_water_ml"] == 360.0


def test_invalid_parameter_payload_is_rejected_without_mutation() -> None:
    before = api_request("GET", "/api/v1/zones/A/irrigation-parameters").json()
    invalid = deepcopy(PARAMETERS)
    invalid["ml_per_moisture_point"] = 0.0

    response = api_request(
        "PUT",
        "/api/v1/zones/A/irrigation-parameters",
        json=invalid,
    )

    assert response.status_code == 422
    assert api_request("GET", "/api/v1/zones/A/irrigation-parameters").json() == before


def test_invalid_zone_preview_is_rejected() -> None:
    response = api_request("GET", "/api/v1/zones/C/irrigation-need")

    assert response.status_code == 422
