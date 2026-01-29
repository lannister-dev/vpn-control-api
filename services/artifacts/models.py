from sqlalchemy import Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class ProfileArtifact(Base):
    __tablename__ = "profile_artifacts"

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(Text, nullable=False)
    artifact: Mapped[dict] = mapped_column(JSONB, nullable=False)