from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.backend_peers.schemas import (
    BackendPeerAppliedState,
    BackendPeerPageItemOut,
    BackendPeerPageOut,
    BackendPeerReportIn,
    BackendPeerStatus,
)
from services.nodes.router import (
    get_backend_peers_page,
    get_placements_page,
    report_backend_peer,
    report_placement,
)
from services.nodes.schemas import NodeRole
from services.placements.schemas import (
    PlacementAppliedState,
    PlacementAssignmentOut,
    PlacementDesiredState,
    PlacementPageOut,
    PlacementReportIn,
)
from services.vpn.keys.schemas import VpnProtocol, VpnTransport


@pytest.mark.asyncio
async def test_gateway_placements_page_and_report_contract():
    placement_id = uuid4()
    item = PlacementAssignmentOut(
        id=placement_id,
        key_id=uuid4(),
        op_version=7,
        desired_state=PlacementDesiredState.active,
        applied_state=PlacementAppliedState.pending,
        applied_version=0,
        backend_node_id=uuid4(),
        gateway_node_id=uuid4(),
        protocol=VpnProtocol.vless,
        client_id="test-client-id",
        transport=VpnTransport.ws,
        valid_until=None,
        is_revoked=False,
        backend_internal_wg_ip="10.10.10.10",
        backend_xray_api_port=10085,
    )
    service = SimpleNamespace(
        get_page_for_gateway=AsyncMock(return_value=PlacementPageOut(items=[item], next_cursor="7:cursor")),
        report_for_gateway=AsyncMock(side_effect=["applied", "skipped_idempotent", "skipped_stale"]),
    )
    node = SimpleNamespace(id=uuid4(), role=NodeRole.gateway.value)

    page = await get_placements_page(node=node, cursor=None, limit=200, service=service)
    assert page.next_cursor == "7:cursor"
    assert page.items[0].id == placement_id

    payload = PlacementReportIn(op_version=7, applied_state=PlacementAppliedState.applied)
    report_1 = await report_placement(
        placement_id=placement_id,
        payload=payload,
        node=node,
        service=service,
    )
    report_2 = await report_placement(
        placement_id=placement_id,
        payload=payload,
        node=node,
        service=service,
    )
    report_3 = await report_placement(
        placement_id=placement_id,
        payload=payload,
        node=node,
        service=service,
    )
    assert report_1.status == "applied"
    assert report_2.status == "skipped_idempotent"
    assert report_3.status == "skipped_stale"


@pytest.mark.asyncio
async def test_backend_peers_page_and_report_contract():
    peer_id = uuid4()
    item = BackendPeerPageItemOut(
        id=peer_id,
        backend_node_id=uuid4(),
        gateway_node_id=uuid4(),
        internal_uuid=str(uuid4()),
        status=BackendPeerStatus.active,
        applied_state=BackendPeerAppliedState.pending,
        op_version=3,
        applied_version=0,
        last_error=None,
        gateway_public_domain="gw.example.com",
    )
    service = SimpleNamespace(
        get_page_for_backend=AsyncMock(return_value=BackendPeerPageOut(items=[item], next_cursor="3:cursor")),
        report_for_backend=AsyncMock(side_effect=["pending", "error", "applied"]),
    )
    node = SimpleNamespace(id=uuid4(), role=NodeRole.backend.value)

    page = await get_backend_peers_page(node=node, cursor=None, limit=200, service=service)
    assert page.next_cursor == "3:cursor"
    assert page.items[0].id == peer_id

    payload = BackendPeerReportIn(op_version=3, applied_state=BackendPeerAppliedState.applied)
    report_1 = await report_backend_peer(
        peer_id=peer_id,
        payload=payload,
        node=node,
        service=service,
    )
    report_2 = await report_backend_peer(
        peer_id=peer_id,
        payload=payload,
        node=node,
        service=service,
    )
    report_3 = await report_backend_peer(
        peer_id=peer_id,
        payload=payload,
        node=node,
        service=service,
    )
    assert report_1.status == "pending"
    assert report_2.status == "error"
    assert report_3.status == "applied"


@pytest.mark.asyncio
async def test_router_maps_cursor_value_error_to_422():
    placement_service = SimpleNamespace(
        get_page_for_gateway=AsyncMock(side_effect=ValueError("Invalid cursor")),
        report_for_gateway=AsyncMock(return_value="applied"),
    )
    backend_service = SimpleNamespace(
        get_page_for_backend=AsyncMock(side_effect=ValueError("Invalid cursor")),
        report_for_backend=AsyncMock(return_value="applied"),
    )

    with pytest.raises(HTTPException) as placement_exc:
        await get_placements_page(
            node=SimpleNamespace(id=uuid4(), role=NodeRole.gateway.value),
            cursor="bad",
            limit=200,
            service=placement_service,
        )
    assert placement_exc.value.status_code == 422
    assert placement_exc.value.detail == "Invalid cursor"

    with pytest.raises(HTTPException) as backend_exc:
        await get_backend_peers_page(
            node=SimpleNamespace(id=uuid4(), role=NodeRole.backend.value),
            cursor="bad",
            limit=200,
            service=backend_service,
        )
    assert backend_exc.value.status_code == 422
    assert backend_exc.value.detail == "Invalid cursor"
