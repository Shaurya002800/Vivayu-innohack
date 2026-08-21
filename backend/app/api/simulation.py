"""Data-driven simulation scenario endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.schemas import (
    ActivateSimulationRequest,
    DashboardSnapshot,
    PrototypeIrrigationParameters,
    PrototypeWaterQualityParameters,
    SimulationScenarioSummary,
    SystemState,
)
from app.services.dashboard_snapshot import build_dashboard_snapshot
from app.state import (
    ApplicationStateStore,
    UnknownScenarioError,
    application_state,
    simulation_state_store,
)


router = APIRouter(prefix="/simulation", tags=["simulation"])


@router.get("/scenarios", response_model=list[SimulationScenarioSummary])
def list_scenarios() -> list[SimulationScenarioSummary]:
    return list(simulation_state_store().list_scenarios())


def _configure_demo_calibration(store: ApplicationStateStore) -> None:
    """Apply explicit prototype configuration only inside the demo state."""

    irrigation = PrototypeIrrigationParameters(
        target_moisture_pct=45,
        critical_moisture_pct=25,
        ml_per_moisture_point=20,
    )
    water_quality = PrototypeWaterQualityParameters(max_irrigation_tds_ppm=450)
    for zone_id in ("A", "B"):
        store.update_irrigation_parameters(zone_id, irrigation)
        store.update_water_quality_parameters(zone_id, water_quality)


@router.post("/activate", response_model=SystemState)
@router.post("/load", response_model=SystemState)
def load_scenario(request: ActivateSimulationRequest) -> SystemState:
    store = simulation_state_store()
    try:
        store.load_scenario(request.scenario_id)
        if store is not application_state:
            _configure_demo_calibration(store)
        return store.get_state()
    except UnknownScenarioError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scenario not found") from error


@router.post("/reset", response_model=SystemState)
def reset_scenario() -> SystemState:
    return simulation_state_store().reset()


@router.get("/snapshot", response_model=DashboardSnapshot)
def get_demo_snapshot() -> DashboardSnapshot:
    """Return demo calculations without reading or replacing live hardware state."""

    return build_dashboard_snapshot(simulation_state_store().get_state())
