"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.irrigation import router as irrigation_router
from app.api.crops import router as crops_router
from app.api.simulation import router as simulation_router
from app.api.state import router as state_router
from app.api.zones import router as zones_router
from app.api.weather import router as weather_router
from app.api.water import router as water_router
from app.config import settings
from app.services.serial_bridge import serial_bridge


@asynccontextmanager
async def lifespan(_app: FastAPI):
    serial_bridge.start()
    try:
        yield
    finally:
        serial_bridge.stop()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(state_router, prefix=settings.api_prefix)
app.include_router(zones_router, prefix=settings.api_prefix)
app.include_router(irrigation_router, prefix=settings.api_prefix)
app.include_router(crops_router, prefix=settings.api_prefix)
app.include_router(weather_router, prefix=settings.api_prefix)
app.include_router(water_router, prefix=settings.api_prefix)
app.include_router(simulation_router, prefix=settings.api_prefix)
