from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

import httpx
import pytest

from app.schemas import WeatherState
from app.services.weather_service import OpenMeteoAdapter, WeatherProviderError, WeatherService
from app.state import ApplicationStateStore, SimulationWeatherProtectedError


def forecast_payload() -> dict[str, Any]:
    return {
        "hourly": {
            "time": [f"2026-08-20T{hour:02d}:00" for hour in range(6)],
            "precipitation_probability": [5, 20, 35, 80, 45, 10],
            "precipitation": [0.0, 0.1, 0.2, 1.0, 0.3, 0.0],
            "et0_fao_evapotranspiration": [0.1, 0.2, 0.3, 0.2, 0.1, 0.1],
            "temperature_2m": [29.0, 30.0, 31.5, 30.5, 28.0, 27.5],
        }
    }


class FakeProvider:
    name = "fake-weather"

    def __init__(self, payload: Mapping[str, Any] | None = None) -> None:
        self.payload = payload or forecast_payload()
        self.error: Exception | None = None
        self.calls = 0
        self.last_timeout_s: float | None = None

    def fetch_six_hour_forecast(
        self, *, latitude: float, longitude: float, timeout_s: float
    ) -> Mapping[str, Any]:
        self.calls += 1
        self.last_timeout_s = timeout_s
        assert latitude == 12.0
        assert longitude == 79.0
        if self.error is not None:
            raise self.error
        return self.payload


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


def service(provider: FakeProvider, clock: MutableClock) -> WeatherService:
    return WeatherService(
        provider,
        latitude=12.0,
        longitude=79.0,
        cache_interval=timedelta(minutes=15),
        timeout_s=2.5,
        clock=clock,
    )


def test_weather_mapping_summarizes_exactly_six_hours() -> None:
    provider = FakeProvider()
    clock = MutableClock()

    weather = service(provider, clock).get_forecast()

    assert weather.status == "LIVE"
    assert weather.rain_probability_6h_pct == 80.0
    assert weather.rain_6h_mm == pytest.approx(1.6)
    assert weather.et0_6h_mm == pytest.approx(1.0)
    assert weather.temperature_max_6h_c == 31.5
    assert weather.fetched_at == clock.now
    assert weather.age_s == 0.0
    assert weather.stale is False
    assert weather.provider == "fake-weather"
    assert weather.provider_status == "OK"
    assert provider.last_timeout_s == 2.5


def test_fresh_cache_avoids_provider_request_and_exposes_age() -> None:
    provider = FakeProvider()
    clock = MutableClock()
    weather_service = service(provider, clock)
    weather_service.get_forecast()
    clock.now += timedelta(minutes=10)

    cached = weather_service.get_forecast()

    assert provider.calls == 1
    assert cached.status == "CACHED"
    assert cached.provider_status == "OK"
    assert cached.age_s == 600.0
    assert cached.stale is False


def test_provider_failure_falls_back_to_cached_forecast() -> None:
    provider = FakeProvider()
    clock = MutableClock()
    weather_service = service(provider, clock)
    live = weather_service.get_forecast()
    provider.error = RuntimeError("provider down")
    clock.now += timedelta(minutes=5)

    fallback = weather_service.get_forecast(force_refresh=True)

    assert fallback.status == "CACHED"
    assert fallback.provider_status == "ERROR"
    assert fallback.rain_6h_mm == live.rain_6h_mm
    assert fallback.age_s == 300.0
    assert fallback.stale is False
    assert fallback.error == "RuntimeError: weather provider unavailable"


def test_expired_cached_fallback_is_marked_stale() -> None:
    provider = FakeProvider()
    clock = MutableClock()
    weather_service = service(provider, clock)
    weather_service.get_forecast()
    provider.error = TimeoutError("timed out")
    clock.now += timedelta(minutes=16)

    fallback = weather_service.get_forecast()

    assert fallback.status == "CACHED"
    assert fallback.provider_status == "ERROR"
    assert fallback.stale is True
    assert fallback.age_s == 960.0


