from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse, RedirectResponse

from services.auth.dependencies import admin_auth
from services.billing.dependencies import _required_redirect
from services.billing.exceptions import (
    InsufficientBalance,
    OrderExpired,
    OrderNotFound,
    PlanNotPurchasable,
    ProviderError,
    WebhookVerificationFailed,
)
from services.billing.schemas import (
    BalanceCreditIn,
    BalanceOut,
    OrderCreateIn,
    OrderListOut,
    OrderOut,
    TransactionListOut,
)
from services.billing.service import BillingService, get_billing_service
from services.billing.utils import map_provider_error_to_http_status
from services.config import get_settings

router = APIRouter(prefix="/billing", tags=["Billing"])


# ── Orders (admin auth) ─────────────────────────────────────

@router.post(
    "/orders",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create payment order",
    dependencies=[Depends(admin_auth)],
)
async def create_order(
    data: OrderCreateIn,
    service: BillingService = Depends(get_billing_service),
):
    try:
        return await service.create_order(data)
    except PlanNotPurchasable as e:
        raise HTTPException(status_code=422, detail=str(e))
    except InsufficientBalance as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ProviderError as e:
        raise HTTPException(status_code=map_provider_error_to_http_status(e), detail=str(e))
    except OrderNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/orders/{order_id}",
    response_model=OrderOut,
    summary="Get order by ID",
    dependencies=[Depends(admin_auth)],
)
async def get_order(
    order_id: UUID,
    service: BillingService = Depends(get_billing_service),
):
    try:
        return await service.get_order(order_id)
    except OrderNotFound:
        raise HTTPException(status_code=404, detail="Order not found")


@router.get(
    "/orders/user/{user_id}",
    response_model=OrderListOut,
    summary="List user orders",
    dependencies=[Depends(admin_auth)],
)
async def list_user_orders(
    user_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: BillingService = Depends(get_billing_service),
):
    return await service.list_user_orders(user_id, limit=limit, offset=offset)


# ── Webhooks (no auth — verified by provider signature) ──────

@router.post(
    "/webhooks/crypto",
    status_code=status.HTTP_200_OK,
    summary="Crypto payment webhook",
)
async def webhook_crypto(
    request: Request,
    service: BillingService = Depends(get_billing_service),
):
    try:
        await service.process_webhook("crypto", request)
        return {"status": "ok"}
    except WebhookVerificationFailed as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OrderNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except OrderExpired as e:
        raise HTTPException(status_code=410, detail=str(e))


@router.post(
    "/webhooks/platega",
    status_code=status.HTTP_200_OK,
    summary="Platega payment webhook",
)
async def webhook_platega(
    request: Request,
    service: BillingService = Depends(get_billing_service),
):
    try:
        await service.process_webhook("platega", request)
        return Response(status_code=status.HTTP_200_OK)
    except WebhookVerificationFailed as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OrderNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except OrderExpired as e:
        raise HTTPException(status_code=410, detail=str(e))


@router.get(
    "/platega/success",
    status_code=status.HTTP_200_OK,
    summary="Platega success return URL",
)
async def platega_success():
    cfg = get_settings().billing
    return _required_redirect(
        cfg.platega_success_redirect_url,
        setting_name="BILLING_PLATEGA_SUCCESS_REDIRECT_URL",
    )


@router.get(
    "/platega/fail",
    status_code=status.HTTP_200_OK,
    summary="Platega fail return URL",
)
async def platega_fail():
    cfg = get_settings().billing
    return _required_redirect(
        cfg.platega_fail_redirect_url,
        setting_name="BILLING_PLATEGA_FAIL_REDIRECT_URL",
    )


@router.api_route(
    "/webhooks/freekassa",
    methods=["GET", "POST"],
    status_code=status.HTTP_200_OK,
    summary="FreeKassa payment webhook",
)
async def webhook_freekassa(
    request: Request,
    service: BillingService = Depends(get_billing_service),
):
    try:
        await service.process_webhook("freekassa", request)
        return PlainTextResponse(content="YES", status_code=status.HTTP_200_OK)
    except WebhookVerificationFailed as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OrderNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except OrderExpired as e:
        raise HTTPException(status_code=410, detail=str(e))


@router.get(
    "/freekassa/success",
    status_code=status.HTTP_200_OK,
    summary="FreeKassa success return URL",
)
async def freekassa_success():
    cfg = get_settings().billing
    return _required_redirect(
        cfg.freekassa_success_redirect_url,
        setting_name="BILLING_FREEKASSA_SUCCESS_REDIRECT_URL",
    )


@router.get(
    "/freekassa/fail",
    status_code=status.HTTP_200_OK,
    summary="FreeKassa fail return URL",
)
async def freekassa_fail():
    cfg = get_settings().billing
    return _required_redirect(
        cfg.freekassa_fail_redirect_url,
        setting_name="BILLING_FREEKASSA_FAIL_REDIRECT_URL",
    )


# ── Balance (admin auth) ─────────────────────────────────────

@router.get(
    "/balance/{user_id}",
    response_model=BalanceOut,
    summary="Get user balance",
    dependencies=[Depends(admin_auth)],
)
async def get_balance(
    user_id: UUID,
    service: BillingService = Depends(get_billing_service),
):
    try:
        return await service.get_balance(user_id)
    except OrderNotFound:
        raise HTTPException(status_code=404, detail="User not found")


@router.post(
    "/balance/{user_id}/credit",
    response_model=BalanceOut,
    summary="Manual balance credit",
    dependencies=[Depends(admin_auth)],
)
async def credit_balance(
    user_id: UUID,
    data: BalanceCreditIn,
    service: BillingService = Depends(get_billing_service),
):
    try:
        return await service.credit_balance(user_id, data)
    except OrderNotFound:
        raise HTTPException(status_code=404, detail="User not found")


@router.get(
    "/transactions/{user_id}",
    response_model=TransactionListOut,
    summary="List user transactions",
    dependencies=[Depends(admin_auth)],
)
async def list_transactions(
    user_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: BillingService = Depends(get_billing_service),
):
    return await service.list_transactions(user_id, limit=limit, offset=offset)
