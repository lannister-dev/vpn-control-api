from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from uuid import uuid4
from datetime import datetime, timezone

from services.nodes.service import NodeAgentService
from services.vpn.keys.schemas import (
    AssignmentDesiredState,
    AssignmentAppliedState,
    AssignmentStatus,
    VpnProtocol,
    VpnTransport,
)


def _make_key(*, is_revoked=False, valid_until=None):
    """Create a mock VpnKey object."""
    key = MagicMock()
    key.protocol = VpnProtocol.vless.value
    key.transport = VpnTransport.ws.value
    key.client_id = "test-client-id"
    key.is_revoked = is_revoked
    key.valid_until = valid_until
    key.traffic_limit_mb = 1000
    return key


def _make_assignment(*, desired_state="present", applied_state=None, status="pending", op_version=1):
    """Create a mock KeyAssignment object."""
    a = MagicMock()
    a.id = uuid4()
    a.key_id = uuid4()
    a.desired_state = desired_state
    a.applied_state = applied_state
    a.status = status
    a.op_version = op_version
    return a


@pytest.fixture()
def service(async_session):
    return NodeAgentService(async_session)


class TestBuildAssignments:
    def test_active_key_keeps_desired_state(self, service):
        key = _make_key(valid_until=datetime(2030, 1, 1, tzinfo=timezone.utc))
        assignment = _make_assignment(desired_state="present")

        result = service._build_assignments([(assignment, key)])
        assert len(result) == 1
        assert result[0].desired_state == AssignmentDesiredState.present

    def test_revoked_key_overrides_to_absent(self, service):
        key = _make_key(is_revoked=True, valid_until=datetime(2030, 1, 1, tzinfo=timezone.utc))
        assignment = _make_assignment(desired_state="present")

        result = service._build_assignments([(assignment, key)])
        assert result[0].desired_state == AssignmentDesiredState.absent

    def test_expired_key_overrides_to_absent(self, service):
        past = datetime(2020, 1, 1, tzinfo=timezone.utc)
        key = _make_key(valid_until=past)
        assignment = _make_assignment(desired_state="present")

        result = service._build_assignments([(assignment, key)])
        assert result[0].desired_state == AssignmentDesiredState.absent

    def test_expired_naive_datetime_treated_as_utc(self, service):
        past = datetime(2020, 1, 1)  # naive
        key = _make_key(valid_until=past)
        assignment = _make_assignment(desired_state="present")

        result = service._build_assignments([(assignment, key)])
        assert result[0].desired_state == AssignmentDesiredState.absent

    def test_applied_state_none_becomes_unknown(self, service):
        key = _make_key(valid_until=datetime(2030, 1, 1, tzinfo=timezone.utc))
        assignment = _make_assignment(applied_state=None)

        result = service._build_assignments([(assignment, key)])
        assert result[0].applied_state == AssignmentAppliedState.unknown

    def test_applied_state_present(self, service):
        key = _make_key(valid_until=datetime(2030, 1, 1, tzinfo=timezone.utc))
        assignment = _make_assignment(applied_state="present")

        result = service._build_assignments([(assignment, key)])
        assert result[0].applied_state == AssignmentAppliedState.present

    def test_status_applied_when_desired_matches_applied(self, service):
        key = _make_key(valid_until=datetime(2030, 1, 1, tzinfo=timezone.utc))
        assignment = _make_assignment(
            desired_state="present", applied_state="present", status="applied",
        )

        result = service._build_assignments([(assignment, key)])
        assert result[0].status == AssignmentStatus.applied

    def test_status_reset_to_pending_when_desired_diverges(self, service):
        key = _make_key(valid_until=datetime(2030, 1, 1, tzinfo=timezone.utc))
        assignment = _make_assignment(
            desired_state="present", applied_state="absent", status="applied",
        )

        result = service._build_assignments([(assignment, key)])
        assert result[0].status == AssignmentStatus.pending

    def test_empty_rows(self, service):
        result = service._build_assignments([])
        assert result == []

    def test_valid_until_none_no_expiry(self, service):
        key = _make_key(valid_until=None)
        assignment = _make_assignment(desired_state="present")

        result = service._build_assignments([(assignment, key)])
        assert result[0].desired_state == AssignmentDesiredState.present
