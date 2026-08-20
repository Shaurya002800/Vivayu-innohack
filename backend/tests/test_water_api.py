import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
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
    "target_moisture_pct": 40.0,
    "critical_moisture_pct": 25.0,
    "ml_per_moisture_point": 20.0,
    "calibration_basis": "prototype_field_response",
}
QUALITY_CONSTRAINT = {
    "max_irrigation_tds_ppm": 500.0,
    "constraint_basis": "prototype_or_sourced",
}


def configure_zone_a() -> None:
    assert api_request(
        "PUT", "/api/v1/zones/A/irrigation-parameters", json=IRRIGATION_PARAMETERS
    ).status_code == 200
    assert api_request(
        "PUT", "/api/v1/water/zones/A/constraint", json=QUALITY_CONSTRAINT
    ).status_code == 200


def source_update(tds_ppm: float, *, available_l: float = 1.0) -> dict[str, Any]:
    return {
        "tds_ppm": tds_ppm,
        "temperature_c": 24.0,
        "available_l": available_l,
        "last_measured_at": datetime.now(timezone.utc).isoformat(),
    }


def test_water_state_exposes_explicit_simulated_source_identity() -> None:
    response = api_request("GET", "/api/v1/water")

    assert response.status_code == 200
    payload = response.json()
    assert payload["fresh"]["source_id"] == "fresh"
    assert payload["marginal"]["source_id"] == "marginal"
    assert payload["fresh"]["quality_status"] == "SIMULATED"
    assert payload["marginal"]["quality_status"] == "SIMULATED"
    assert payload["mix"]["tds_ppm"] is None


def test_source_update_changes_only_selected_source_and_canonical_state() -> None:
    before = api_request("GET", "/api/v1/water").json()

    response = api_request(
        "PUT", "/api/v1/water/sources/fresh", json=source_update(300.0)
    )
    after = api_request("GET", "/api/v1/state").json()["water"]

    assert response.status_code == 200
    assert response.json()["tds_ppm"] == 300.0
    assert response.json()["quality_status"] == "SIMULATED"
    assert after["fresh"] == response.json()
    assert after["marginal"] == before["marginal"]


def test_invalid_source_payload_and_future_timestamp_are_rejected() -> None:
    before = api_request("GET", "/api/v1/water").json()
    invalid = source_update(-1.0)
    future = source_update(250.0)
    future["last_measured_at"] = (
        datetime.now(timezone.utc) + timedelta(hours=1)
    ).isoformat()

    assert api_request(
        "PUT", "/api/v1/water/sources/fresh", json=invalid
    ).status_code == 422
    assert api_request(
        "PUT", "/api/v1/water/sources/fresh", json=future
    ).status_code == 422
    assert api_request("GET", "/api/v1/water").json() == before


def test_zone_constraint_update_is_isolated_and_updates_crop_context() -> None:
    zone_b_before = api_request("GET", "/api/v1/zones/B").json()

    response = api_request(
        "PUT", "/api/v1/water/zones/A/constraint", json=QUALITY_CONSTRAINT
    )
    zone_a = api_request("GET", "/api/v1/zones/A").json()

    assert response.status_code == 200
    assert response.json() == QUALITY_CONSTRAINT
    assert zone_a["crop_context"]["max_irrigation_tds_ppm"] == 500.0
    assert api_request("GET", "/api/v1/zones/B").json() == zone_b_before


def test_preview_integrates_milestone4_requested_volume_and_is_read_only() -> None:
    configure_zone_a()
    before = api_request("GET", "/api/v1/state").json()

    irrigation = api_request("GET", "/api/v1/zones/A/irrigation-need").json()
    response = api_request("GET", "/api/v1/water/zones/A/strategy")
    after = api_request("GET", "/api/v1/state").json()

    assert response.status_code == 200
    payload = response.json()
    assert payload["requested_water_ml"] == irrigation["requested_water_ml"] == 160.0
    assert payload["strategy"] == "CONTROLLED_BLEND"
    assert payload["safe"] is True
    assert payload["measured_tds_ppm"] is None
    assert after == before
    assert "decision" not in after
    assert "actuation" not in after


def test_no_irrigation_request_and_missing_constraint_are_explicit() -> None:
    api_request(
        "PUT", "/api/v1/zones/A/irrigation-parameters", json=IRRIGATION_PARAMETERS
    )
    missing = api_request("GET", "/api/v1/water/zones/A/strategy").json()
    api_request(
        "PUT", "/api/v1/water/zones/A/constraint", json=QUALITY_CONSTRAINT
    )
    no_need_parameters = deepcopy(IRRIGATION_PARAMETERS)
    no_need_parameters["target_moisture_pct"] = 30.0
    api_request(
        "PUT", "/api/v1/zones/A/irrigation-parameters", json=no_need_parameters
    )
    zero = api_request("GET", "/api/v1/water/zones/A/strategy").json()

    assert missing["strategy"] == "CONFIG_REQUIRED"
    assert zero["strategy"] == "NO_IRRIGATION_REQUEST"


def test_source_tds_changes_strategy_with_soil_crop_weather_unchanged() -> None:
    configure_zone_a()
    state_before = api_request("GET", "/api/v1/state").json()
    api_request(
        "PUT", "/api/v1/water/sources/marginal", json=source_update(400.0)
    )
    marginal_only = api_request("GET", "/api/v1/water/zones/A/strategy").json()
    api_request(
        "PUT", "/api/v1/water/sources/marginal", json=source_update(820.0)
    )
    controlled = api_request("GET", "/api/v1/water/zones/A/strategy").json()
    state_after = api_request("GET", "/api/v1/state").json()

    assert marginal_only["strategy"] == "MARGINAL_ONLY"
    assert controlled["strategy"] == "CONTROLLED_BLEND"
    assert state_after["zones"] == state_before["zones"]
    assert state_after["weather"] == state_before["weather"]


def test_scenario_and_source_changes_do_not_leak_across_reset() -> None:
    baseline = api_request("GET", "/api/v1/water").json()
    api_request("PUT", "/api/v1/water/sources/fresh", json=source_update(350.0))
    api_request(
        "POST", "/api/v1/simulation/load", json={"scenario_id": "tds_correction"}
    )

    reset = api_request("POST", "/api/v1/simulation/reset").json()

    for source_id in ("fresh", "marginal"):
        reset["water"][source_id].pop("measurement_age_s")
        baseline[source_id].pop("measurement_age_s")
    assert reset["water"] == baseline
    assert reset["active_scenario_id"] is None


def test_invalid_zone_and_source_are_rejected() -> None:
    assert api_request(
        "GET", "/api/v1/water/zones/C/strategy"
    ).status_code == 422
    assert api_request(
        "PUT", "/api/v1/water/sources/unknown", json=source_update(250.0)
    ).status_code == 422
