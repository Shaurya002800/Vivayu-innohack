"""System health route."""

from fastapi import APIRouter

from app.config import settings
from app.schemas import HealthResponse


router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    return HealthResponse(service=settings.app_name, data_mode=settings.data_mode)
