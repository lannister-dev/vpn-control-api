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
    SubscriptionRotateOut,
)
from services.vpn.subscriptions.exceptions import (
    SubscriptionNotFound,
    SubscriptionInactive,
    SubscriptionExpired,
    SubscriptionTokenExpired,
    SubscriptionRateLimited,
    SubscriptionBuild,
)
from services.vpn.subscriptions.service import get_subscription_service, SubscriptionService

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
        500: {"description": "Failed to build subscription config"},
    },
)
async def get_subscription_config(
        token: str,
        request: Request,
        service: SubscriptionService = Depends(get_subscription_service),
):
    try:
        payload, etag, not_modified = await service.build_payload(
            raw_token=token,
            if_none_match=request.headers.get("if-none-match"),
        )
        if not_modified:
            return PlainTextResponse(status_code=status.HTTP_304_NOT_MODIFIED)

        return PlainTextResponse(
            content=payload, headers={"ETag": etag}
        )

    except SubscriptionNotFound:
        raise HTTPException(status_code=404, detail="Subscription not found")

    except (SubscriptionInactive, SubscriptionExpired, SubscriptionTokenExpired):
        raise HTTPException(status_code=403, detail="Subscription is not active")

    except SubscriptionRateLimited:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    except SubscriptionBuild as exc:
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
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Activate subscription",
    dependencies=[Depends(admin_auth)],
)
async def activate_subscription(
        subscription_id: UUID,
        service: SubscriptionService = Depends(get_subscription_service),
):
    try:
        await service.activate(subscription_id)
    except SubscriptionNotFound:
        raise HTTPException(status_code=404, detail="Subscription not found")


@router.post(
    "/{subscription_id}/deactivate",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate subscription",
    dependencies=[Depends(admin_auth)],
)
async def deactivate_subscription(
        subscription_id: UUID,
        service: SubscriptionService = Depends(get_subscription_service),
):
    try:
        await service.deactivate(subscription_id)
    except SubscriptionNotFound:
        raise HTTPException(status_code=404, detail="Subscription not found")
