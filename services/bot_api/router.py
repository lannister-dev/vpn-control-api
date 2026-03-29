from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from services.auth.dependencies import bot_auth

from .schemas import (
    BotDeviceSlotPurchaseIn,
    BotDevicesOut,
    BotOrderActionOut,
    BotOrderCreateIn,
    BotOrderHistoryOut,
    BotPlanListOut,
    BotSessionOut,
    BotSessionSyncIn,
    BotStarsConfirmIn,
    BotSubscriptionLinkOut,
)
from .service import BotApiService, get_bot_api_service

router = APIRouter(prefix="/bot", tags=["Bot"], dependencies=[Depends(bot_auth)])


# ── TEMPORARY debug endpoint — remove after fixing auth ──
from fastapi import Request as _Req
from services.auth.utils import AuthUtils as _AU
from services.config import get_settings as _gs
import os as _os


@router.get("/debug-auth", dependencies=[])       # no auth
async def _debug_auth(_req: _Req):
    s = _gs()
    expected = s.bot_api.api_key_hash
    env_raw = _os.environ.get("BOT_API_KEY_HASH", "<NOT SET>")
    auth = _req.headers.get("authorization", "")
    token = auth.replace("Bearer ", "") if auth.startswith("Bearer ") else ""
    provided = _AU.hash_admin_api_key(token) if token else "<no token>"
    return {
        "expected_hash_first12": expected[:12] if expected else "<empty>",
        "expected_len": len(expected),
        "env_raw_first12": env_raw[:12],
        "provided_hash_first12": provided[:12] if token else "<no token>",
        "token_len": len(token),
        "match": expected == provided if token else False,
    }


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
    "/users/{telegram_id}/subscription-link",
    response_model=BotSubscriptionLinkOut,
    summary="Rotate and issue a fresh subscription link for Telegram bot user",
)
async def bot_issue_subscription_link(
    telegram_id: int,
    service: BotApiService = Depends(get_bot_api_service),
):
    return await service.issue_subscription_link(telegram_id=telegram_id)
