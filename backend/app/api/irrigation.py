"""Read/configure prototype parameters and calculate side-effect-free previews."""

from fastapi import APIRouter

from app.schemas import (
    IrrigationNeedResult,
    PrototypeIrrigationParameters,
    ZoneId,
)
from app.services.irrigation_need import calculate_irrigation_need, irrigation_need_policy
from app.state import application_state


router = APIRouter(prefix="/zones", tags=["irrigation"])


@router.get(
    "/{zone_id}/irrigation-parameters",
    response_model=PrototypeIrrigationParameters,
)
def get_irrigation_parameters(zone_id: ZoneId) -> PrototypeIrrigationParameters:
    return application_state.get_irrigation_parameters(zone_id)


@router.put(
    "/{zone_id}/irrigation-parameters",
    response_model=PrototypeIrrigationParameters,
)
def update_irrigation_parameters(
    zone_id: ZoneId,
    parameters: PrototypeIrrigationParameters,
) -> PrototypeIrrigationParameters:
    zone = application_state.update_irrigation_parameters(zone_id, parameters)
    return zone.config.irrigation_parameters


@router.get("/{zone_id}/irrigation-need", response_model=IrrigationNeedResult)
def preview_irrigation_need(zone_id: ZoneId) -> IrrigationNeedResult:
    state = application_state.get_state()
    return calculate_irrigation_need(
        state.zones[zone_id],
        state.weather,
        irrigation_need_policy,
    )
