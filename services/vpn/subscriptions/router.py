from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import PlainTextResponse
from services.auth.dependencies import admin_auth

from services.vpn.subscriptions.schemas import (
    SubscriptionCreateIn,
    SubscriptionCreatedOut,
    SubscriptionDeviceOut,
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
from services.config import get_settings

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
):
    try:
        settings = get_settings()
        hwid = request.headers.get(settings.subscriptions.hwid_header)
        user_agent = request.headers.get("user-agent")

        payload, etag, not_modified = await service.build_payload(
            raw_token=token,
            hwid=hwid,
            user_agent=user_agent,
            if_none_match=request.headers.get("if-none-match"),
        )
        if not_modified:
            SUBSCRIPTION_REQUEST_TOTAL.labels(result="not_modified").inc()
            return PlainTextResponse(status_code=status.HTTP_304_NOT_MODIFIED)

        SUBSCRIPTION_REQUEST_TOTAL.labels(result="success").inc()
        return PlainTextResponse(
            content=payload, headers={"ETag": etag}
        )

    except SubscriptionNotFound:
        SUBSCRIPTION_REQUEST_TOTAL.labels(result="not_found").inc()
        raise HTTPException(status_code=404, detail="Subscription not found")

    except SubscriptionHwidRequired:
        SUBSCRIPTION_REQUEST_TOTAL.labels(result="hwid_required").inc()
        raise HTTPException(status_code=404, detail="Subscription not found")

    except SubscriptionDeviceLimitReached:
        SUBSCRIPTION_REQUEST_TOTAL.labels(result="device_limit").inc()
        raise HTTPException(status_code=403, detail="Device limit reached")

    except SubscriptionInactive:
        SUBSCRIPTION_REQUEST_TOTAL.labels(result="inactive").inc()
        raise HTTPException(status_code=403, detail="Subscription is not active")

    except SubscriptionExpired:
        SUBSCRIPTION_REQUEST_TOTAL.labels(result="expired").inc()
        raise HTTPException(status_code=403, detail="Subscription is not active")

    except SubscriptionTokenExpired:
        SUBSCRIPTION_REQUEST_TOTAL.labels(result="token_expired").inc()
        raise HTTPException(status_code=403, detail="Subscription is not active")

    except SubscriptionRateLimited:
        SUBSCRIPTION_REQUEST_TOTAL.labels(result="rate_limited").inc()
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    except SubscriptionBuild as exc:
        SUBSCRIPTION_REQUEST_TOTAL.labels(result="build_error").inc()
        msg = str(exc)
        if msg.startswith("No available "):
            raise HTTPException(
                status_code=503,
                detail=f"Failed to build subscription: {exc}",
            )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to build subscription: {exc}"
        )


#================== ADMINS ==================

@router.post(
    "",
    response_model=SubscriptionCreatedOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create subscription",
    description="Create a new VPN subscription and generate an access token.",
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


@router.post(
    "/{subscription_id}/bind-root-key/{vpn_key_id}",
    status_code=status.HTTP_200_OK,
    summary="Bind subscription to an existing key (legacy mode)",
    dependencies=[Depends(admin_auth)],
)
async def bind_subscription_root_key(
        subscription_id: UUID,
        vpn_key_id: UUID,
        service: SubscriptionService = Depends(get_subscription_service),
):
    await service.bind_root_key(subscription_id, vpn_key_id)
    return {"status": "bound_root_key"}


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
