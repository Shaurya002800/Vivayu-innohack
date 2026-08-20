"""Read-only crop profile and derived zone crop-context endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.schemas import CropProfile
from app.services.crop_service import UnknownCropError, crop_service


router = APIRouter(prefix="/crops", tags=["crops"])


@router.get("", response_model=list[CropProfile])
def list_crop_profiles() -> tuple[CropProfile, ...]:
    return crop_service.list_profiles()


@router.get("/{crop_id}", response_model=CropProfile)
def get_crop_profile(crop_id: str) -> CropProfile:
    try:
        return crop_service.get_profile(crop_id)
    except UnknownCropError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
