"""Helper for emitting entry-pool-changed events from non-entry contexts.

Backend health transitions (is_draining / is_enabled / is_active) can happen
from several places: probe-driven drain, heartbeat-driven auto-heal, admin
manual toggles. Each of those places needs to notify the data plane of
every entry whose pool includes the affected backend.

Instead of re-implementing that fan-out at each site, callers invoke this
single entry point. It participates in the caller's DB transaction, so the
health flip and the outbox event commit together or both roll back.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


async def enqueue_pool_snapshots_for_backend(
    session: AsyncSession,
    backend_node_id: UUID,
) -> int:
    """Emit one pool_changed event per entry that references the backend.

    Returns the number of entries notified. Callers should log the result
    and swallow no exceptions — if event enqueue fails, the whole flip
    must roll back so we never leave a silent data-plane divergence.
    """
    # Local import avoids a circular dep chain:
    # services.entry.events -> services.entry.service ->
    # services.nodes.agent.repository (which pulls other services).
    from services.entry.service import EntryService

    return await EntryService(session).notify_backend_health_changed(backend_node_id)
