from fastapi import APIRouter, Depends, status

from services.admin_audit.service import AdminAuditService, get_admin_audit_service
from services.auth.dependencies import admin_auth, current_admin_actor
from services.probe.policy.schemas import ProbePolicyOut, ProbePolicyUpdateIn
from services.probe.policy.service import ProbePolicyService, get_probe_policy_service


router = APIRouter(
    prefix="/admin/probe/policy",
    tags=["Admin Probe Policy"],
    dependencies=[Depends(admin_auth)],
)


@router.get(
    "",
    response_model=ProbePolicyOut,
    status_code=status.HTTP_200_OK,
    summary="Get current probe policy",
)
async def get_policy(
    service: ProbePolicyService = Depends(get_probe_policy_service),
) -> ProbePolicyOut:
    return await service.get()


@router.patch(
    "",
    response_model=ProbePolicyOut,
    status_code=status.HTTP_200_OK,
    summary="Partially update probe policy",
)
async def update_policy(
    data: ProbePolicyUpdateIn,
    actor: str = Depends(current_admin_actor),
    service: ProbePolicyService = Depends(get_probe_policy_service),
    audit: AdminAuditService = Depends(get_admin_audit_service),
) -> ProbePolicyOut:
    changed = data.model_dump(exclude_unset=True)
    result = await service.update(data)
    if changed:
        await audit.record(
            actor=actor,
            action="probe_policy_update",
            target="probe_policy",
            summary=f"updated {len(changed)} field(s): {', '.join(sorted(changed.keys()))}",
            details={k: _jsonable(v) for k, v in changed.items()},
        )
    return result


def _jsonable(v):
    if hasattr(v, "hex"):
        return str(v)
    return v
