from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.entry.schemas import EntryBackendAssignIn, EntryBackendUpdateIn
from services.entry.service import (
    BackendNotFoundError,
    EntryNotFoundError,
    EntryRoleError,
    EntryService,
)


def _make_node(*, role: str, reality_ip: str | None = "10.0.1.5", is_enabled: bool = True, is_draining: bool = False):
    return SimpleNamespace(
        id=uuid4(),
        role=role,
        reality_ip=reality_ip,
        internal_wg_ip="10.0.1.99",
        is_enabled=is_enabled,
        is_draining=is_draining,
        is_active=True,
    )


def _make_assignment(*, entry_id, backend_id, weight: int = 100, enabled: bool = True, is_active: bool = True, updated_at: datetime | None = None):
    return SimpleNamespace(
        id=uuid4(),
        entry_node_id=entry_id,
        backend_node_id=backend_id,
        weight=weight,
        enabled=enabled,
        is_active=is_active,
        updated_at=updated_at or datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc),
    )


def _make_service(async_session):
    service = EntryService(async_session)
    service.reality_port = 443
    service.node_repo = SimpleNamespace(
        get_by_id=AsyncMock(),
        list_by_ids=AsyncMock(),
    )
    service.assignment_repo = SimpleNamespace(
        list_by_entry=AsyncMock(),
        get_by_entry_and_backend=AsyncMock(),
        create=AsyncMock(),
        update_by_id=AsyncMock(),
    )
    return service


@pytest.mark.asyncio
async def test_get_relay_pool_builds_generation_and_filters(async_session):
    service = _make_service(async_session)
    entry = _make_node(role="entry")
    backend_ok = _make_node(role="backend", reality_ip="10.0.1.5")
    backend_draining = _make_node(role="backend", reality_ip="10.0.1.6", is_draining=True)
    backend_missing_address = _make_node(role="backend", reality_ip=None)
    backend_missing_address.internal_wg_ip = ""

    a1 = _make_assignment(entry_id=entry.id, backend_id=backend_ok.id, weight=200, updated_at=datetime(2026, 4, 16, 14, 0, tzinfo=timezone.utc))
    a2 = _make_assignment(entry_id=entry.id, backend_id=backend_draining.id, weight=50)
    a3 = _make_assignment(entry_id=entry.id, backend_id=backend_missing_address.id, weight=10)

    service.node_repo.get_by_id.return_value = entry
    service.assignment_repo.list_by_entry.return_value = [a1, a2, a3]
    service.node_repo.list_by_ids.return_value = [backend_ok, backend_draining, backend_missing_address]

    pool = await service.get_relay_pool(entry.id)

    assert pool.entry_id == entry.id
    assert pool.ttl_seconds == 300
    assert pool.generation == int(a1.updated_at.timestamp())

    ids = {b.id: b for b in pool.backends}
    assert backend_ok.id in ids
    assert ids[backend_ok.id].enabled is True
    assert ids[backend_ok.id].address == "10.0.1.5"
    assert ids[backend_ok.id].port == 443
    assert ids[backend_ok.id].weight == 200

    assert backend_draining.id in ids
    assert ids[backend_draining.id].enabled is False  # draining → enabled=false

    assert backend_missing_address.id not in ids  # no resolvable address → dropped entirely


@pytest.mark.asyncio
async def test_get_relay_pool_rejects_non_entry_role(async_session):
    service = _make_service(async_session)
    service.node_repo.get_by_id.return_value = _make_node(role="backend")

    with pytest.raises(EntryRoleError):
        await service.get_relay_pool(uuid4())


@pytest.mark.asyncio
async def test_get_relay_pool_missing_entry(async_session):
    service = _make_service(async_session)
    service.node_repo.get_by_id.return_value = None

    with pytest.raises(EntryNotFoundError):
        await service.get_relay_pool(uuid4())


