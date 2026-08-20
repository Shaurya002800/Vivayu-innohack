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


def test_get_complete_state_is_visibly_simulated() -> None:
    response = api_request("GET", "/api/v1/state")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_mode"] == "simulation"
    assert set(payload["zones"]) == {"A", "B"}
    assert payload["power"]["solar_power_w"] is None


def test_list_activate_and_reset_simulation_scenario() -> None:
    scenarios = api_request("GET", "/api/v1/simulation/scenarios")
    loaded = api_request(
        "POST",
        "/api/v1/simulation/load",
        json={"scenario_id": "zone_a_critical"},
    )
    reset = api_request("POST", "/api/v1/simulation/reset")

    assert scenarios.status_code == 200
    assert len(scenarios.json()) == 6
    assert loaded.status_code == 200
    assert loaded.json()["active_scenario_id"] == "zone_a_critical"
    assert loaded.json()["zones"]["A"]["telemetry"]["soil_moisture_pct"] == 22.0
    assert reset.status_code == 200
    assert reset.json()["active_scenario_id"] is None
    assert reset.json()["zones"]["A"]["telemetry"]["soil_moisture_pct"] == 32.0


def test_unknown_scenario_returns_404() -> None:
    response = api_request(
        "POST",
        "/api/v1/simulation/load",
        json={"scenario_id": "not-a-scenario"},
    )

    assert response.status_code == 404


def test_invalid_zone_path_is_rejected() -> None:
    response = api_request("GET", "/api/v1/zones/C")

    assert response.status_code == 422


def test_zone_config_and_manual_stage_persist_through_api() -> None:
    initial = api_request("GET", "/api/v1/zones/A").json()
    config = initial["config"]
    config.update(
        {
            "crop_id": "okra",
            "growth_stage_mode": "AUTO",
            "manual_growth_stage": None,
        }
    )

    updated = api_request("PUT", "/api/v1/zones/A/config", json=config)
    overridden = api_request(
        "POST",
        "/api/v1/zones/A/stage-override",
        json={"growth_stage": "flowering"},
    )
    persisted = api_request("GET", "/api/v1/zones/A")

    assert updated.status_code == 200
    assert updated.json()["config"]["crop_id"] == "okra"
    assert overridden.status_code == 200
    assert overridden.json()["growth_stage"] == "flowering"
    assert persisted.json()["config"]["crop_id"] == "okra"
    assert persisted.json()["config"]["manual_growth_stage"] == "flowering"


def test_zone_config_body_cannot_target_a_different_zone() -> None:
    zone_b_config = api_request("GET", "/api/v1/zones/B").json()["config"]

    response = api_request("PUT", "/api/v1/zones/A/config", json=zone_b_config)

    assert response.status_code == 409
