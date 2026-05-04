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
from services.routing.entry.service import EntryRoutingAdminService, EntryRoutingService


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
        entry.zone = "europe"
        entry.region = "de"

        key1 = MagicMock(client_id="client-1", entry_routing_override_backend_tag=None)
        key2 = MagicMock(client_id="client-2", entry_routing_override_backend_tag=None)
        key_no_client = MagicMock(client_id=None, entry_routing_override_backend_tag=None)

        node_repo = MagicMock()
        node_repo.get_by_id = AsyncMock(return_value=entry)
        node_repo.list = AsyncMock(return_value=[entry])
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
        assert spec.backends == []
        assert spec.rules == []
        assert spec.final_outbound == "direct"

    async def test_assigns_users_to_backends_in_same_zone(self):
        entry_id = uuid4()
        entry = MagicMock()
        entry.id = entry_id
        entry.role = ROLE_ENTRY
        entry.zone = "europe"
        entry.region = "de"

        backend1 = MagicMock()
        backend1.id = uuid4()
        backend1.name = "hel-backend-01"
        backend1.role = "backend"
        backend1.is_enabled = True
        backend1.is_draining = False
        backend1.zone = "europe"
        backend1.region = "fi"
        backend1.reality_ip = "1.1.1.1"
        backend1.public_domain = ""

        backend2 = MagicMock()
        backend2.id = uuid4()
        backend2.name = "par-backend-01"
        backend2.role = "backend"
        backend2.is_enabled = True
        backend2.is_draining = False
        backend2.zone = "europe"
        backend2.region = "fr"
        backend2.reality_ip = "2.2.2.2"
        backend2.public_domain = ""

        backend_asia = MagicMock()
        backend_asia.id = uuid4()
        backend_asia.name = "sg-backend"
        backend_asia.role = "backend"
        backend_asia.is_enabled = True
        backend_asia.is_draining = False
        backend_asia.zone = "asia"
        backend_asia.region = "sg"
        backend_asia.reality_ip = "3.3.3.3"
        backend_asia.public_domain = ""

        keys = [MagicMock(client_id=f"u{i}", entry_routing_override_backend_tag=None) for i in range(10)]
        node_repo = MagicMock()
        node_repo.get_by_id = AsyncMock(return_value=entry)
        node_repo.list = AsyncMock(return_value=[entry, backend1, backend2, backend_asia])
        key_repo = MagicMock()
        key_repo.list_all_active = AsyncMock(return_value=keys)

        svc = EntryRoutingService(
            session=MagicMock(),
            config=EntryRoutingConfig(
                listen_port=8443,
                reality_private_key="pk",
                reality_short_id="sid",
                reality_server_name="www.cloudflare.com",
                reality_handshake_server="www.cloudflare.com",
                reality_handshake_port=443,
                backend_service_uuid="svc-uuid",
                backend_reality_public_key="pubkey",
                backend_port=443,
            ),
        )
        svc.node_repo = node_repo
        svc.key_repo = key_repo

        spec = await svc.build_spec_for_node(entry_id)
        assert spec is not None
        assert {b.tag for b in spec.backends} == {
            "backend-hel-backend-01",
            "backend-par-backend-01",
        }, "asia backend must be filtered out by zone"
        assert all(b.uuid == "svc-uuid" for b in spec.backends)
        assert all(b.reality_public_key == "pubkey" for b in spec.backends)
        assert len(spec.rules) == 10
        assert {r.outbound_tag for r in spec.rules} <= {b.tag for b in spec.backends}

    async def test_override_pins_user_to_specific_backend(self):
        entry_id = uuid4()
        entry = MagicMock()
        entry.id = entry_id
        entry.role = ROLE_ENTRY
        entry.zone = "europe"
        entry.region = "de"

        backend1 = MagicMock()
        backend1.id = uuid4()
        backend1.name = "hel"
        backend1.role = "backend"
        backend1.is_enabled = True
        backend1.is_draining = False
        backend1.zone = "europe"
        backend1.region = "fi"
        backend1.reality_ip = "1.1.1.1"
        backend1.public_domain = ""

        backend2 = MagicMock()
        backend2.id = uuid4()
        backend2.name = "par"
        backend2.role = "backend"
        backend2.is_enabled = True
        backend2.is_draining = False
        backend2.zone = "europe"
        backend2.region = "fr"
        backend2.reality_ip = "2.2.2.2"
        backend2.public_domain = ""

        forced = MagicMock(client_id="forced-user", entry_routing_override_backend_tag="backend-par")
        free = MagicMock(client_id="free-user", entry_routing_override_backend_tag=None)

        node_repo = MagicMock()
        node_repo.get_by_id = AsyncMock(return_value=entry)
        node_repo.list = AsyncMock(return_value=[entry, backend1, backend2])
        key_repo = MagicMock()
        key_repo.list_all_active = AsyncMock(return_value=[forced, free])

        svc = EntryRoutingService(
            session=MagicMock(),
            config=EntryRoutingConfig(
                backend_service_uuid="svc",
                backend_reality_public_key="pubkey",
            ),
        )
        svc.node_repo = node_repo
        svc.key_repo = key_repo

        spec = await svc.build_spec_for_node(entry_id)
        rules = {r.user_uuid: r.outbound_tag for r in spec.rules}
        assert rules["forced-user"] == "backend-par"
        assert rules["free-user"] in {"backend-hel", "backend-par"}

    async def test_invalid_override_falls_back_to_hash(self):
        entry_id = uuid4()
        entry = MagicMock()
        entry.id = entry_id
        entry.role = ROLE_ENTRY
        entry.zone = "europe"
        entry.region = "de"

        backend = MagicMock()
        backend.id = uuid4()
        backend.name = "hel"
        backend.role = "backend"
        backend.is_enabled = True
        backend.is_draining = False
        backend.zone = "europe"
        backend.region = "fi"
        backend.reality_ip = "1.1.1.1"
        backend.public_domain = ""

        bad = MagicMock(client_id="user-1", entry_routing_override_backend_tag="backend-removed")
        node_repo = MagicMock()
        node_repo.get_by_id = AsyncMock(return_value=entry)
        node_repo.list = AsyncMock(return_value=[entry, backend])
        key_repo = MagicMock()
        key_repo.list_all_active = AsyncMock(return_value=[bad])

        svc = EntryRoutingService(
            session=MagicMock(),
            config=EntryRoutingConfig(
                backend_service_uuid="svc",
                backend_reality_public_key="pubkey",
            ),
        )
        svc.node_repo = node_repo
        svc.key_repo = key_repo

        spec = await svc.build_spec_for_node(entry_id)
        assert spec.rules[0].outbound_tag == "backend-hel"

    async def test_user_assignment_is_stable_across_runs(self):
        entry_id = uuid4()
        entry = MagicMock()
        entry.id = entry_id
        entry.role = ROLE_ENTRY
        entry.zone = "europe"
        entry.region = "de"

        backend1 = MagicMock()
        backend1.id = uuid4()
        backend1.name = "b1"
        backend1.role = "backend"
        backend1.is_enabled = True
        backend1.is_draining = False
        backend1.zone = "europe"
        backend1.region = "fi"
        backend1.reality_ip = "1.1.1.1"
        backend1.public_domain = ""

        backend2 = MagicMock()
        backend2.id = uuid4()
        backend2.name = "b2"
        backend2.role = "backend"
        backend2.is_enabled = True
        backend2.is_draining = False
        backend2.zone = "europe"
        backend2.region = "fr"
        backend2.reality_ip = "2.2.2.2"
        backend2.public_domain = ""

        keys = [MagicMock(client_id=f"u{i}", entry_routing_override_backend_tag=None) for i in range(50)]
        cfg = EntryRoutingConfig(
            listen_port=8443,
            reality_private_key="pk",
            reality_short_id="sid",
            reality_server_name="www.cloudflare.com",
            reality_handshake_server="www.cloudflare.com",
            reality_handshake_port=443,
            backend_service_uuid="svc",
            backend_reality_public_key="pubkey",
        )

        async def _build():
            node_repo = MagicMock()
            node_repo.get_by_id = AsyncMock(return_value=entry)
            node_repo.list = AsyncMock(return_value=[entry, backend1, backend2])
            key_repo = MagicMock()
            key_repo.list_all_active = AsyncMock(return_value=keys)
            svc = EntryRoutingService(session=MagicMock(), config=cfg)
            svc.node_repo = node_repo
            svc.key_repo = key_repo
            return await svc.build_spec_for_node(entry_id)

        spec_a = await _build()
        spec_b = await _build()
        rules_a = sorted((r.user_uuid, r.outbound_tag) for r in spec_a.rules)
        rules_b = sorted((r.user_uuid, r.outbound_tag) for r in spec_b.rules)
        assert rules_a == rules_b
        tags = {r.outbound_tag for r in spec_a.rules}
        assert len(tags) == 2, "both backends should receive at least one user across 50 keys"


