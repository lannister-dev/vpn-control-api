from datetime import datetime, timezone
from uuid import UUID

from services.routes.schemas import RouteOut
from services.routes.types import RouteNodeRole


def normalized_optional_uuid(value) -> UUID | str | None:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None


def build_route_out(
    route,
    *,
    routing_eligible: bool = False,
    routing_reason: str | None = None,
) -> RouteOut:
    return RouteOut(
        id=route.id,
        name=route.name,
        node_id=route.node_id,
        entry_node_id=normalized_optional_uuid(getattr(route, "entry_node_id", None)),
        transport_profile_id=route.transport_profile_id,
        health_status=route.health_status,
        base_weight=route.base_weight,
        effective_weight=route.effective_weight,
        cooldown_until=route.cooldown_until,
        warmup_stage=route.warmup_stage,
        warmup_started_at=route.warmup_started_at,
        routing_eligible=routing_eligible,
        routing_reason=routing_reason,
        is_active=route.is_active,
        created_at=route.created_at,
        updated_at=route.updated_at,
    )


def normalized_node_role(node) -> RouteNodeRole | None:
    raw = getattr(node, "role", None)
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized:
            try:
                return RouteNodeRole(normalized)
            except ValueError:
                return None
    return None


def to_utc_or_none(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
