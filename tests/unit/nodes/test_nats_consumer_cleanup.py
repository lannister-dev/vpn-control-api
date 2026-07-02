from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from services.nodes.reconcilers.nats_consumer_cleanup import NatsConsumerCleanupReconciler


def _rec(nats):
    lock = MagicMock()
    lock.hold = MagicMock()
    return NatsConsumerCleanupReconciler(nats_client=nats, tick_lock=lock)


async def test_removes_only_orphan_consumers():
    active_id = uuid4()
    orphan_id = uuid4()
    nats = MagicMock()
    nats.list_consumer_names = AsyncMock(return_value=[
        f"node-agent-prod-{active_id}-sync-acks",
        f"node-agent-prod-{orphan_id}-sync-acks",
        f"agent_{orphan_id}_commands",
        "vpn-control-api-prod-heartbeats",
    ])
    nats.delete_consumer = AsyncMock(return_value=True)
    rec = _rec(nats)

    fake_session = AsyncMock()
    fake_session.__aenter__.return_value = fake_session
    fake_session.__aexit__.return_value = False
    rec._session_maker = MagicMock(return_value=fake_session)

    node = SimpleNamespace(id=active_id)
    with patch(
        "services.nodes.reconcilers.nats_consumer_cleanup.VpnNodeRepository"
    ) as RepoCls:
        RepoCls.return_value.list_active_with_agent_state = AsyncMock(return_value=[(node, None)])
        removed = await rec.tick()

    deleted = {c.args[1] for c in nats.delete_consumer.await_args_list}
    assert f"node-agent-prod-{orphan_id}-sync-acks" in deleted
    assert f"agent_{orphan_id}_commands" in deleted
    assert f"node-agent-prod-{active_id}-sync-acks" not in deleted
    assert "vpn-control-api-prod-heartbeats" not in deleted
    assert removed == 6  # 3 streams × 2 orphan each


async def test_no_active_nodes_skips():
    nats = MagicMock()
    nats.list_consumer_names = AsyncMock(return_value=["node-agent-prod-x-sync-acks"])
    nats.delete_consumer = AsyncMock()
    rec = _rec(nats)
    fake_session = AsyncMock()
    fake_session.__aenter__.return_value = fake_session
    fake_session.__aexit__.return_value = False
    rec._session_maker = MagicMock(return_value=fake_session)
    with patch(
        "services.nodes.reconcilers.nats_consumer_cleanup.VpnNodeRepository"
    ) as RepoCls:
        RepoCls.return_value.list_active_with_agent_state = AsyncMock(return_value=[])
        removed = await rec.tick()
    assert removed == 0
    nats.delete_consumer.assert_not_awaited()
