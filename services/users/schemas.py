from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserCreateIn(BaseModel):
    telegram_id: int
    username: str | None = None
    tag: str | None = None
    description: str | None = None
    terms_accepted: bool = False
    terms_accepted_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class UserInternalCreate(BaseModel):
    telegram_id: int
    username: str | None = None
    balance: Decimal = Decimal("0")
    tag: str | None = None
    description: str | None = None
    terms_accepted: bool = False
    terms_accepted_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class UserUpdateIn(BaseModel):
    username: str | None = None
    balance: Decimal | None = None
    is_active: bool | None = None
    tag: str | None = None
    description: str | None = None
    terms_accepted: bool | None = None
    terms_accepted_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class UserInternalUpdate(BaseModel):
    username: str | None = None
    balance: Decimal | None = None
    is_active: bool | None = None
    tag: str | None = None
    description: str | None = None
    terms_accepted: bool | None = None
    terms_accepted_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class UserOut(BaseModel):
    id: UUID
    telegram_id: int
    username: str | None
    balance: Decimal
    is_active: bool
    tag: str | None = None
    description: str | None = None
    terms_accepted: bool = False
    terms_accepted_at: datetime | None = None
    referral_code: str | None = None
    suppress_marketing: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserDetailOut(UserOut):
    subscription_count: int
    key_count: int


class UserListOut(BaseModel):
    items: list[UserOut]
    total: int
    limit: int
    offset: int
