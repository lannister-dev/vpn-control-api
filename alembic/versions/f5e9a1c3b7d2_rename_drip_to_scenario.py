"""rename drip_* tables to scenario_* (extracted into services/scenarios package)

Revision ID: f5e9a1c3b7d2
Revises: d7c4a1e9f0b2
Create Date: 2026-06-26
"""

from typing import Union

from alembic import op

revision: str = "f5e9a1c3b7d2"
down_revision: Union[str, None] = "d7c4a1e9f0b2"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.rename_table("drip_campaign", "scenario_campaign")
    op.rename_table("drip_node", "scenario_node")
    op.rename_table("drip_edge", "scenario_edge")
    op.rename_table("user_campaign_state", "scenario_state")

    op.execute("ALTER INDEX ix_drip_edge_campaign_from RENAME TO ix_scenario_edge_campaign_from")
    op.execute("ALTER INDEX ix_user_campaign_due RENAME TO ix_scenario_state_due")
    op.execute(
        "ALTER TABLE scenario_node "
        "RENAME CONSTRAINT uq_drip_node_campaign_key TO uq_scenario_node_campaign_key"
    )
    op.execute(
        "ALTER TABLE scenario_state "
        "RENAME CONSTRAINT uq_user_campaign TO uq_scenario_state_user_campaign"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE scenario_state "
        "RENAME CONSTRAINT uq_scenario_state_user_campaign TO uq_user_campaign"
    )
    op.execute(
        "ALTER TABLE scenario_node "
        "RENAME CONSTRAINT uq_scenario_node_campaign_key TO uq_drip_node_campaign_key"
    )
    op.execute("ALTER INDEX ix_scenario_state_due RENAME TO ix_user_campaign_due")
    op.execute("ALTER INDEX ix_scenario_edge_campaign_from RENAME TO ix_drip_edge_campaign_from")

    op.rename_table("scenario_state", "user_campaign_state")
    op.rename_table("scenario_edge", "drip_edge")
    op.rename_table("scenario_node", "drip_node")
    op.rename_table("scenario_campaign", "drip_campaign")
