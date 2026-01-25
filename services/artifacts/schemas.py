from datetime import datetime
from typing import Dict, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProfileArtifactPublishIn(BaseModel):
    artifact: Dict[str, Any]


class ProfileArtifactCreate(BaseModel):
    version: int
    artifact: Dict[str, Any]
    checksum: str


class ProfileArtifactUpdate(BaseModel):
    is_active: bool | None = None


class ProfileArtifactOut(BaseModel):
    id: UUID
    version: int
    checksum: str
    artifact: Dict[str, Any]
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
