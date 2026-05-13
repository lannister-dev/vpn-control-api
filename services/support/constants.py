from enum import Enum


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


SUPPORT_INBOUND_SUBJECT = "support.message.in"
SUPPORT_OUTBOUND_SUBJECT = "support.message.out"
SUPPORT_TICKET_EVENT_SUBJECT = "support.ticket.event"

REOPEN_WINDOW_MIN = 60

SUBJECT_PREVIEW_LEN = 80