def test_timeout_without_cache_exposes_offline_null_state() -> None:
    provider = FakeProvider()
    provider.error = TimeoutError("timed out")

    weather = service(provider, MutableClock()).get_forecast()

    assert weather.status == "OFFLINE"
    assert weather.provider_status == "ERROR"
    assert weather.stale is True
    assert weather.fetched_at is None
    assert weather.age_s is None
    assert weather.rain_probability_6h_pct is None
    assert weather.rain_6h_mm is None
    assert weather.et0_6h_mm is None
    assert weather.temperature_max_6h_c is None


def test_missing_location_does_not_call_provider_or_invent_weather() -> None:
    provider = FakeProvider()
    weather_service = WeatherService(provider, latitude=None, longitude=None)

    weather = weather_service.get_forecast()

    assert provider.calls == 0
    assert weather.status == "OFFLINE"
    assert weather.provider_status == "NOT_CONFIGURED"
    assert weather.rain_6h_mm is None


def test_partial_provider_metric_remains_null_instead_of_becoming_zero() -> None:
    payload = forecast_payload()
    payload["hourly"]["et0_fao_evapotranspiration"][2] = None
    provider = FakeProvider(payload)

    weather = service(provider, MutableClock()).get_forecast()

    assert weather.status == "LIVE"
    assert weather.et0_6h_mm is None
    assert weather.rain_6h_mm == pytest.approx(1.6)


def test_malformed_forecast_fails_closed_to_offline() -> None:
    provider = FakeProvider({"hourly": {"time": ["only-one-hour"]}})

    weather = service(provider, MutableClock()).get_forecast()

    assert weather.status == "OFFLINE"
    assert weather.provider_status == "ERROR"
    assert weather.rain_6h_mm is None


def test_simulation_weather_cannot_be_overwritten_by_live_state() -> None:
    store = ApplicationStateStore(data_mode="simulation")
    original = store.get_state().weather
    live = WeatherState(
        status="LIVE",
        rain_6h_mm=99.0,
        provider="fake-weather",
        provider_status="OK",
    )

    with pytest.raises(SimulationWeatherProtectedError):
        store.update_weather(live)

    assert store.get_state().weather == original


def test_hardware_state_accepts_canonical_live_weather() -> None:
    store = ApplicationStateStore(data_mode="hardware")
    provider = FakeProvider()
    live = service(provider, MutableClock()).get_forecast()

    stored = store.update_weather(live)

    assert stored.status == "LIVE"
    assert store.get_state().weather == live


def test_open_meteo_adapter_sets_required_fields_and_request_timeout() -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> Mapping[str, Any]:
            return forecast_payload()

    class Client:
        def __init__(self) -> None:
            self.params: Mapping[str, Any] | None = None
            self.timeout: float | None = None

        def get(self, url: str, *, params: Mapping[str, Any], timeout: float) -> Response:
            assert url == "https://weather.test/forecast"
            self.params = params
            self.timeout = timeout
            return Response()

    client = Client()
    adapter = OpenMeteoAdapter(
        "https://weather.test/forecast",
        client=client,  # type: ignore[arg-type]
    )

    adapter.fetch_six_hour_forecast(latitude=12.0, longitude=79.0, timeout_s=3.0)

    assert client.timeout == 3.0
    assert client.params is not None
    assert client.params["forecast_hours"] == 6
    assert "precipitation_probability" in client.params["hourly"]
    assert "et0_fao_evapotranspiration" in client.params["hourly"]


def test_open_meteo_timeout_is_normalized_to_provider_error() -> None:
    class TimingOutClient:
        def get(self, url: str, *, params: Mapping[str, Any], timeout: float) -> None:
            raise httpx.ReadTimeout("timed out")

    adapter = OpenMeteoAdapter(
        "https://weather.test/forecast",
        client=TimingOutClient(),  # type: ignore[arg-type]
    )

    with pytest.raises(WeatherProviderError, match="request failed"):
        adapter.fetch_six_hour_forecast(latitude=12.0, longitude=79.0, timeout_s=3.0)
