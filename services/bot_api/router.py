from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from services.auth.dependencies import bot_auth
from services.referral.schemas import BotReferralApplyIn, BotReferralInfoOut

from .schemas import (
    BotDeviceSlotPurchaseIn,
    BotDevicesOut,
    BotOrderActionOut,
    BotOrderCreateIn,
    BotOrderHistoryOut,
    BotOrderUpdateIn,
    BotPlanListOut,
    BotRenewOfferOut,
    BotRenewOrderIn,
    BotSessionOut,
    BotSessionSyncIn,
    BotStarsConfirmIn,
    BotSubscriptionLinkOut,
    BotSubscriptionSummaryOut,
    BotSubscriptionTrafficIn,
    BotSubscriptionTrafficListOut,
    BotTopUpCreateIn,
    BotTrafficWarningBulkIn,
    BotTrafficWarningMarkIn,
)
from .service import BotApiService, get_bot_api_service

router = APIRouter(prefix="/bot", tags=["Bot"], dependencies=[Depends(bot_auth)])



@router.post(
    "/users/session",
    response_model=BotSessionOut,
    summary="Sync Telegram user and get dashboard snapshot for bot UI",
)
async def bot_sync_session(
    payload: BotSessionSyncIn,
    service: BotApiService = Depends(get_bot_api_service),
):
    return await service.sync_session(payload)


@router.get(
    "/plans",
    response_model=BotPlanListOut,
    summary="List active plans for Telegram bot",
)
async def bot_list_plans(
    telegram_id: int | None = None,
    service: BotApiService = Depends(get_bot_api_service),
):
    return await service.list_plans(telegram_id=telegram_id)


@router.post(
    "/users/session/accept-terms",
    response_model=BotSessionOut,
    summary="Accept terms for Telegram user and get updated dashboard snapshot",
)
async def bot_accept_terms(
    payload: BotSessionSyncIn,
    service: BotApiService = Depends(get_bot_api_service),
):
    return await service.accept_terms(payload)


@router.post(
    "/users/{telegram_id}/orders",
    response_model=BotOrderActionOut,
    summary="Create payment order for Telegram bot user",
)
async def bot_create_order(
    telegram_id: int,
    payload: BotOrderCreateIn,
    service: BotApiService = Depends(get_bot_api_service),
):
    return await service.create_order(telegram_id=telegram_id, payload=payload)


@router.get(
    "/users/{telegram_id}/orders/{order_id}",
    response_model=BotOrderActionOut,
    summary="Get payment order state for Telegram bot user",
)
async def bot_get_order(
    telegram_id: int,
    order_id: UUID,
    service: BotApiService = Depends(get_bot_api_service),
):
    return await service.get_order(telegram_id=telegram_id, order_id=order_id)


@router.patch(
    "/users/{telegram_id}/orders/{order_id}",
    summary="Update Telegram bot order metadata",
)
async def bot_update_order(
    telegram_id: int,
    order_id: UUID,
    payload: BotOrderUpdateIn,
    service: BotApiService = Depends(get_bot_api_service),
):
    await service.update_order_metadata(
        telegram_id=telegram_id,
        order_id=order_id,
        payload=payload,
    )
    return {"ok": True}


@router.post(
    "/users/{telegram_id}/orders/{order_id}/confirm-stars",
    response_model=BotOrderActionOut,
    summary="Confirm Telegram Stars payment after successful_payment",
)
async def bot_confirm_stars(
    telegram_id: int,
    order_id: UUID,
    payload: BotStarsConfirmIn,
    service: BotApiService = Depends(get_bot_api_service),
):
    return await service.confirm_stars_payment(
        telegram_id=telegram_id, order_id=order_id, payload=payload,
    )


@router.get(
    "/users/{telegram_id}/renew-offer",
    response_model=BotRenewOfferOut,
    summary="Get renewal offer for current Telegram bot subscription",
)
async def bot_get_renew_offer(
    telegram_id: int,
    service: BotApiService = Depends(get_bot_api_service),
):
    return await service.get_renew_offer(telegram_id=telegram_id)


@router.post(
    "/users/{telegram_id}/renew",
    response_model=BotOrderActionOut,
    summary="Create renewal order for current Telegram bot subscription",
)
async def bot_create_renew_order(
    telegram_id: int,
    payload: BotRenewOrderIn,
    service: BotApiService = Depends(get_bot_api_service),
):
    return await service.create_renew_order(telegram_id=telegram_id, payload=payload)


@router.get(
    "/users/{telegram_id}/orders",
    response_model=BotOrderHistoryOut,
    summary="List payment orders for Telegram bot user",
)
async def bot_list_orders(
    telegram_id: int,
    service: BotApiService = Depends(get_bot_api_service),
):
    return await service.list_user_orders(telegram_id=telegram_id)


@router.get(
    "/users/{telegram_id}/devices",
    response_model=BotDevicesOut,
    summary="List subscription devices for Telegram bot user",
)
async def bot_list_devices(
    telegram_id: int,
    service: BotApiService = Depends(get_bot_api_service),
):
    return await service.list_devices(telegram_id=telegram_id)


