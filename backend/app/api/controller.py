"""Minimal controller safety API; Milestone 10 exposes no start controls."""

from fastapi import APIRouter, HTTPException, status

from app.schemas import CommandRecord
from app.services.serial_bridge import (
    CommandHistoryFullError,
    CommandUnavailableError,
    serial_bridge,
)


router = APIRouter(tags=["controller"])


@router.post("/system/stop-all", response_model=CommandRecord)
def emergency_stop() -> CommandRecord:
    """Send or safely queue the highest-priority STOP_ALL command."""

    try:
        return serial_bridge.emergency_stop()
    except CommandUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except CommandHistoryFullError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