@pytest.mark.asyncio
async def test_assign_backend_creates_new(async_session):
    service = _make_service(async_session)
    entry = _make_node(role="entry")
    backend = _make_node(role="backend")

    service.node_repo.get_by_id.side_effect = [entry, backend]
    service.assignment_repo.get_by_entry_and_backend.return_value = None
    service.assignment_repo.create.return_value = _make_assignment(entry_id=entry.id, backend_id=backend.id)

    payload = EntryBackendAssignIn(backend_node_id=backend.id, weight=200, enabled=True)
    result = await service.assign_backend(entry.id, payload)

    service.assignment_repo.create.assert_awaited_once()
    service.assignment_repo.update_by_id.assert_not_awaited()
    assert result.entry_node_id == entry.id


@pytest.mark.asyncio
async def test_assign_backend_reactivates_existing(async_session):
    service = _make_service(async_session)
    entry = _make_node(role="entry")
    backend = _make_node(role="backend")
    existing = _make_assignment(entry_id=entry.id, backend_id=backend.id, is_active=False)

    service.node_repo.get_by_id.side_effect = [entry, backend]
    service.assignment_repo.get_by_entry_and_backend.return_value = existing
    service.assignment_repo.update_by_id.return_value = existing

    payload = EntryBackendAssignIn(backend_node_id=backend.id, weight=150, enabled=True)
    await service.assign_backend(entry.id, payload)

    service.assignment_repo.create.assert_not_awaited()
    service.assignment_repo.update_by_id.assert_awaited_once()
    args, _ = service.assignment_repo.update_by_id.call_args
    assert args[1]["is_active"] is True
    assert args[1]["weight"] == 150


@pytest.mark.asyncio
async def test_assign_backend_rejects_non_backend_role(async_session):
    service = _make_service(async_session)
    entry = _make_node(role="entry")
    wrong_backend = _make_node(role="entry")

    service.node_repo.get_by_id.side_effect = [entry, wrong_backend]

    with pytest.raises(EntryRoleError):
        await service.assign_backend(
            entry.id,
            EntryBackendAssignIn(backend_node_id=wrong_backend.id),
        )


@pytest.mark.asyncio
async def test_assign_backend_missing_backend_node(async_session):
    service = _make_service(async_session)
    entry = _make_node(role="entry")

    service.node_repo.get_by_id.side_effect = [entry, None]

    with pytest.raises(BackendNotFoundError):
        await service.assign_backend(
            entry.id,
            EntryBackendAssignIn(backend_node_id=uuid4()),
        )


@pytest.mark.asyncio
async def test_remove_assignment_soft_deletes(async_session):
    service = _make_service(async_session)
    entry_id = uuid4()
    backend_id = uuid4()
    existing = _make_assignment(entry_id=entry_id, backend_id=backend_id)
    service.assignment_repo.get_by_entry_and_backend.return_value = existing
    service.assignment_repo.update_by_id.return_value = existing

    removed = await service.remove_assignment(entry_id, backend_id)

    assert removed is True
    args, _ = service.assignment_repo.update_by_id.call_args
    assert args[1] == {"is_active": False}


@pytest.mark.asyncio
async def test_remove_assignment_noop_when_missing(async_session):
    service = _make_service(async_session)
    service.assignment_repo.get_by_entry_and_backend.return_value = None

    removed = await service.remove_assignment(uuid4(), uuid4())

    assert removed is False
    service.assignment_repo.update_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_assignment_applies_partial(async_session):
    service = _make_service(async_session)
    entry_id = uuid4()
    backend_id = uuid4()
    existing = _make_assignment(entry_id=entry_id, backend_id=backend_id, weight=100, enabled=True)
    service.assignment_repo.get_by_entry_and_backend.return_value = existing
    service.assignment_repo.update_by_id.return_value = existing

    await service.update_assignment(
        entry_id,
        backend_id,
        EntryBackendUpdateIn(enabled=False),
    )

    args, _ = service.assignment_repo.update_by_id.call_args
    assert args[1] == {"enabled": False}


@pytest.mark.asyncio
async def test_update_assignment_returns_none_when_soft_deleted(async_session):
    service = _make_service(async_session)
    existing = _make_assignment(entry_id=uuid4(), backend_id=uuid4(), is_active=False)
    service.assignment_repo.get_by_entry_and_backend.return_value = existing

    result = await service.update_assignment(
        uuid4(),
        uuid4(),
        EntryBackendUpdateIn(weight=500),
    )

    assert result is None