@pytest.mark.asyncio
class TestAdminServiceSetOverride:
    async def _build(self, *, key, backends):
        from services.routing.entry.service import EntryRoutingAdminService
        cfg = EntryRoutingConfig(
            backend_service_uuid="svc",
            backend_reality_public_key="pubkey",
        )
        svc = EntryRoutingAdminService(session=MagicMock(), config=cfg)

        async def fake_collect():
            return {b.tag for b in backends}

        svc._collect_valid_backend_tags = fake_collect
        svc.key_repo = MagicMock()
        svc.key_repo.get_by_id = AsyncMock(return_value=key)
        svc.key_repo.update_by_id = AsyncMock()
        return svc

    async def test_unknown_tag_raises(self):
        from services.routing.entry.exceptions import UnknownBackendTagError
        from services.routing.entry.schemas import EntryRoutingBackend
        key = MagicMock()
        key.id = uuid4()
        key.client_id = "u1"
        key.entry_routing_override_backend_tag = None
        backends = [EntryRoutingBackend(tag="backend-a", server="1.1.1.1", server_port=443, uuid="x")]
        svc = await self._build(key=key, backends=backends)
        with pytest.raises(UnknownBackendTagError):
            await svc.set_key_override(key_id=key.id, backend_tag="backend-removed")

    async def test_returns_none_when_key_missing(self):
        svc = await self._build(key=None, backends=[])
        result = await svc.set_key_override(key_id=uuid4(), backend_tag=None)
        assert result is None

    async def test_clearing_override_does_not_validate(self):
        key = MagicMock()
        key.id = uuid4()
        key.client_id = "u1"
        key.entry_routing_override_backend_tag = "stale-tag"
        svc = await self._build(key=key, backends=[])
        change = await svc.set_key_override(key_id=key.id, backend_tag=None)
        assert change is not None
        assert change.changed is True
        assert change.current is None


class TestAdminServiceEffectiveBackend:
    @staticmethod
    def _eff(client_id, override=None, tags=("backend-a", "backend-b")):
        return EntryRoutingAdminService._effective_backend(
            client_id=client_id,
            override=override,
            backend_tags_sorted=list(tags),
            valid_tags=set(tags),
        )

    def test_returns_none_when_no_backends(self):
        assert self._eff("u1", tags=()) is None

    def test_override_takes_priority(self):
        assert self._eff("u1", override="backend-b") == "backend-b"

    def test_invalid_override_falls_back_to_hash(self):
        result = self._eff("u1", override="backend-removed")
        assert result in {"backend-a", "backend-b"}

    def test_hash_is_deterministic_for_same_id(self):
        assert self._eff("u-stable") == self._eff("u-stable")

    def test_distribution_uses_all_backends(self):
        seen = {self._eff(f"u{i}") for i in range(50)}
        assert seen == {"backend-a", "backend-b"}
