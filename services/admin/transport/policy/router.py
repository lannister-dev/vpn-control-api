from fastapi import APIRouter, Depends, status

from services.admin.audit.service import AdminAuditService, get_admin_audit_service
from services.admin.transport.policy.schemas import TransportPolicyOut, TransportPolicyUpdateIn
from services.admin.transport.policy.service import TransportPolicyService, get_transport_policy_service
from services.auth.dependencies import admin_auth, current_admin_actor

router = APIRouter(
    prefix="/admin/transport/policy",
    tags=["Admin Transport Policy"],
    dependencies=[Depends(admin_auth)],
)


@router.get(
    "",
    response_model=TransportPolicyOut,
    status_code=status.HTTP_200_OK,
    summary="Get current transport cleanup policy",
)
async def get_policy(
    service: TransportPolicyService = Depends(get_transport_policy_service),
) -> TransportPolicyOut:
    return await service.get()


@router.patch(
    "",
    response_model=TransportPolicyOut,
    status_code=status.HTTP_200_OK,
    summary="Partially update transport policy",
)
async def update_policy(
    data: TransportPolicyUpdateIn,
    actor: str = Depends(current_admin_actor),
    service: TransportPolicyService = Depends(get_transport_policy_service),
    audit: AdminAuditService = Depends(get_admin_audit_service),
) -> TransportPolicyOut:
    changed = data.model_dump(exclude_unset=True)
    result = await service.update(data)
    if changed:
        await audit.record(
            actor=actor,
            action="transport_policy_update",
            target="transport_policy",
            summary=f"updated {len(changed)} field(s): {', '.join(sorted(changed.keys()))}",
            details={k: (str(v) if hasattr(v, 'hex') else v) for k, v in changed.items()},
        )
    return result
