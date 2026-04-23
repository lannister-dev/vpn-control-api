from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
