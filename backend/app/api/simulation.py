"""Data-driven simulation scenario endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.schemas import ActivateSimulationRequest, SimulationScenarioSummary, SystemState
from app.state import (
    SimulationModeDisabledError,
    UnknownScenarioError,
    application_state,
)


router = APIRouter(prefix="/simulation", tags=["simulation"])


@router.get("/scenarios", response_model=list[SimulationScenarioSummary])
def list_scenarios() -> list[SimulationScenarioSummary]:
    return list(application_state.list_scenarios())


@router.post("/activate", response_model=SystemState)
@router.post("/load", response_model=SystemState)
def load_scenario(request: ActivateSimulationRequest) -> SystemState:
    try:
        return application_state.load_scenario(request.scenario_id)
    except UnknownScenarioError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scenario not found") from error
    except SimulationModeDisabledError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/reset", response_model=SystemState)
def reset_scenario() -> SystemState:
    return application_state.reset()
