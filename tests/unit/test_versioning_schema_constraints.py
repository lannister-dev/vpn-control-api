from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from services.backend_peers.schemas import (
    BackendPeerAppliedState,
    BackendPeerInternalCreate,
    BackendPeerReportIn,
    BackendPeerStatus,
)
from services.placements.schemas import PlacementAppliedState, PlacementReportIn, PlacementUpdate


def test_placement_report_rejects_non_positive_op_version():
    with pytest.raises(ValidationError):
        PlacementReportIn(op_version=0, applied_state=PlacementAppliedState.applied)


def test_placement_update_rejects_negative_applied_version():
    with pytest.raises(ValidationError):
        PlacementUpdate(
            applied_state=PlacementAppliedState.applied,
            applied_version=-1,
            updated_at=datetime.now(timezone.utc),
        )


def test_backend_peer_report_rejects_non_positive_op_version():
    with pytest.raises(ValidationError):
        BackendPeerReportIn(op_version=0, applied_state=BackendPeerAppliedState.applied)


def test_backend_peer_internal_create_rejects_negative_applied_version():
    with pytest.raises(ValidationError):
        BackendPeerInternalCreate(
            backend_node_id="3fa85f64-5717-4562-b3fc-2c963f66afa6",
            gateway_node_id="7f8e19f6-16c6-43c4-83c0-8a7f77fc7f99",
            internal_uuid="a5cb1c49-443f-45f6-9c8d-f4e09d8f3990",
            status=BackendPeerStatus.active,
            applied_state=BackendPeerAppliedState.pending,
            op_version=1,
            applied_version=-1,
            last_error=None,
            is_active=True,
        )
