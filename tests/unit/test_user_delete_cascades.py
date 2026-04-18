from services.placements.model import UserPlacement
from services.traffic.users.model import TrafficUsage
from services.vpn.keys.models import KeyAssignment, VpnKey
from services.vpn.subscriptions.model import (
    Subscription,
    SubscriptionDevice,
    SubscriptionDeviceKey,
)


def _fk_ondelete(table, column_name: str) -> str | None:
    column = table.__table__.c[column_name]
    fk = next(iter(column.foreign_keys))
    return fk.ondelete


def test_user_delete_cascades_across_subscription_and_key_graph():
    assert _fk_ondelete(Subscription, "user_id") == "CASCADE"
    assert _fk_ondelete(VpnKey, "user_id") == "CASCADE"
    assert _fk_ondelete(SubscriptionDevice, "subscription_id") == "CASCADE"
    assert _fk_ondelete(SubscriptionDeviceKey, "subscription_device_id") == "CASCADE"
    assert _fk_ondelete(SubscriptionDeviceKey, "vpn_key_id") == "CASCADE"
    assert _fk_ondelete(KeyAssignment, "key_id") == "CASCADE"
    assert _fk_ondelete(UserPlacement, "key_id") == "CASCADE"
    assert _fk_ondelete(TrafficUsage, "key_id") == "CASCADE"
