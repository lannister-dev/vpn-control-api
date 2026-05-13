from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TicketStatus(str, Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    WAITING_USER = "waiting_user"
    CLOSED = "closed"


class TicketPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TicketCategory(str, Enum):
    PAYMENT = "payment"
    TECHNICAL = "technical"
    ACCOUNT = "account"
    SPEED = "speed"
    CONNECTION = "connection"
    REFUND = "refund"
    OTHER = "other"


class MessageSenderKind(str, Enum):
    USER = "user"
    OPERATOR = "operator"
    SYSTEM = "system"


class BroadcastAudience(str, Enum):
    ALL = "all"
    ACTIVE = "active"
    EXPIRING = "expiring"
    BY_PLAN = "by_plan"
    TRIAL = "trial"
    NO_SUB = "no_sub"


class BroadcastStatus(str, Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"


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


class TicketStatsRaw(BaseModel):
    open: int = 0
    unanswered: int = 0
    closed_today: int = 0
    avg_reply_minutes: int | None = None


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


class SupportInboundAttachmentMsg(BaseModel):
    kind: str
    tg_file_id: str
    tg_file_unique_id: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    mime_type: str | None = None
    duration: int | None = None


class SupportInboundMessage(BaseModel):
    telegram_id: int
    text: str = ""
    attachments: list[SupportInboundAttachmentMsg] = Field(default_factory=list)
    tg_message_id: int | None = None
