"""Cached six-hour weather integration behind a provider adapter boundary."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, Callable, Mapping, Protocol, Sequence

import httpx

from app.config import settings
from app.schemas import WeatherState


class WeatherProviderError(RuntimeError):
    """Raised when a weather provider cannot return a usable forecast."""


class WeatherProvider(Protocol):
    name: str

    def fetch_six_hour_forecast(
        self, *, latitude: float, longitude: float, timeout_s: float
    ) -> Mapping[str, Any]: ...


class OpenMeteoAdapter:
    """Minimal adapter for the Open-Meteo forecast API."""

    def __init__(
        self,
        api_url: str,
        client: httpx.Client | None = None,
        *,
        provider_name: str = "open-meteo",
    ) -> None:
        self._api_url = api_url
        self._client = client
        self.name = provider_name

    def fetch_six_hour_forecast(
        self, *, latitude: float, longitude: float, timeout_s: float
    ) -> Mapping[str, Any]:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(
                (
                    "precipitation_probability",
                    "precipitation",
                    "et0_fao_evapotranspiration",
                    "temperature_2m",
                )
            ),
            "forecast_hours": 6,
            "timezone": "auto",
        }
        try:
            if self._client is not None:
                response = self._client.get(self._api_url, params=params, timeout=timeout_s)
            else:
                with httpx.Client(timeout=timeout_s) as client:
                    response = client.get(self._api_url, params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise WeatherProviderError("weather provider request failed") from error
        if not isinstance(payload, Mapping):
            raise WeatherProviderError("weather provider returned an invalid document")
        return payload


class WeatherService:
    """Map provider data, cache successful forecasts and expose safe fallbacks."""

    def __init__(
        self,
        provider: WeatherProvider,
        *,
        latitude: float | None,
        longitude: float | None,
        cache_interval: timedelta = timedelta(minutes=15),
        timeout_s: float = 5.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if cache_interval.total_seconds() <= 0:
            raise ValueError("weather cache interval must be positive")
        if timeout_s <= 0:
            raise ValueError("weather request timeout must be positive")
        self._provider = provider
        self._latitude = latitude
        self._longitude = longitude
        self._cache_interval = cache_interval
        self._timeout_s = timeout_s
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._cached: WeatherState | None = None
        self._lock = RLock()

    def get_forecast(self, *, force_refresh: bool = False) -> WeatherState:
        with self._lock:
            now = self._aware_now()
            if not force_refresh and self._cached is not None:
                age_s = self._age_seconds(self._cached, now)
                if age_s < self._cache_interval.total_seconds():
                    return self._cached.model_copy(
                        update={
                            "status": "CACHED",
                            "age_s": age_s,
                            "stale": False,
                            "provider_status": "OK",
                            "error": None,
                        },
                        deep=True,
                    )

            if self._latitude is None or self._longitude is None:
                return self._unavailable(
                    provider_status="NOT_CONFIGURED",
                    error="weather location is not configured",
                )

            try:
                payload = self._provider.fetch_six_hour_forecast(
                    latitude=self._latitude,
                    longitude=self._longitude,
                    timeout_s=self._timeout_s,
                )
                live = self._map_forecast(payload, fetched_at=now)
            except Exception as error:  # provider boundary: preserve service availability
                return self._fallback(now, error)

            self._cached = live
            return live.model_copy(deep=True)

    def clear_cache(self) -> None:
        with self._lock:
            self._cached = None

    def _map_forecast(self, payload: Mapping[str, Any], *, fetched_at: datetime) -> WeatherState:
        hourly = payload.get("hourly")
        if not isinstance(hourly, Mapping):
            raise WeatherProviderError("weather forecast has no hourly data")

        times = hourly.get("time")
        if not isinstance(times, Sequence) or isinstance(times, (str, bytes)) or len(times) < 6:
            raise WeatherProviderError("weather forecast contains fewer than six hours")

        return WeatherState(
            status="LIVE",
            rain_probability_6h_pct=self._aggregate(hourly, "precipitation_probability", max),
            rain_6h_mm=self._aggregate(hourly, "precipitation", sum),
            et0_6h_mm=self._aggregate(hourly, "et0_fao_evapotranspiration", sum),
            temperature_max_6h_c=self._aggregate(hourly, "temperature_2m", max),
            fetched_at=fetched_at,
            age_s=0.0,
            stale=False,
            provider=self._provider.name,
            provider_status="OK",
            error=None,
        )

    @staticmethod
    def _aggregate(
        hourly: Mapping[str, Any], key: str, operation: Callable[[Sequence[float]], float]
    ) -> float | None:
        values = hourly.get(key)
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or len(values) < 6:
            return None
        six_values = values[:6]
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in six_values):
            return None
        return float(operation(six_values))

    def _fallback(self, now: datetime, error: Exception) -> WeatherState:
        message = f"{type(error).__name__}: weather provider unavailable"
        if self._cached is None:
            return self._unavailable(provider_status="ERROR", error=message)
        age_s = self._age_seconds(self._cached, now)
        return self._cached.model_copy(
            update={
                "status": "CACHED",
                "age_s": age_s,
                "stale": age_s >= self._cache_interval.total_seconds(),
                "provider_status": "ERROR",
                "error": message,
            },
            deep=True,
        )

    def _unavailable(self, *, provider_status: str, error: str) -> WeatherState:
        return WeatherState.model_validate(
            {
                "status": "OFFLINE",
                "fetched_at": None,
                "age_s": None,
                "stale": True,
                "provider": self._provider.name,
                "provider_status": provider_status,
                "error": error,
            }
        )

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("weather service clock must return a timezone-aware datetime")
        return value

    @staticmethod
    def _age_seconds(weather: WeatherState, now: datetime) -> float:
        if weather.fetched_at is None:
            return 0.0
        return max(0.0, (now - weather.fetched_at).total_seconds())


open_meteo_adapter = OpenMeteoAdapter(
    settings.weather_api_url,
    provider_name=settings.weather_provider,
)
weather_service = WeatherService(
    open_meteo_adapter,
    latitude=settings.farm_latitude,
    longitude=settings.farm_longitude,
    cache_interval=timedelta(minutes=settings.weather_cache_minutes),
    timeout_s=settings.weather_request_timeout_s,
)
