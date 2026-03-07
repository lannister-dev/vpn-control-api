from uuid import UUID


def connect_telemetry_allowed_routes_key(*, key_id: UUID) -> str:
    return f"connect:telemetry:allowed_routes:{key_id}"
