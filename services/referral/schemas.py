from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReferralCreateIn(BaseModel):
    referrer_user_id: UUID
    referred_user_id: UUID


class ReferralOut(BaseModel):
    id: UUID
    referrer_user_id: UUID
    referred_user_id: UUID
    status: str
    reward_amount: Decimal
    referred_reward_amount: Decimal
    rewarded_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BotReferralInfoOut(BaseModel):
    referral_code: str
    referral_link: str
    total_invited: int
    total_rewarded: int
    total_earned_rub: Decimal
    reward_per_referral_rub: Decimal


class BotReferralApplyIn(BaseModel):
    referral_code: str
