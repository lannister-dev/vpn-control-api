from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.support.constants import DRIP_CONDITIONS, DRIP_TRIGGER_EVENTS


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
    WAS_PAYING_EXPIRED = "was_paying_expired"
    DORMANT = "dormant"


class BroadcastStatus(str, Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MessageEntity(BaseModel):
    type: str
    offset: int
    length: int
    url: str | None = None
    language: str | None = None
    custom_emoji_id: str | None = None


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


class AgentOut(BaseModel):
    id: UUID
    username: str
    role: str

    model_config = ConfigDict(from_attributes=True)


class AgentListOut(BaseModel):
    items: list[AgentOut]


class TicketStatsRaw(BaseModel):
    open: int = 0
    unanswered: int = 0
    closed_today: int = 0
    avg_reply_minutes: int | None = None


class SupportTicketCreate(BaseModel):
    user_id: UUID
    subject: str = ""
    status: TicketStatus = TicketStatus.NEW
    category: TicketCategory = TicketCategory.OTHER
    priority: TicketPriority = TicketPriority.NORMAL
    last_activity_at: datetime
    first_user_msg_at: datetime | None = None


class SupportMessageCreate(BaseModel):
    ticket_id: UUID
    sender_kind: MessageSenderKind
    sender_admin_id: UUID | None = None
    body: str = ""
    is_note: bool = False
    delivered: bool = False
    tg_message_id: int | None = None


class SupportAttachmentCreate(BaseModel):
    message_id: UUID | None = None
    kind: str
    tg_file_id: str | None = None
    tg_file_unique_id: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    mime_type: str | None = None
    duration: int | None = None
    storage_url: str | None = None


class BroadcastCreate(BaseModel):
    audience: BroadcastAudience
    audience_label: str | None = None
    plan_id: UUID | None = None
    text_body: str
    media_kind: str | None = None
    media_url: str | None = None
    inline_buttons: list[dict] | None = None
    status: BroadcastStatus = BroadcastStatus.DRAFT
    scheduled_at: datetime | None = None
    target_count: int = 0
    promo_code_id: UUID | None = None
    created_by_admin_id: UUID | None = None
    entities: list[dict] | None = None
    custom_emoji_assets: dict | None = None


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
    text_body: str = ""
    media_kind: str | None = None
    media_url: str | None = None
    inline_buttons: list[dict] | None = None
    entities: list[dict] | None = None
    custom_emoji_assets: dict | None = None
    status: BroadcastStatus
    delivered: int = 0
    errors: int = 0
    clicks: int = 0
    target_count: int = 0
    promo_code_id: UUID | None = None
    sent_at: datetime | None = None
    scheduled_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BroadcastListOut(BaseModel):
    items: list[BroadcastOut]


class BroadcastFunnelOut(BaseModel):
    broadcast_id: UUID
    has_promo: bool = False
    target_count: int = 0
    delivered: int = 0
    clicked: int = 0
    applied: int = 0
    click_rate: float = 0.0
    apply_rate: float = 0.0


class BroadcastAudienceCount(BaseModel):
    count: int


class RecurringCadence(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"


_HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class RecurringBroadcastCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    audience: BroadcastAudience = BroadcastAudience.ALL
    plan_id: UUID | None = None
    text_body: str = Field(min_length=1)
    media_kind: str | None = None
    media_url: str | None = None
    inline_buttons: list[dict] | None = None
    promo_code_id: UUID | None = None
    cadence: RecurringCadence = RecurringCadence.DAILY
    time_of_day: str = Field(pattern=_HHMM)
    weekdays: list[int] | None = None


class RecurringBroadcastUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    audience: BroadcastAudience | None = None
    plan_id: UUID | None = None
    text_body: str | None = Field(default=None, min_length=1)
    media_kind: str | None = None
    media_url: str | None = None
    inline_buttons: list[dict] | None = None
    promo_code_id: UUID | None = None
    cadence: RecurringCadence | None = None
    time_of_day: str | None = Field(default=None, pattern=_HHMM)
    weekdays: list[int] | None = None
    is_active: bool | None = None


class RecurringBroadcastInternalCreate(BaseModel):
    name: str
    audience: str
    plan_id: UUID | None = None
    text_body: str
    media_kind: str | None = None
    media_url: str | None = None
    inline_buttons: list[dict] | None = None
    promo_code_id: UUID | None = None
    cadence: str
    time_of_day: str
    weekdays: list[int] | None = None
    next_run_at: datetime
    created_by_admin_id: UUID | None = None


class RecurringBroadcastOut(BaseModel):
    id: UUID
    name: str
    audience: str
    plan_id: UUID | None
    text_body: str
    media_kind: str | None
    media_url: str | None
    inline_buttons: list[dict] | None
    promo_code_id: UUID | None
    cadence: str
    time_of_day: str
    weekdays: list[int] | None
    next_run_at: datetime
    last_run_at: datetime | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecurringBroadcastListOut(BaseModel):
    items: list[RecurringBroadcastOut]


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
    entities: list[MessageEntity] = Field(default_factory=list)
    caption_entities: list[MessageEntity] = Field(default_factory=list)
    attachments: list[SupportInboundAttachmentMsg] = Field(default_factory=list)
    tg_message_id: int | None = None
    intent: str | None = None


class SupportOutboundAttachmentMsg(BaseModel):
    kind: str
    tg_file_id: str | None = None
    url: str | None = None
    file_name: str | None = None


class SupportOutboundInlineButton(BaseModel):
    text: str
    url: str
    style: str | None = None


class SupportOutboundPayload(BaseModel):
    ticket_id: str
    message_id: str
    telegram_id: int
    text: str = ""
    media: list[SupportOutboundAttachmentMsg] = Field(default_factory=list)
    buttons: list[SupportOutboundInlineButton] = Field(default_factory=list)
    entities: list[MessageEntity] | None = None
    parse_mode: str | None = None
    kind: str = "reply"


class SupportSentAck(BaseModel):
    message_id: UUID
    tg_message_id: int | None = None
    ok: bool = True
    error: str | None = None


class DripTriggerEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: str
    telegram_id: int


class DripStepIn(BaseModel):
    step_order: int
    delay_seconds: int = 0
    condition: str = "always"
    text_body: str
    inline_buttons: list[dict] | None = None
    media_kind: str | None = None
    media_url: str | None = None

    @field_validator("condition")
    @classmethod
    def _check_condition(cls, v: str) -> str:
        if v not in DRIP_CONDITIONS:
            raise ValueError(f"condition must be one of {DRIP_CONDITIONS}")
        return v


class DripStepOut(DripStepIn):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class DripCampaignIn(BaseModel):
    key: str
    name: str
    trigger_event: str | None = None
    is_active: bool = True
    steps: list[DripStepIn] = Field(default_factory=list)

    @field_validator("trigger_event")
    @classmethod
    def _check_trigger(cls, v: str | None) -> str | None:
        if v is not None and v not in DRIP_TRIGGER_EVENTS:
            raise ValueError(f"trigger_event must be null or one of {DRIP_TRIGGER_EVENTS}")
        return v


class DripCampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    name: str
    trigger_event: str | None
    is_active: bool
    steps: list[DripStepOut]


class DripCampaignListOut(BaseModel):
    items: list[DripCampaignOut]


class DripCampaignStat(BaseModel):
    campaign_id: UUID
    enrolled: int = 0
    active: int = 0
    completed: int = 0
    abandoned: int = 0
    stopped: int = 0


class DripStatsOut(BaseModel):
    items: list[DripCampaignStat]


class OnboardingFunnelOut(BaseModel):
    period_days: int
    registered: int = 0
    trial_started: int = 0
    connected: int = 0
    purchased: int = 0
    renewed: int = 0
