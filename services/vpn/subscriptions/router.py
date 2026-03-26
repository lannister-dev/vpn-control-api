from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import PlainTextResponse
from services.auth.dependencies import admin_auth

from services.vpn.subscriptions.adapter import SubscriptionPublicAdapter
from services.vpn.subscriptions.dependencies import get_subscription_public_adapter
from services.vpn.subscriptions.schemas import (
    SubscriptionCreateIn,
    SubscriptionCreatedOut,
    SubscriptionDeviceOut,
    SubscriptionOut,
    SubscriptionRotateOut,
)
from services.vpn.subscriptions.exceptions import (
    SubscriptionNotFound,
    SubscriptionInactive,
    SubscriptionExpired,
    SubscriptionTokenExpired,
    SubscriptionRateLimited,
    SubscriptionBuild,
    SubscriptionHwidRequired,
    SubscriptionDeviceLimitReached,
)
from services.vpn.subscriptions.service import get_subscription_service, SubscriptionService
from shared.monitoring.metrics import SUBSCRIPTION_REQUEST_TOTAL

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


#================= PUBLIC =========================

@router.get(
    "/sub/{token}",
    response_class=PlainTextResponse,
    summary="Get VPN subscription config",
    description=(
            "Public endpoint for VPN clients.\n\n"
            "Returns a plain-text list of VLESS URIs (newline separated).\n"
            "Supports ETag / If-None-Match for efficient polling.\n\n"
            "**HWID:** required via configured header.\n"
            "**Authentication:** none (token is the secret).\n"
            "**Rate limit:** enforced per subscription."
    ),
    responses={
        200: {"description": "Subscription config (text/plain)"},
        304: {"description": "Not modified (ETag match)"},
        403: {"description": "Subscription inactive / expired / token expired"},
        404: {"description": "Subscription not found"},
        429: {"description": "Rate limit exceeded"},
        503: {"description": "No available nodes/configs to build subscription"},
        500: {"description": "Failed to build subscription config"},
    },
)
async def get_subscription_config(
        token: str,
        request: Request,
        service: SubscriptionService = Depends(get_subscription_service),
        adapter: SubscriptionPublicAdapter = Depends(get_subscription_public_adapter),
):
    try:
        hwid = request.headers.get(adapter.hwid_header)
        user_agent = request.headers.get("user-agent")
        if_none_match = request.headers.get("if-none-match")
        if adapter.should_disable_not_modified(user_agent=user_agent):
            if_none_match = None

        payload, etag, not_modified, user_info = await service.build_payload(
            raw_token=token,
            hwid=hwid,
            user_agent=user_agent,
            if_none_match=if_none_match,
        )
        public_response = adapter.build_success_response(
            etag=etag,
            payload=payload,
            not_modified=not_modified,
            user_info=user_info,
            user_agent=user_agent,
        )
        SUBSCRIPTION_REQUEST_TOTAL.labels(result=public_response.metric_result).inc()
        if public_response.payload is None:
            return Response(status_code=public_response.status_code, headers=public_response.headers)

        return PlainTextResponse(
            content=public_response.payload,
            status_code=public_response.status_code,
            headers=public_response.headers,
        )
    except (
            SubscriptionNotFound,
            SubscriptionHwidRequired,
            SubscriptionDeviceLimitReached,
            SubscriptionInactive,
            SubscriptionExpired,
            SubscriptionTokenExpired,
            SubscriptionRateLimited,
            SubscriptionBuild,
    ) as exc:
        mapped = adapter.map_error(exc)
        SUBSCRIPTION_REQUEST_TOTAL.labels(result=mapped.metric_result).inc()
        raise HTTPException(status_code=mapped.status_code, detail=mapped.detail)


#================== ADMINS ==================

@router.post(
    "",
    response_model=SubscriptionCreatedOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create subscription",
    description="Create VPN subscription with HWID and generate an access token.",
    dependencies=[Depends(admin_auth)],
    responses={
        404: {"description": "User not found"},
    }
)
async def create_subscription(
        data: SubscriptionCreateIn,
        service: SubscriptionService = Depends(get_subscription_service),
):
    return await service.create(data)


