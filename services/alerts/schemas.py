from enum import Enum

from pydantic import BaseModel, Field


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
