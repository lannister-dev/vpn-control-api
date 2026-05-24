from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AdminAuditRecordCreate(BaseModel):
    actor: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=128)
    target: str | None = Field(default=None, max_length=255)
    summary: str | None = Field(default=None, max_length=500)
    details: dict = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class AdminAuditRecordOut(BaseModel):
    id: UUID
    created_at: datetime
    actor: str
    action: str
    target: str | None = None
    summary: str | None = None
    details: dict = {}

    model_config = ConfigDict(from_attributes=True)


class AdminAuditListOut(BaseModel):
    items: list[AdminAuditRecordOut]
    total: int
    limit: int
    offset: int
