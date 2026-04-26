from __future__ import annotations

import logging
import secrets
import string
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.billing.models import BalanceTransaction, PaymentOrder
from services.billing.repository import OrderRepository, TransactionRepository
from services.billing.schemas import TransactionInternalCreate
from services.bot_notifications.service import TelegramBotNotifyService
from services.config import get_settings
from services.referral.exceptions import (
    AlreadyReferred,
    ReferralCodeNotFound,
    ReferralNotEnabled,
    SelfReferralNotAllowed,
)
from services.referral.models import Referral
from services.referral.repository import ReferralRepository
from services.referral.schemas import BotReferralInfoOut
from services.users.models import User
from services.users.repository import UserRepository
from shared.utils.logger import StructuredLogger

log = StructuredLogger(logging.getLogger("referral"))

_CODE_ALPHABET = string.ascii_lowercase + string.digits
_CODE_LENGTH = 8


def _generate_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


class ReferralService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.referral_repo = ReferralRepository(session)
        self.order_repo = OrderRepository(session)
        self.tx_repo = TransactionRepository(session)
        self.notify = TelegramBotNotifyService()
        self.settings = get_settings().referral

    # ── Public: get or create referral code for user ──────────

    async def get_or_create_code(self, user: User) -> str:
        if user.referral_code:
            return user.referral_code

        for _ in range(5):
            code = _generate_code()
            existing = await self.session.execute(
                select(User).where(User.referral_code == code)
            )
            if existing.scalar_one_or_none() is None:
                break
        else:
            code = _generate_code() + secrets.choice(_CODE_ALPHABET)

        await self.session.execute(
            update(User).where(User.id == user.id).values(referral_code=code)
        )
        await self.session.flush()
        return code

    # ── Public: get referral info for bot ─────────────────────

    async def get_referral_info(self, user: User) -> BotReferralInfoOut:
        code = await self.get_or_create_code(user)
        total_invited = await self.referral_repo.count_by_referrer(user.id)
        total_rewarded = await self.referral_repo.count_rewarded_by_referrer(user.id)
        total_earned = await self.referral_repo.sum_rewards_by_referrer(user.id)

        bot_username = self.settings.bot_username
        referral_link = f"https://t.me/{bot_username}?start=ref_{code}" if bot_username else ""

        return BotReferralInfoOut(
            referral_code=code,
            referral_link=referral_link,
            total_invited=total_invited,
            total_rewarded=total_rewarded,
            total_earned_rub=Decimal(str(total_earned)),
            reward_per_referral_rub=Decimal(str(self.settings.reward_rub)),
        )

    # ── Public: apply referral code (called when referred user starts bot) ──

    async def apply_referral(self, referred_user: User, referral_code: str) -> None:
        if not self.settings.enabled:
            raise ReferralNotEnabled("Referral program is disabled")

        referrer = await self.session.execute(
            select(User).where(User.referral_code == referral_code)
        )
        referrer_user = referrer.scalar_one_or_none()
        if not referrer_user:
            raise ReferralCodeNotFound(f"Code {referral_code} not found")

        if referrer_user.id == referred_user.id:
            raise SelfReferralNotAllowed("Cannot refer yourself")

        existing = await self.referral_repo.get_by_referred_user(referred_user.id)
        if existing:
            raise AlreadyReferred("User already has a referrer")

        await self.referral_repo.create({
            "referrer_user_id": referrer_user.id,
            "referred_user_id": referred_user.id,
            "status": "pending",
            "reward_amount": Decimal("0"),
            "referred_reward_amount": Decimal("0"),
        })

        log.info(
            "referral_applied",
            referrer_id=str(referrer_user.id),
            referred_id=str(referred_user.id),
            code=referral_code,
        )

    # ── Public: process reward after first paid order ─────────

    async def process_reward_if_eligible(self, user_id: UUID) -> None:
        if not self.settings.enabled:
            return

        referral = await self.referral_repo.get_pending_by_referred_user(user_id)
        if not referral:
            return

        # Check this is the first completed paid order (not free, not top_up)
        result = await self.session.execute(
            select(PaymentOrder).where(
                PaymentOrder.user_id == user_id,
                PaymentOrder.status.in_(["paid", "completed"]),
                PaymentOrder.provider != "free",
                PaymentOrder.order_type != "top_up",
            )
        )
        paid_orders = result.scalars().all()
        if len(paid_orders) > 1:
            # Not the first — already had paid orders before
            return

        now = datetime.now(timezone.utc)
        reward_amount = Decimal(str(self.settings.reward_rub))
        referred_reward = Decimal(str(self.settings.referred_reward_rub))

        from shared.monitoring.metrics import REFERRAL_REWARD_TOTAL

        # Credit referrer
        if reward_amount > 0:
            await self._credit_user(
                referral.referrer_user_id,
                reward_amount,
                tx_type="referral_reward",
                description=f"Referral reward for inviting user",
            )
            REFERRAL_REWARD_TOTAL.labels(side="referrer").inc()
            log.info(
                "referral_reward_credited",
                referrer_id=str(referral.referrer_user_id),
                referred_id=str(user_id),
                amount=str(reward_amount),
            )

            # Notify referrer via bot
            referrer = await self.user_repo.get_by_id(referral.referrer_user_id)
            if referrer:
                import asyncio
                asyncio.create_task(
                    self.notify.send_message(
                        chat_id=referrer.telegram_id,
                        text=(
                            f"🎉 <b>Реферальный бонус!</b>\n\n"
                            f"Ваш друг оплатил подписку.\n"
                            f"На баланс начислено <b>{int(reward_amount)} ₽</b>."
                        ),
                    )
                )

        # Credit referred user (optional)
        if referred_reward > 0:
            await self._credit_user(
                referral.referred_user_id,
                referred_reward,
                tx_type="referral_bonus",
                description="Bonus for joining via referral link",
            )
            REFERRAL_REWARD_TOTAL.labels(side="referred").inc()

        # Mark referral as rewarded
        await self.referral_repo.update_by_id(
            referral.id,
            {
                "status": "rewarded",
                "reward_amount": reward_amount,
                "referred_reward_amount": referred_reward,
                "rewarded_at": now,
            },
        )

    # ── Internal ──────────────────────────────────────────────

    async def _credit_user(
        self,
        user_id: UUID,
        amount: Decimal,
        *,
        tx_type: str,
        description: str,
    ) -> None:
        result = await self.session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        user = result.scalar_one_or_none()
        if not user:
            return

        new_balance = user.balance + amount
        await self.session.execute(
            update(User).where(User.id == user_id).values(balance=new_balance)
        )
        await self.tx_repo.create(
            TransactionInternalCreate(
                user_id=user_id,
                amount=amount,
                balance_after=new_balance,
                type=tx_type,
                description=description,
            ).model_dump()
        )
