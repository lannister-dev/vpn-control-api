from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)

from services.auth.dependencies import admin_auth
from services.config import get_settings
from services.scenarios.schemas import (
    ScenarioCampaignIn,
    ScenarioCampaignListOut,
    ScenarioCampaignOut,
    ScenarioCampaignPatch,
    ScenarioStatsOut,
)
from services.scenarios.service import ScenarioService, get_scenario_service
from shared.s3 import S3Client

router = APIRouter(prefix="/scenarios", tags=["Scenarios"], dependencies=[Depends(admin_auth)])


@router.get("/campaigns", response_model=ScenarioCampaignListOut)
async def list_campaigns(service: ScenarioService = Depends(get_scenario_service)):
    return await service.list_campaigns()


@router.get("/stats", response_model=ScenarioStatsOut)
async def scenario_stats(service: ScenarioService = Depends(get_scenario_service)):
    return await service.stats()


@router.post("/upload")
async def scenario_upload(file: UploadFile = File(...)):
    settings = get_settings()
    if not settings.s3.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="S3 не настроен — загрузка медиа недоступна",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Пустой файл")
    ct = file.content_type or "application/octet-stream"
    kind = (
        "image" if ct.startswith("image/")
        else "video" if ct.startswith("video/")
        else "document"
    )
    ext = (file.filename or "").rsplit(".", 1)
    suffix = f".{ext[1]}" if len(ext) == 2 else ""
    key = f"scenarios/{uuid4().hex}{suffix}"
    up = await S3Client(settings.s3).upload_bytes(
        key=key, data=data, content_type=ct, cache_control="public, max-age=2592000"
    )
    return {"media_kind": kind, "media_url": up.public_url}


@router.post(
    "/campaigns",
    response_model=ScenarioCampaignOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_campaign(
    payload: ScenarioCampaignIn,
    service: ScenarioService = Depends(get_scenario_service),
):
    return await service.create_campaign(payload)


@router.patch("/campaigns/{campaign_id}", response_model=ScenarioCampaignOut)
async def patch_campaign(
    campaign_id: UUID,
    payload: ScenarioCampaignPatch,
    service: ScenarioService = Depends(get_scenario_service),
):
    out = await service.set_active(campaign_id, payload.is_active)
    if out is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return out


@router.put("/campaigns/{campaign_id}", response_model=ScenarioCampaignOut)
async def update_campaign(
    campaign_id: UUID,
    payload: ScenarioCampaignIn,
    service: ScenarioService = Depends(get_scenario_service),
):
    out = await service.update_campaign(campaign_id, payload)
    if out is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return out


@router.delete("/campaigns/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: UUID,
    service: ScenarioService = Depends(get_scenario_service),
):
    if not await service.delete_campaign(campaign_id):
        raise HTTPException(status_code=404, detail="Campaign not found")
