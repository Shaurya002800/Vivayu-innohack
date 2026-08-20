"""Independent Zone A and Zone B configuration endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.schemas import CropContext, StageOverrideRequest, ZoneConfig, ZoneId, ZoneState
from app.services.crop_service import FutureSowingDateError, UnknownCropError
from app.state import UnknownZoneError, application_state


router = APIRouter(prefix="/zones", tags=["zones"])


@router.get("", response_model=dict[ZoneId, ZoneState])
def list_zones() -> dict[ZoneId, ZoneState]:
    return application_state.get_state().zones


@router.get("/{zone_id}", response_model=ZoneState)
def get_zone(zone_id: ZoneId) -> ZoneState:
    try:
        return application_state.get_zone(zone_id)
    except UnknownZoneError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="zone not found") from error


@router.get("/{zone_id}/crop-context", response_model=CropContext)
def get_zone_crop_context(zone_id: ZoneId) -> CropContext:
    context = application_state.get_zone(zone_id).crop_context
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="crop context is unavailable",
        )
    return context


@router.put("/{zone_id}/config", response_model=ZoneState)
def update_zone_config(zone_id: ZoneId, config: ZoneConfig) -> ZoneState:
    try:
        return application_state.update_zone_config(zone_id, config)
    except (FutureSowingDateError, UnknownCropError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/{zone_id}/stage-override", response_model=ZoneState)
def set_stage_override(zone_id: ZoneId, request: StageOverrideRequest) -> ZoneState:
    try:
        return application_state.set_manual_stage(zone_id, request.growth_stage)
    except (FutureSowingDateError, UnknownCropError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
