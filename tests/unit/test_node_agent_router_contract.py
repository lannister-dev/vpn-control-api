from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.nodes.router import (
    get_placements_page,
    sync_report,
)
from services.nodes.schemas import NodeRole, NodeSyncReportIn
from services.placements.schemas import (
    PlacementAppliedState,
    PlacementAssignmentOut,
    PlacementDesiredState,
    PlacementPageOut,
)
from services.vpn.keys.schemas import VpnProtocol, VpnTransport


@pytest.mark.asyncio
async def test_backend_placements_for_node_contract():
    placement_id = uuid4()
    item = PlacementAssignmentOut(
        id=placement_id,
        key_id=uuid4(),
        op_version=7,
        desired_state=PlacementDesiredState.active,
        applied_state=PlacementAppliedState.pending,
        applied_version=0,
        backend_node_id=uuid4(),
        protocol=VpnProtocol.vless,
        client_id="test-client-id",
        transport=VpnTransport.ws,
        valid_until=None,
        is_revoked=False,
        backend_internal_wg_ip="10.10.10.10",
        backend_xray_api_port=10085,
    )
    service = SimpleNamespace(
        get_page_for_backend=AsyncMock(return_value=PlacementPageOut(items=[item], next_cursor="7:cursor")),
    )
    node = SimpleNamespace(id=uuid4(), role=NodeRole.backend.value)

    page = await get_placements_page(
        node=node,
        cursor=None,
        limit=200,
        service=service,
    )
    assert page.next_cursor == "7:cursor"
    assert page.items[0].id == placement_id
    service.get_page_for_backend.assert_awaited_once_with(
        node=node,
        cursor=None,
        limit=200,
    )


@pytest.mark.asyncio
async def test_router_maps_cursor_value_error_to_422():
    placement_service = SimpleNamespace(
        get_page_for_backend=AsyncMock(side_effect=ValueError("Invalid cursor")),
    )

    with pytest.raises(HTTPException) as placement_exc:
        await get_placements_page(
            node=SimpleNamespace(id=uuid4(), role=NodeRole.backend.value),
            cursor="bad",
            limit=200,
            service=placement_service,
        )
    assert placement_exc.value.status_code == 422
    assert placement_exc.value.detail == "Invalid cursor"


@pytest.mark.asyncio
async def test_sync_report_contract():
    service = SimpleNamespace(
        handle_sync_report=AsyncMock(return_value=True),
    )
    node = SimpleNamespace(id=uuid4(), role=NodeRole.backend.value)
    payload = NodeSyncReportIn(synced_count=12, config_version=8)

    out = await sync_report(
        payload=payload,
        node=node,
        service=service,
    )

    assert out.status == "accepted"
    service.handle_sync_report.assert_awaited_once_with(node=node, payload=payload)


@pytest.mark.asyncio
async def test_sync_report_contract_skipped_status():
    service = SimpleNamespace(
        handle_sync_report=AsyncMock(return_value=False),
    )
    node = SimpleNamespace(id=uuid4(), role=NodeRole.backend.value)
    payload = NodeSyncReportIn(synced_count=12, config_version=8)

    out = await sync_report(
        payload=payload,
        node=node,
        service=service,
    )

    assert out.status == "skipped"
    service.handle_sync_report.assert_awaited_once_with(node=node, payload=payload)
