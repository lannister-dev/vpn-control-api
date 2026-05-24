from fastapi import APIRouter, Depends, status

from services.admin.audit.service import AdminAuditService, get_admin_audit_service
from services.auth.dependencies import admin_auth, current_admin_actor
from services.traffic.policy.schemas import TrafficPolicyOut, TrafficPolicyUpdateIn
from services.traffic.policy.service import TrafficPolicyService, get_traffic_policy_service

router = APIRouter(
    prefix="/admin/traffic/policy",
    tags=["Admin Traffic Policy"],
    dependencies=[Depends(admin_auth)],
)


@router.get(
    "",
    response_model=TrafficPolicyOut,
    status_code=status.HTTP_200_OK,
    summary="Get current traffic cleanup policy",
)
async def get_policy(
    service: TrafficPolicyService = Depends(get_traffic_policy_service),
) -> TrafficPolicyOut:
    return await service.get()


@router.patch(
    "",
    response_model=TrafficPolicyOut,
    status_code=status.HTTP_200_OK,
    summary="Partially update traffic policy",
)
async def update_policy(
    data: TrafficPolicyUpdateIn,
    actor: str = Depends(current_admin_actor),
    service: TrafficPolicyService = Depends(get_traffic_policy_service),
    audit: AdminAuditService = Depends(get_admin_audit_service),
) -> TrafficPolicyOut:
    changed = data.model_dump(exclude_unset=True)
    result = await service.update(data)
    if changed:
        await audit.record(
            actor=actor,
            action="traffic_policy_update",
            target="traffic_policy",
            summary=f"updated {len(changed)} field(s): {', '.join(sorted(changed.keys()))}",
            details={k: (str(v) if hasattr(v, 'hex') else v) for k, v in changed.items()},
        )
    return result
