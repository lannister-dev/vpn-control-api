from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from services.auth.dependencies import admin_auth, current_admin_user_id
from services.promo.exceptions import (
    PromoCodeExists,
    PromoError,
    PromoNotFound,
)
from services.promo.schemas import (
    PromoActivationListOut,
    PromoCodeCreateIn,
    PromoCodeListOut,
    PromoCodeOut,
    PromoCodeUpdateIn,
    PromoQuoteOut,
    PromoStatsOut,
    PromoValidateIn,
)
from services.promo.service import PromoService, get_promo_service

router = APIRouter(
    prefix="/promo", tags=["Promo"], dependencies=[Depends(admin_auth)]
)


@router.get("", response_model=PromoCodeListOut, summary="List promo codes")
async def list_promos(service: PromoService = Depends(get_promo_service)):
    return await service.list_promos()


@router.post(
    "", response_model=PromoCodeOut, status_code=status.HTTP_201_CREATED,
    summary="Create a promo code",
)
async def create_promo(
    data: PromoCodeCreateIn,
    service: PromoService = Depends(get_promo_service),
    actor_admin_id: UUID | None = Depends(current_admin_user_id),
):
    try:
        return await service.create_promo(data, actor_admin_id=actor_admin_id)
    except PromoCodeExists as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.patch("/{promo_id}", response_model=PromoCodeOut, summary="Update a promo code")
async def update_promo(
    promo_id: UUID,
    data: PromoCodeUpdateIn,
    service: PromoService = Depends(get_promo_service),
):
    try:
        return await service.update_promo(promo_id, data)
    except PromoNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/{promo_id}", status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a promo code",
)
async def delete_promo(
    promo_id: UUID, service: PromoService = Depends(get_promo_service)
):
    try:
        await service.delete_promo(promo_id)
    except PromoNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{promo_id}/activations", response_model=PromoActivationListOut,
    summary="Promo activation ledger",
)
async def list_activations(
    promo_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: PromoService = Depends(get_promo_service),
):
    return await service.list_activations(promo_id, limit=limit, offset=offset)


@router.get(
    "/{promo_id}/stats", response_model=PromoStatsOut,
    summary="Promo activation analytics",
)
async def promo_stats(
    promo_id: UUID, service: PromoService = Depends(get_promo_service)
):
    try:
        return await service.stats(promo_id)
    except PromoNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/validate", response_model=PromoQuoteOut,
    summary="Validate a promo code and preview the discount",
)
async def validate_promo(
    data: PromoValidateIn,
    service: PromoService = Depends(get_promo_service),
):
    try:
        return await service.validate_and_quote(
            code=data.code,
            user_id=data.user_id,
            plan_id=data.plan_id,
            order_type=data.order_type,
            amount_rub=data.amount_rub,
        )
    except PromoError as e:
        raise HTTPException(status_code=422, detail=str(e))
