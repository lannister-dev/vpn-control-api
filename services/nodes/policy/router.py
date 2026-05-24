from fastapi import APIRouter, Depends, status

from services.admin.audit.service import AdminAuditService, get_admin_audit_service
from services.auth.dependencies import admin_auth, current_admin_actor
from services.nodes.policy.schemas import NodePolicyOut, NodePolicyUpdateIn
from services.nodes.policy.service import NodePolicyService, get_node_policy_service

router = APIRouter(
    prefix="/admin/nodes/policy",
    tags=["Admin Nodes Policy"],
    dependencies=[Depends(admin_auth)],
)


@router.get(
    "",
    response_model=NodePolicyOut,
    status_code=status.HTTP_200_OK,
    summary="Get node management policy",
)
async def get_policy(
    service: NodePolicyService = Depends(get_node_policy_service),
) -> NodePolicyOut:
    return await service.get()


@router.patch(
    "",
    response_model=NodePolicyOut,
    status_code=status.HTTP_200_OK,
    summary="Partially update node policy",
)
async def update_policy(
    data: NodePolicyUpdateIn,
    actor: str = Depends(current_admin_actor),
    service: NodePolicyService = Depends(get_node_policy_service),
    audit: AdminAuditService = Depends(get_admin_audit_service),
) -> NodePolicyOut:
    changed = data.model_dump(exclude_unset=True)
    result = await service.update(data)
    if changed:
        await audit.record(
            actor=actor,
            action="node_policy_update",
            target="node_policy",
            summary=f"updated {len(changed)} field(s): {', '.join(sorted(changed.keys()))}",
            details={k: (str(v) if hasattr(v, 'hex') else v) for k, v in changed.items()},
        )
    return result
