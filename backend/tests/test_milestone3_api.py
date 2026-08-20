import asyncio
from copy import deepcopy
from datetime import date, timedelta
from typing import Any

import httpx

from app.main import app
from app.schemas import WeatherState
from app.state import ApplicationStateStore


async def request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def api_request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    return asyncio.run(request(method, path, **kwargs))


def test_crop_profile_endpoints_list_and_validate_profiles() -> None:
    listed = api_request("GET", "/api/v1/crops")
    tomato = api_request("GET", "/api/v1/crops/tomato")
    missing = api_request("GET", "/api/v1/crops/not-real")

    assert listed.status_code == 200
    assert {profile["crop_id"] for profile in listed.json()} == {"tomato", "chilli", "okra"}
    assert tomato.status_code == 200
    assert tomato.json()["stages"][0]["start_day"] == 0
    assert missing.status_code == 404


def test_unknown_crop_config_is_rejected_without_mutating_zone() -> None:
    before = api_request("GET", "/api/v1/zones/A").json()
    config = deepcopy(before["config"])
    config["crop_id"] = "not-real"

    response = api_request("PUT", "/api/v1/zones/A/config", json=config)

    assert response.status_code == 422
    assert api_request("GET", "/api/v1/zones/A").json() == before


def test_future_sowing_date_is_rejected_by_zone_api() -> None:
    config = api_request("GET", "/api/v1/zones/A").json()["config"]
    config["sowing_date"] = (date.today() + timedelta(days=1)).isoformat()

    response = api_request("PUT", "/api/v1/zones/A/config", json=config)

    assert response.status_code == 422
    assert "future" in response.json()["detail"]


def test_zone_crop_context_and_complete_state_are_integrated() -> None:
    context_response = api_request("GET", "/api/v1/zones/A/crop-context")
    state_response = api_request("GET", "/api/v1/state")

    assert context_response.status_code == 200
    assert context_response.json()["crop_id"] == "tomato"
    assert state_response.status_code == 200
    state = state_response.json()
    assert state["zones"]["A"]["crop_context"] == context_response.json()
    assert state["zones"]["B"]["crop_context"]["crop_id"] == "chilli"
    assert state["weather"]["provider"] == "demo_scenarios"
    assert state["weather"]["provider_status"] == "SIMULATED"
    assert state["weather"]["stale"] is False


def test_simulation_weather_refresh_preserves_scenario_weather(monkeypatch: Any) -> None:
    loaded = api_request(
        "POST",
        "/api/v1/simulation/load",
        json={"scenario_id": "rain_soon"},
    ).json()

    class MustNotBeCalled:
        def get_forecast(self, *, force_refresh: bool = False) -> None:
            raise AssertionError("live provider was called in simulation mode")

    monkeypatch.setattr("app.api.weather.weather_service", MustNotBeCalled())
    refreshed = api_request("POST", "/api/v1/weather/refresh")

    assert refreshed.status_code == 200
    assert refreshed.json() == loaded["weather"]
    assert refreshed.json()["rain_6h_mm"] == 7.4
    assert refreshed.json()["status"] == "SIMULATED"


def test_weather_get_returns_state_without_refresh_side_effect(monkeypatch: Any) -> None:
    class MustNotBeCalled:
        def get_forecast(self, *, force_refresh: bool = False) -> None:
            raise AssertionError("GET weather attempted a provider request")

    monkeypatch.setattr("app.api.weather.weather_service", MustNotBeCalled())
    response = api_request("GET", "/api/v1/weather")

    assert response.status_code == 200
    assert response.json()["status"] == "SIMULATED"


def test_hardware_weather_refresh_updates_canonical_state(monkeypatch: Any) -> None:
    hardware_store = ApplicationStateStore(data_mode="hardware")
    live = WeatherState(
        status="LIVE",
        rain_probability_6h_pct=40.0,
        rain_6h_mm=1.2,
        et0_6h_mm=0.8,
        temperature_max_6h_c=31.0,
        fetched_at="2026-08-20T10:00:00+00:00",
        age_s=0.0,
        provider="fake-weather",
        provider_status="OK",
    )

    class LiveService:
        def __init__(self) -> None:
            self.force_refresh: bool | None = None

        def get_forecast(self, *, force_refresh: bool = False) -> WeatherState:
            self.force_refresh = force_refresh
            return live

    service = LiveService()
    monkeypatch.setattr("app.api.weather.application_state", hardware_store)
    monkeypatch.setattr("app.api.weather.weather_service", service)

    response = api_request("POST", "/api/v1/weather/refresh")

    assert response.status_code == 200
    assert response.json()["status"] == "LIVE"
    assert service.force_refresh is True
    assert hardware_store.get_state().weather == live
