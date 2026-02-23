from uuid import UUID

from pydantic import BaseModel, Field

from services.routes.schemas import RouteHealthAction


class AdminSetRouteHealthIn(BaseModel):
    route_id: UUID
    action: RouteHealthAction
    cooldown_hours: int = Field(default=6, ge=1, le=72)
