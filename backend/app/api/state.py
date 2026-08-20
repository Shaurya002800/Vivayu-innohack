"""Canonical complete application-state endpoint."""

from fastapi import APIRouter

from app.schemas import SystemState
from app.state import application_state


router = APIRouter(tags=["system"])


@router.get("/state", response_model=SystemState)
def get_state() -> SystemState:
    return application_state.get_state()
