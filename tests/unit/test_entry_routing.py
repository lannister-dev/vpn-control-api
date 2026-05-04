from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.config import EntryRoutingConfig
from services.nodes.constants import ROLE_BACKEND, ROLE_ENTRY
from services.routing.entry.schemas import (
    EntryRoutingBackend,
    EntryRoutingReality,
    EntryRoutingRule,
    EntryRoutingSpec,
    EntryRoutingUser,
)
from services.routing.entry.service import EntryRoutingService


def _reality() -> EntryRoutingReality:
    return EntryRoutingReality(
        private_key="pk",
        short_id="abcd1234",
        server_name="www.cloudflare.com",
        handshake_server="www.cloudflare.com",
    )


def _spec(**overrides) -> EntryRoutingSpec:
    base = dict(
        node_id=str(uuid4()),
        listen_port=8443,
        reality=_reality(),
        users=[EntryRoutingUser(uuid="u1")],
        backends=[],
        rules=[],
        final_outbound="direct",
    )
    base.update(overrides)
    return EntryRoutingSpec(**base)


class TestEntryRoutingSpecSignature:
    def test_signature_stable_across_user_order(self):
        a = _spec(users=[EntryRoutingUser(uuid="u1"), EntryRoutingUser(uuid="u2")])
        b = _spec(node_id=a.node_id, users=[EntryRoutingUser(uuid="u2"), EntryRoutingUser(uuid="u1")])
        assert a.signature() == b.signature()

    def test_signature_changes_when_user_added(self):
        a = _spec()
        b = _spec(node_id=a.node_id, users=[EntryRoutingUser(uuid="u1"), EntryRoutingUser(uuid="u2")])
        assert a.signature() != b.signature()

    def test_signature_changes_when_rule_outbound_changes(self):
        a = _spec(
            backends=[EntryRoutingBackend(tag="b1", server="1.1.1.1", server_port=10000, uuid="svc")],
            rules=[EntryRoutingRule(user_uuid="u1", outbound_tag="b1")],
        )
        b = _spec(
            node_id=a.node_id,
            backends=a.backends,
            rules=[EntryRoutingRule(user_uuid="u1", outbound_tag="direct")],
        )
        assert a.signature() != b.signature()


@pytest.mark.asyncio
class TestEntryRoutingService:
    async def test_returns_none_for_backend_node(self):
        backend_id = uuid4()
        backend = MagicMock()
        backend.id = backend_id
        backend.role = ROLE_BACKEND

        node_repo = MagicMock()
        node_repo.get_by_id = AsyncMock(return_value=backend)

        svc = EntryRoutingService(
            session=MagicMock(),
            config=EntryRoutingConfig(
                listen_port=8443,
                reality_private_key="pk",
                reality_short_id="abcd",
                reality_server_name="www.cloudflare.com",
                reality_handshake_server="www.cloudflare.com",
                reality_handshake_port=443,
            ),
        )
        svc.node_repo = node_repo
        svc.key_repo = MagicMock()
        result = await svc.build_spec_for_node(backend_id)
        assert result is None

    async def test_builds_spec_with_active_users(self):
        entry_id = uuid4()
        entry = MagicMock()
        entry.id = entry_id
        entry.role = ROLE_ENTRY

        key1 = MagicMock(client_id="client-1")
        key2 = MagicMock(client_id="client-2")
        key_no_client = MagicMock(client_id=None)

        node_repo = MagicMock()
        node_repo.get_by_id = AsyncMock(return_value=entry)
        key_repo = MagicMock()
        key_repo.list_all_active = AsyncMock(return_value=[key1, key2, key_no_client])

        svc = EntryRoutingService(
            session=MagicMock(),
            config=EntryRoutingConfig(
                listen_port=8443,
                reality_private_key="pk",
                reality_short_id="abcd",
                reality_server_name="www.cloudflare.com",
                reality_handshake_server="www.cloudflare.com",
                reality_handshake_port=443,
            ),
        )
        svc.node_repo = node_repo
        svc.key_repo = key_repo

        spec = await svc.build_spec_for_node(entry_id)
        assert spec is not None
        assert {u.uuid for u in spec.users} == {"client-1", "client-2"}
        assert spec.node_id == str(entry_id)
        assert spec.listen_port == 8443
        assert spec.reality.private_key == "pk"
