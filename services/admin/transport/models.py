from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class NatsProcessedMsgLog(Base):
    __tablename__ = "nats_processed_msg_log"

    msg_id: Mapped[str] = mapped_column(String(128), nullable=False)
    subject: Mapped[str] = mapped_column(String(128), nullable=False)

    __table_args__ = (
        UniqueConstraint("subject", "msg_id", name="uq_nats_processed_msg_subject_msg_id"),
        Index("ix_nats_processed_msg_log_created_at", "created_at"),
    )