@router.get(
    "/by-user/{user_id}",
    response_model=list[SubscriptionOut],
    status_code=status.HTTP_200_OK,
    summary="List subscriptions by user",
    dependencies=[Depends(admin_auth)],
)
async def list_subscriptions_by_user(
        user_id: UUID,
        active_only: bool = False,
        service: SubscriptionService = Depends(get_subscription_service),
):
    return await service.list_subscriptions_by_user(user_id=user_id, active_only=active_only)


@router.get(
    "/{subscription_id}",
    response_model=SubscriptionOut,
    status_code=status.HTTP_200_OK,
    summary="Get subscription by id",
    dependencies=[Depends(admin_auth)],
)
async def get_subscription_by_id(
        subscription_id: UUID,
        service: SubscriptionService = Depends(get_subscription_service),
):
    try:
        return await service.get_subscription(subscription_id)
    except SubscriptionNotFound:
        raise HTTPException(status_code=404, detail="Subscription not found")


@router.post(
    "/{subscription_id}/rotate-token",
    response_model=SubscriptionRotateOut,
    summary="Rotate subscription token",
    description=(
        "Generate a new access token for subscription.\n"
        "Old token may remain valid for a grace period (configured in service)."
    ),
    dependencies=[Depends(admin_auth)],
)
async def rotate_subscription_token(
        subscription_id: UUID,
        service: SubscriptionService = Depends(get_subscription_service),
):
    try:
        return await service.rotate_token(subscription_id)
    except SubscriptionNotFound:
        raise HTTPException(status_code=404, detail="Subscription not found")


@router.post(
    "/{subscription_id}/activate",
    status_code=status.HTTP_200_OK,
    summary="Activate subscription",
    dependencies=[Depends(admin_auth)],
)
async def activate_subscription(
        subscription_id: UUID,
        service: SubscriptionService = Depends(get_subscription_service),
):
    try:
        restored_keys = await service.activate(subscription_id)
        return {"status": "active", "restored_keys": restored_keys}
    except SubscriptionNotFound:
        raise HTTPException(status_code=404, detail="Subscription not found")


@router.post(
    "/{subscription_id}/deactivate",
    status_code=status.HTTP_200_OK,
    summary="Deactivate subscription",
    dependencies=[Depends(admin_auth)],
)
async def deactivate_subscription(
        subscription_id: UUID,
        service: SubscriptionService = Depends(get_subscription_service),
):
    try:
        revoked_keys = await service.deactivate(subscription_id)
        return {"status": "inactive", "revoked_keys": revoked_keys}
    except SubscriptionNotFound:
        raise HTTPException(status_code=404, detail="Subscription not found")


@router.get(
    "/{subscription_id}/devices",
    response_model=list[SubscriptionDeviceOut],
    status_code=status.HTTP_200_OK,
    summary="List subscription devices",
    dependencies=[Depends(admin_auth)],
)
async def list_subscription_devices(
        subscription_id: UUID,
        active_only: bool = False,
        service: SubscriptionService = Depends(get_subscription_service),
):
    try:
        return await service.list_devices(subscription_id, active_only=active_only)
    except SubscriptionNotFound:
        raise HTTPException(status_code=404, detail="Subscription not found")


@router.post(
    "/{subscription_id}/devices/{device_id}/revoke",
    status_code=status.HTTP_200_OK,
    summary="Revoke one device and free slot",
    dependencies=[Depends(admin_auth)],
)
async def revoke_subscription_device(
        subscription_id: UUID,
        device_id: UUID,
        service: SubscriptionService = Depends(get_subscription_service),
):
    try:
        changed = await service.revoke_device(subscription_id, device_id)
        return {"status": "revoked_device", "revoked_key": changed}
    except SubscriptionNotFound:
        raise HTTPException(status_code=404, detail="Subscription not found")
