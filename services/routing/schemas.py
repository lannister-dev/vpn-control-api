from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RoutingNodeOut(BaseModel):
    node_id: UUID
    domain: str
    region: str
    score: float

    model_config = ConfigDict(from_attributes=True)
