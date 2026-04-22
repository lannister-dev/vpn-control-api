from fastapi import APIRouter, Depends, status

from services.auth.dependencies import admin_auth
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
    service: ProbePolicyService = Depends(get_probe_policy_service),
) -> ProbePolicyOut:
    return await service.update(data)
