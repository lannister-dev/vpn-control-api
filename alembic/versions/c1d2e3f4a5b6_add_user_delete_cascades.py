"""add user delete cascades

Revision ID: c1d2e3f4a5b6
Revises: bb8d2e3f4a5b
Create Date: 2026-03-31
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "bb8d2e3f4a5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _replace_fk(
    *,
    table_name: str,
    constraint_name: str,
    local_cols: list[str],
    remote_table: str,
    remote_cols: list[str],
    ondelete: str | None,
) -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    fk_by_name = {
        fk["name"]: fk
        for fk in inspector.get_foreign_keys(table_name)
        if fk.get("name")
    }
    existing = fk_by_name.get(constraint_name)

    if existing is not None:
        existing_ondelete = (existing.get("options") or {}).get("ondelete")
        if existing_ondelete == ondelete:
            return

    with op.batch_alter_table(table_name) as batch_op:
        if existing is not None:
            batch_op.drop_constraint(constraint_name, type_="foreignkey")
        batch_op.create_foreign_key(
            constraint_name,
            remote_table,
            local_cols,
            remote_cols,
            ondelete=ondelete,
        )


def upgrade() -> None:
    _replace_fk(
        table_name="subscription",
        constraint_name="subscription_user_id_fkey",
        local_cols=["user_id"],
        remote_table="user",
        remote_cols=["id"],
        ondelete="CASCADE",
    )
    _replace_fk(
        table_name="vpn_key",
        constraint_name="vpn_key_user_id_fkey",
        local_cols=["user_id"],
        remote_table="user",
        remote_cols=["id"],
        ondelete="CASCADE",
    )
    _replace_fk(
        table_name="subscription_device",
        constraint_name="subscription_device_subscription_id_fkey",
        local_cols=["subscription_id"],
        remote_table="subscription",
        remote_cols=["id"],
        ondelete="CASCADE",
    )
    _replace_fk(
        table_name="subscription_device_key",
        constraint_name="subscription_device_key_subscription_device_id_fkey",
        local_cols=["subscription_device_id"],
        remote_table="subscription_device",
        remote_cols=["id"],
        ondelete="CASCADE",
    )
    _replace_fk(
        table_name="subscription_device_key",
        constraint_name="subscription_device_key_vpn_key_id_fkey",
        local_cols=["vpn_key_id"],
        remote_table="vpn_key",
        remote_cols=["id"],
        ondelete="CASCADE",
    )
    _replace_fk(
        table_name="key_assignment",
        constraint_name="key_assignment_key_id_fkey",
        local_cols=["key_id"],
        remote_table="vpn_key",
        remote_cols=["id"],
        ondelete="CASCADE",
    )
    _replace_fk(
        table_name="user_placement",
        constraint_name="user_placement_key_id_fkey",
        local_cols=["key_id"],
        remote_table="vpn_key",
        remote_cols=["id"],
        ondelete="CASCADE",
    )
    _replace_fk(
        table_name="traffic_usage",
        constraint_name="traffic_usage_key_id_fkey",
        local_cols=["key_id"],
        remote_table="vpn_key",
        remote_cols=["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    _replace_fk(
        table_name="subscription",
        constraint_name="subscription_user_id_fkey",
        local_cols=["user_id"],
        remote_table="user",
        remote_cols=["id"],
        ondelete=None,
    )
    _replace_fk(
        table_name="vpn_key",
        constraint_name="vpn_key_user_id_fkey",
        local_cols=["user_id"],
        remote_table="user",
        remote_cols=["id"],
        ondelete=None,
    )
    _replace_fk(
        table_name="subscription_device",
        constraint_name="subscription_device_subscription_id_fkey",
        local_cols=["subscription_id"],
        remote_table="subscription",
        remote_cols=["id"],
        ondelete=None,
    )
    _replace_fk(
        table_name="subscription_device_key",
        constraint_name="subscription_device_key_subscription_device_id_fkey",
        local_cols=["subscription_device_id"],
        remote_table="subscription_device",
        remote_cols=["id"],
        ondelete=None,
    )
    _replace_fk(
        table_name="subscription_device_key",
        constraint_name="subscription_device_key_vpn_key_id_fkey",
        local_cols=["vpn_key_id"],
        remote_table="vpn_key",
        remote_cols=["id"],
        ondelete=None,
    )
    _replace_fk(
        table_name="key_assignment",
        constraint_name="key_assignment_key_id_fkey",
        local_cols=["key_id"],
        remote_table="vpn_key",
        remote_cols=["id"],
        ondelete=None,
    )
    _replace_fk(
        table_name="user_placement",
        constraint_name="user_placement_key_id_fkey",
        local_cols=["key_id"],
        remote_table="vpn_key",
        remote_cols=["id"],
        ondelete=None,
    )
    _replace_fk(
        table_name="traffic_usage",
        constraint_name="traffic_usage_key_id_fkey",
        local_cols=["key_id"],
        remote_table="vpn_key",
        remote_cols=["id"],
        ondelete=None,
    )
