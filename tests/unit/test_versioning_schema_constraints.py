from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

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
