"""Prototype water-source management and side-effect-free quality previews."""

from fastapi import APIRouter, HTTPException, status

from app.schemas import (
    FreshwaterAllocationResult,
    PrototypeWaterQualityParameters,
    WaterQualityResult,
    WaterSourceId,
    WaterSourceState,
    WaterSourceUpdateRequest,
    WaterState,
    ZoneId,
    ZoneAllocationInput,
)
from app.services.freshwater_allocator import (
    allocate_freshwater,
    freshwater_allocation_policy,
)
from app.services.irrigation_need import calculate_irrigation_need, irrigation_need_policy
from app.services.water_quality import calculate_water_quality_strategy, water_quality_policy
from app.state import application_state


router = APIRouter(prefix="/water", tags=["water"])


@router.get("", response_model=WaterState)
def get_water_state() -> WaterState:
    return application_state.get_water()


@router.put("/sources/{source_id}", response_model=WaterSourceState)
def update_water_source(
    source_id: WaterSourceId,
    update: WaterSourceUpdateRequest,
) -> WaterSourceState:
    try:
        return application_state.update_water_source(source_id, update)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.get(
    "/zones/{zone_id}/constraint",
    response_model=PrototypeWaterQualityParameters,
)
def get_zone_water_quality_constraint(
    zone_id: ZoneId,
) -> PrototypeWaterQualityParameters:
    return application_state.get_water_quality_parameters(zone_id)


@router.put(
    "/zones/{zone_id}/constraint",
    response_model=PrototypeWaterQualityParameters,
)
def update_zone_water_quality_constraint(
    zone_id: ZoneId,
    parameters: PrototypeWaterQualityParameters,
) -> PrototypeWaterQualityParameters:
    zone = application_state.update_water_quality_parameters(zone_id, parameters)
    return zone.config.water_quality_parameters


@router.get("/zones/{zone_id}/strategy", response_model=WaterQualityResult)
def preview_zone_water_quality_strategy(zone_id: ZoneId) -> WaterQualityResult:
    state = application_state.get_state()
    zone = state.zones[zone_id]
    irrigation = calculate_irrigation_need(
        zone,
        state.weather,
        irrigation_need_policy,
    )
    configured_max_tds_ppm = (
        zone.crop_context.max_irrigation_tds_ppm
        if zone.crop_context is not None
        else zone.config.water_quality_parameters.max_irrigation_tds_ppm
    )
    return calculate_water_quality_strategy(
        zone_id=zone_id,
        requested_water_ml=irrigation.requested_water_ml,
        fresh_source=state.water.fresh,
        marginal_source=state.water.marginal,
        configured_max_tds_ppm=configured_max_tds_ppm,
        policy=water_quality_policy,
    )


@router.get("/allocation-preview", response_model=FreshwaterAllocationResult)
def preview_freshwater_allocation() -> FreshwaterAllocationResult:
    state = application_state.get_state()
    zone_inputs: dict[ZoneId, ZoneAllocationInput] = {}
    for zone_id in ("A", "B"):
        zone = state.zones[zone_id]
        irrigation = calculate_irrigation_need(
            zone,
            state.weather,
            irrigation_need_policy,
        )
        configured_max_tds_ppm = (
            zone.crop_context.max_irrigation_tds_ppm
            if zone.crop_context is not None
            else zone.config.water_quality_parameters.max_irrigation_tds_ppm
        )
        quality = calculate_water_quality_strategy(
            zone_id=zone_id,
            requested_water_ml=irrigation.requested_water_ml,
            fresh_source=state.water.fresh,
            marginal_source=state.water.marginal,
            configured_max_tds_ppm=configured_max_tds_ppm,
            policy=water_quality_policy,
        )
        zone_inputs[zone_id] = ZoneAllocationInput(
            zone_id=zone_id,
            irrigation_need=irrigation,
            water_quality=quality,
        )
    return allocate_freshwater(
        freshwater_available_ml=(
            state.water.fresh.available_l * 1000
            if state.water.fresh.available_l is not None
            else None
        ),
        marginal_available_ml=(
            state.water.marginal.available_l * 1000
            if state.water.marginal.available_l is not None
            else None
        ),
        zone_inputs=zone_inputs,
        policy=freshwater_allocation_policy,
    )
