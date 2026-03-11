from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from services.auth.admin.constants import AdminRole


class PasswordLoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class LoginOut(BaseModel):
    ok: bool = True
    username: str
    role: AdminRole
    csrf_token: str


class SessionCheckOut(BaseModel):
    authenticated: bool
    username: str | None = None
    role: AdminRole | None = None
    csrf_token: str | None = None


class AdminSessionCreate(BaseModel):
    user_id: UUID
    session_hash: str = Field(..., min_length=1, max_length=128)
    ip_address: str | None = Field(default=None, max_length=45)
    user_agent: str | None = Field(default=None, max_length=512)
    expires_at: datetime


class AdminUserCreateData(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    role: AdminRole
    password_hash: str | None = Field(default=None, max_length=256)
    telegram_id: int | None = None


class AdminUserUpdateData(BaseModel):
    role: AdminRole | None = None
    is_active: bool | None = None
    telegram_id: int | None = None
    telegram_username: str | None = Field(default=None, max_length=128)


class AdminUserPasswordUpdateData(BaseModel):
    password_hash: str = Field(..., min_length=1, max_length=256)


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    telegram_id: int | None = None
    telegram_username: str | None = None
    role: AdminRole
    is_active: bool
    created_at: datetime


class AdminUserCreateIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str | None = Field(None, min_length=8, max_length=256)
    telegram_id: int | None = None
    role: AdminRole = AdminRole.viewer


class AdminUserUpdateIn(BaseModel):
    role: AdminRole | None = None
    is_active: bool | None = None
    telegram_id: int | None = Field(None)
    telegram_username: str | None = Field(None, max_length=128)


class AdminUserPasswordResetIn(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=256)


class AdminUserListOut(BaseModel):
    items: list[AdminUserOut]
    total: int
    limit: int
    offset: int


class AdminSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ip_address: str | None = None
    user_agent: str | None = None
    expires_at: datetime
    created_at: datetime


class AdminUserSessionsOut(BaseModel):
    items: list[AdminSessionOut]
    total: int
