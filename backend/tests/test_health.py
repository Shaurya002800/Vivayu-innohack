import asyncio

import httpx

from app.main import app


async def request_health() -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/v1/health")


def test_health_returns_safe_default_mode() -> None:
    response = asyncio.run(request_health())

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "VIVAYU Aqua API",
        "data_mode": "simulation",
        "schema_version": "1.0",
    }