@router.post(
    "/users/{telegram_id}/devices/{device_id}/revoke",
    response_model=BotDevicesOut,
    summary="Revoke a subscription device for Telegram bot user",
)
async def bot_revoke_device(
    telegram_id: int,
    device_id: UUID,
    service: BotApiService = Depends(get_bot_api_service),
):
    return await service.revoke_device(telegram_id=telegram_id, device_id=device_id)


@router.post(
    "/users/{telegram_id}/device-slots",
    response_model=BotOrderActionOut,
    summary="Purchase additional device slots for Telegram bot user",
)
async def bot_purchase_device_slots(
    telegram_id: int,
    payload: BotDeviceSlotPurchaseIn,
    service: BotApiService = Depends(get_bot_api_service),
):
    return await service.purchase_device_slots(telegram_id=telegram_id, payload=payload)


@router.post(
    "/users/{telegram_id}/top-up",
    response_model=BotOrderActionOut,
    summary="Create balance top-up order for Telegram bot user",
)
async def bot_create_top_up_order(
    telegram_id: int,
    payload: BotTopUpCreateIn,
    service: BotApiService = Depends(get_bot_api_service),
):
    return await service.create_top_up_order(telegram_id=telegram_id, payload=payload)


@router.post(
    "/users/{telegram_id}/campaigns/migrate/claim",
    response_model=BotOrderActionOut,
    summary="Claim migration gift for Telegram bot user",
)
async def bot_claim_migration_gift(
    telegram_id: int,
    service: BotApiService = Depends(get_bot_api_service),
):
    return await service.claim_migration_gift(telegram_id=telegram_id)


@router.get(
    "/users/{telegram_id}/referral",
    response_model=BotReferralInfoOut,
    summary="Get referral info for Telegram bot user",
)
async def bot_get_referral_info(
    telegram_id: int,
    service: BotApiService = Depends(get_bot_api_service),
):
    return await service.get_referral_info(telegram_id=telegram_id)


@router.post(
    "/users/{telegram_id}/referral/apply",
    summary="Apply referral code for Telegram bot user",
)
async def bot_apply_referral(
    telegram_id: int,
    payload: BotReferralApplyIn,
    service: BotApiService = Depends(get_bot_api_service),
):
    from fastapi import HTTPException

    from services.referral.exceptions import (
        AlreadyReferred,
        ReferralCodeNotFound,
        ReferralNotEnabled,
        SelfReferralNotAllowed,
    )

    try:
        return await service.apply_referral(
            telegram_id=telegram_id, referral_code=payload.referral_code,
        )
    except ReferralNotEnabled:
        raise HTTPException(status_code=409, detail="Referral program is disabled")
    except ReferralCodeNotFound:
        raise HTTPException(status_code=404, detail="Referral code not found")
    except SelfReferralNotAllowed:
        raise HTTPException(status_code=409, detail="Cannot refer yourself")
    except AlreadyReferred:
        raise HTTPException(status_code=409, detail="Already referred")


@router.get(
    "/users/{telegram_id}/subscription",
    response_model=BotSubscriptionSummaryOut | None,
    summary="Read-only current subscription snapshot for Telegram bot user (no DB writes)",
)
async def bot_get_subscription_summary(
    telegram_id: int,
    service: BotApiService = Depends(get_bot_api_service),
):
    return await service.get_subscription_summary(telegram_id=telegram_id)


@router.post(
    "/subscriptions/traffic-check",
    response_model=BotSubscriptionTrafficListOut,
    summary="Batch traffic-check for many telegram_ids in one query (no ORM hydration)",
)
async def bot_subscriptions_traffic_check(
    payload: BotSubscriptionTrafficIn,
    service: BotApiService = Depends(get_bot_api_service),
):
    return await service.list_subscriptions_traffic(telegram_ids=payload.telegram_ids)


@router.post(
    "/subscriptions/mark-traffic-warnings",
    summary="Bulk-bookmark sent traffic-warning thresholds (single UPDATE on the DB)",
)
async def bot_subscriptions_mark_traffic_warnings(
    payload: BotTrafficWarningBulkIn,
    service: BotApiService = Depends(get_bot_api_service),
):
    pairs = [(e.subscription_id, e.threshold_pct) for e in payload.entries]
    affected = await service.bulk_mark_traffic_warnings(pairs)
    return {"affected": affected}


@router.post(
    "/users/{telegram_id}/subscriptions/{subscription_id}/mark-traffic-warning",
    summary="Bookmark that bot has sent a traffic-threshold warning to user",
)
async def bot_mark_traffic_warning(
    telegram_id: int,
    subscription_id: UUID,
    payload: BotTrafficWarningMarkIn,
    service: BotApiService = Depends(get_bot_api_service),
):
    await service.mark_traffic_warning(
        telegram_id=telegram_id,
        subscription_id=subscription_id,
        threshold_pct=payload.threshold_pct,
    )
    return {"ok": True}


@router.post(
    "/users/{telegram_id}/subscription-link",
    response_model=BotSubscriptionLinkOut,
    summary="Rotate and issue a fresh subscription link for Telegram bot user",
)
async def bot_issue_subscription_link(
    telegram_id: int,
    service: BotApiService = Depends(get_bot_api_service),
):
    return await service.issue_subscription_link(telegram_id=telegram_id)
