"""Build one read-only dashboard projection from an explicitly supplied state."""

from app.schemas import (
    DashboardSnapshot,
    IrrigationNeedResult,
    SystemState,
    WaterQualityResult,
    ZoneAllocationInput,
    ZoneId,
)
from app.services.freshwater_allocator import (
    allocate_freshwater,
    freshwater_allocation_policy,
)
from app.services.irrigation_need import (
    calculate_irrigation_need,
    irrigation_need_policy,
)
from app.services.water_quality import (
    calculate_water_quality_strategy,
    water_quality_policy,
)


def build_dashboard_snapshot(state: SystemState) -> DashboardSnapshot:
    """Run frozen M4/M5/M6 preview functions without mutating the source store."""

    irrigation: dict[ZoneId, IrrigationNeedResult] = {}
    water_quality: dict[ZoneId, WaterQualityResult] = {}
    zone_inputs: dict[ZoneId, ZoneAllocationInput] = {}

    for zone_id in ("A", "B"):
        zone = state.zones[zone_id]
        irrigation_result = calculate_irrigation_need(
            zone,
            state.weather,
            irrigation_need_policy,
        )
        configured_max_tds_ppm = (
            zone.crop_context.max_irrigation_tds_ppm
            if zone.crop_context is not None
            else zone.config.water_quality_parameters.max_irrigation_tds_ppm
        )
        quality_result = calculate_water_quality_strategy(
            zone_id=zone_id,
            requested_water_ml=irrigation_result.requested_water_ml,
            fresh_source=state.water.fresh,
            marginal_source=state.water.marginal,
            configured_max_tds_ppm=configured_max_tds_ppm,
            policy=water_quality_policy,
        )
        irrigation[zone_id] = irrigation_result
        water_quality[zone_id] = quality_result
        zone_inputs[zone_id] = ZoneAllocationInput(
            zone_id=zone_id,
            irrigation_need=irrigation_result,
            water_quality=quality_result,
        )

    allocation = allocate_freshwater(
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
    return DashboardSnapshot(
        state=state,
        irrigation=irrigation,
        water_quality=water_quality,
        allocation=allocation,
    )
