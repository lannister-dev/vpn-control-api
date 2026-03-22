from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from services.auth.dependencies import admin_auth, probe_auth
from services.probe.drain_service import ProbeDrainService, get_probe_drain_service
from services.probe.ingestion_service import ProbeIngestionService, get_probe_ingestion_service
from services.probe.schemas import (
    ProbeAutoDrainMigrateIn,
    ProbeAutoDrainMigrateOut,
    ProbeCleanupOut,
    ProbeDrainMigrateIn,
    ProbeDrainMigrateOut,
    ProbeReportIn,
    ProbeReportOut,
    ProbeTargetOut,
)

router = APIRouter(prefix="/probe", tags=["Probe"])


@router.post(
    "/report",
    response_model=ProbeReportOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(probe_auth)],
    summary="Ingest external probe report",
)
async def report_probe(
        payload: ProbeReportIn,
        service: ProbeIngestionService = Depends(get_probe_ingestion_service),
):
    return await service.report(payload)


@router.get(
    "/targets",
    response_model=list[ProbeTargetOut],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(probe_auth)],
    summary="List probe targets",
)
async def list_probe_targets(
        include_draining: bool = Query(default=False),
        include_disabled: bool = Query(default=False),
        service: ProbeIngestionService = Depends(get_probe_ingestion_service),
):
    return await service.list_targets(
        include_draining=include_draining,
        include_disabled=include_disabled,
    )


@router.get(
    "/reports/recent",
    response_model=list[ProbeReportOut],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(admin_auth)],
    summary="List recent probe reports",
)
async def list_recent_probe_reports(
        limit: int = Query(default=100, ge=1, le=1000),
        node_id: UUID | None = Query(default=None),
        route_id: UUID | None = Query(default=None),
        source: str | None = Query(default=None, max_length=64),
        service: ProbeIngestionService = Depends(get_probe_ingestion_service),
):
    return await service.list_recent(limit=limit, node_id=node_id, route_id=route_id, source=source)


@router.post(
    "/admin/cleanup-old-signals",
    response_model=ProbeCleanupOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(admin_auth)],
    summary="Delete probe signals older than retention period",
)
async def cleanup_old_probe_signals(
        service: ProbeIngestionService = Depends(get_probe_ingestion_service),
):
    deleted = await service.cleanup_old_signals()
    return ProbeCleanupOut(
        deleted=deleted,
        retention_days=service.retention_days,
    )


@router.post(
    "/admin/drain-and-migrate-backend",
    response_model=ProbeDrainMigrateOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(admin_auth)],
    summary="Drain backend and migrate placements based on latest probe failure",
)
async def drain_and_migrate_backend_from_probe(
        payload: ProbeDrainMigrateIn,
        service: ProbeDrainService = Depends(get_probe_drain_service),
):
    return await service.drain_and_migrate_backend(payload)


@router.post(
    "/admin/auto-drain-migrate-backends",
    response_model=ProbeAutoDrainMigrateOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(admin_auth)],
    summary="Auto-evaluate backends by probe policy and drain+migrate eligible nodes",
)
async def auto_drain_and_migrate_backends_from_probe(
        payload: ProbeAutoDrainMigrateIn,
        service: ProbeDrainService = Depends(get_probe_drain_service),
):
    return await service.auto_drain_and_migrate_backends(payload)
