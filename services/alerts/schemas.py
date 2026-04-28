from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AlertLevel(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class AlertMessage(BaseModel):
    level: AlertLevel
    title: str = Field(min_length=1, max_length=128)
    body: str = Field(min_length=1, max_length=4000)


class TelegramSendMessageIn(BaseModel):
    chat_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4096)
    disable_web_page_preview: bool = True


class AlertEventOut(BaseModel):
    id: UUID
    level: AlertLevel
    source: str
    dedup_key: str | None = None
    entity_id: str | None = None
    title: str
    body: str
    occurrences: int
    created_at: datetime
    last_seen_at: datetime
    read_at: datetime | None = None
    resolved_at: datetime | None = None
    dismissed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AlertListOut(BaseModel):
    items: list[AlertEventOut]
    total: int
    unread: int
    limit: int
    offset: int


class AlertCountOut(BaseModel):
    unread: int


class AlertMarkAllReadOut(BaseModel):
    marked: int
