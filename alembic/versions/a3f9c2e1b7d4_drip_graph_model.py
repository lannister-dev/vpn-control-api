"""drip graph model: drip_node + drip_edge, replace linear drip_step

Revision ID: a3f9c2e1b7d4
Revises: c5e2f8a4b9d1
Create Date: 2026-06-25
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a3f9c2e1b7d4"
down_revision: Union[str, None] = "c5e2f8a4b9d1"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.add_column(
        "drip_campaign",
        sa.Column("entry_node_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "user_campaign_state",
        sa.Column("current_node_key", sa.String(length=64), nullable=True),
    )

    op.create_table(
        "drip_node",
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("drip_campaign.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node_key", sa.String(length=64), nullable=False),
        sa.Column("node_type", sa.String(length=16), nullable=False),
        sa.Column("pos_cx", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("pos_top", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("delay_seconds", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("condition", sa.String(length=32), nullable=False, server_default=sa.text("'always'")),
        sa.Column("text_body", sa.Text(), nullable=True),
        sa.Column("inline_buttons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("media_kind", sa.String(length=16), nullable=True),
        sa.Column("media_url", sa.String(length=512), nullable=True),
        sa.Column("check_kind", sa.String(length=32), nullable=True),
        sa.Column("conversion", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "node_key", name="uq_drip_node_campaign_key"),
    )

    op.create_table(
        "drip_edge",
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("drip_campaign.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_key", sa.String(length=64), nullable=False),
        sa.Column("to_key", sa.String(length=64), nullable=False),
        sa.Column("branch", sa.String(length=8), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_drip_edge_campaign_from", "drip_edge", ["campaign_id", "from_key"])

    # ── Convert existing linear drip_step chains into message nodes + edges ──
    op.execute(
        """
        INSERT INTO drip_node
            (id, campaign_id, node_key, node_type, pos_cx, pos_top, delay_seconds,
             condition, text_body, inline_buttons, media_kind, media_url,
             conversion, created_at, updated_at, is_active)
        SELECT gen_random_uuid(), campaign_id, 'm' || (step_order + 1), 'message', 320, 0,
               delay_seconds, condition, text_body, inline_buttons, media_kind, media_url,
               false, now(), now(), true
        FROM drip_step
        """
    )
    op.execute(
        """
        INSERT INTO drip_node
            (id, campaign_id, node_key, node_type, pos_cx, pos_top, delay_seconds,
             condition, conversion, label, created_at, updated_at, is_active)
        SELECT gen_random_uuid(), campaign_id, 'end', 'end', 320, 0, 0,
               'always', false, 'Цепочка завершена', now(), now(), true
        FROM (SELECT DISTINCT campaign_id FROM drip_step) c
        """
    )
    op.execute(
        """
        INSERT INTO drip_edge
            (id, campaign_id, from_key, to_key, branch, created_at, updated_at, is_active)
        SELECT gen_random_uuid(), s.campaign_id, 'm' || (s.step_order + 1),
               'm' || (s.step_order + 2), NULL, now(), now(), true
        FROM drip_step s
        WHERE EXISTS (
            SELECT 1 FROM drip_step s2
            WHERE s2.campaign_id = s.campaign_id AND s2.step_order = s.step_order + 1
        )
        """
    )
    op.execute(
        """
        INSERT INTO drip_edge
            (id, campaign_id, from_key, to_key, branch, created_at, updated_at, is_active)
        SELECT gen_random_uuid(), s.campaign_id, 'm' || (s.step_order + 1),
               'end', NULL, now(), now(), true
        FROM drip_step s
        WHERE NOT EXISTS (
            SELECT 1 FROM drip_step s2
            WHERE s2.campaign_id = s.campaign_id AND s2.step_order = s.step_order + 1
        )
        """
    )
    op.execute(
        """
        UPDATE drip_campaign SET entry_node_key = 'm1'
        WHERE id IN (SELECT DISTINCT campaign_id FROM drip_step)
        """
    )
    op.execute(
        "UPDATE user_campaign_state SET current_node_key = 'm' || (current_step + 1)"
    )

    op.drop_table("drip_step")
    op.drop_column("user_campaign_state", "current_step")


def downgrade() -> None:
    op.add_column(
        "user_campaign_state",
        sa.Column("current_step", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_table(
        "drip_step",
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("drip_campaign.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("delay_seconds", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("condition", sa.String(length=32), nullable=False, server_default=sa.text("'always'")),
        sa.Column("text_body", sa.Text(), nullable=False),
        sa.Column("inline_buttons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("media_kind", sa.String(length=16), nullable=True),
        sa.Column("media_url", sa.String(length=512), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "step_order", name="uq_drip_step_campaign_order"),
    )
    op.drop_index("ix_drip_edge_campaign_from", table_name="drip_edge")
    op.drop_table("drip_edge")
    op.drop_table("drip_node")
    op.drop_column("user_campaign_state", "current_node_key")
    op.drop_column("drip_campaign", "entry_node_key")
