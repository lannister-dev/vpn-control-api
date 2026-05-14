from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ZoneCreateIn(BaseModel):
    code: str = Field(min_length=2, max_length=16, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=64)
    emoji: str = Field(default="", max_length=16)
    sort_order: int = Field(default=0, ge=0)


class ZoneUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    emoji: str | None = Field(default=None, max_length=16)
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ZoneOut(BaseModel):
    id: UUID
    code: str
    name: str
    emoji: str
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ZoneListOut(BaseModel):
    items: list[ZoneOut]
    total: int


class ZoneReorderIn(BaseModel):
    codes: list[str] = Field(min_length=1, max_length=200)


class ZoneReorderOut(BaseModel):
    updated: int
