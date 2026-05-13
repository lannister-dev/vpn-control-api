from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from services.support.constants import (
    BroadcastAudience,
    BroadcastStatus,
    MessageSenderKind,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)


class TicketUserRef(BaseModel):
    id: UUID
    username: str | None = None
    telegram_id: int
    balance: Decimal = Decimal("0")
    plan_name: str | None = None
    expires_at: datetime | None = None
    lifetime_spend: Decimal = Decimal("0")

    model_config = ConfigDict(from_attributes=True)


class TicketOut(BaseModel):
    id: UUID
    subject: str = ""
    status: TicketStatus
    priority: TicketPriority
    category: TicketCategory
    assignee: str | None = None
    has_media: bool = False
    attachments_count: int = 0
    created_at: datetime
    updated_at: datetime
    last_activity_at: datetime
    user: TicketUserRef

    model_config = ConfigDict(from_attributes=True)


class TicketListOut(BaseModel):
    items: list[TicketOut]
    total: int


class TicketStatsOut(BaseModel):
    open: int = 0
    unanswered: int = 0
    avg_reply_minutes: int | None = None
    avg_reply_change: int | None = None
    closed_today: int = 0
    open_spark_24h: list[int] = Field(default_factory=list)
    reply_spark_24h: list[int] = Field(default_factory=list)


class TicketCreateIn(BaseModel):
    user_id: UUID
    subject: str = ""
    category: TicketCategory = TicketCategory.OTHER
    priority: TicketPriority = TicketPriority.NORMAL


class TicketPatchIn(BaseModel):
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    category: TicketCategory | None = None
    assignee: str | None = None


class TicketBulkUpdateIn(BaseModel):
    ids: list[UUID]
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    assignee: str | None = None


class AttachmentOut(BaseModel):
    kind: str
    url: str
    thumb_url: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    duration: int | None = None

    model_config = ConfigDict(from_attributes=True)


class MessageAuthorRef(BaseModel):
    label: str


class MessageOut(BaseModel):
    id: UUID
    from_: MessageSenderKind = Field(alias="from")
    kind: str = "text"
    text: str = ""
    media: list[AttachmentOut] = Field(default_factory=list)
    created_at: datetime
    delivered: bool = False
    read: bool = False
    is_note: bool = False
    author: MessageAuthorRef | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MessageListOut(BaseModel):
    items: list[MessageOut]


class TemplateOut(BaseModel):
    id: UUID
    tag: str
    title: str
    body: str
    used_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class TemplateListOut(BaseModel):
    items: list[TemplateOut]


class TemplateCreateIn(BaseModel):
    tag: str = Field(max_length=40)
    title: str = Field(max_length=120)
    body: str


class TemplateUpdateIn(BaseModel):
    tag: str | None = Field(default=None, max_length=40)
    title: str | None = Field(default=None, max_length=120)
    body: str | None = None


class BroadcastInlineButton(BaseModel):
    text: str
    url: str | None = None
    callback: str | None = None


class BroadcastOut(BaseModel):
    id: UUID
    audience: BroadcastAudience
    audience_label: str | None = None
    preview: str = ""
    status: BroadcastStatus
    delivered: int = 0
    errors: int = 0
    clicks: int = 0
    target_count: int = 0
    sent_at: datetime | None = None
    scheduled_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BroadcastListOut(BaseModel):
    items: list[BroadcastOut]


class BroadcastAudienceCount(BaseModel):
    count: int
