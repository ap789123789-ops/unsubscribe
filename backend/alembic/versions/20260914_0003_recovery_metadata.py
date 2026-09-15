"""Add restartable scan metadata.

Revision ID: 20260914_0003
Revises: 20260914_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260914_0003"
down_revision: str | None = "20260914_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scan_checkpoints",
        sa.Column("days", sa.Integer(), nullable=False, server_default="30"),
    )
    op.add_column(
        "scan_checkpoints",
        sa.Column("max_messages", sa.Integer(), nullable=False, server_default="500"),
    )
    op.rename_table("action_events", "action_events_before_stream_sequence")
    op.create_table(
        "action_events",
        sa.Column("stream_sequence", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id", sa.String(36), nullable=False, unique=True),
        sa.Column(
            "action_id",
            sa.String(36),
            sa.ForeignKey("unsubscribe_actions.id"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("from_state", sa.String(40), nullable=True),
        sa.Column("to_state", sa.String(40), nullable=False),
        sa.Column("evidence_code", sa.String(100), nullable=True),
        sa.Column("safe_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("action_id", "sequence"),
    )
    op.execute(
        """INSERT INTO action_events
        (id, action_id, sequence, from_state, to_state, evidence_code, safe_detail, created_at)
        SELECT id, action_id, sequence, from_state, to_state, evidence_code, safe_detail, created_at
        FROM action_events_before_stream_sequence
        ORDER BY created_at, action_id, sequence"""
    )
    op.drop_table("action_events_before_stream_sequence")


def downgrade() -> None:
    op.rename_table("action_events", "action_events_with_stream_sequence")
    op.create_table(
        "action_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "action_id",
            sa.String(36),
            sa.ForeignKey("unsubscribe_actions.id"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("from_state", sa.String(40), nullable=True),
        sa.Column("to_state", sa.String(40), nullable=False),
        sa.Column("evidence_code", sa.String(100), nullable=True),
        sa.Column("safe_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("action_id", "sequence"),
    )
    op.execute(
        """INSERT INTO action_events
        (id, action_id, sequence, from_state, to_state, evidence_code, safe_detail, created_at)
        SELECT id, action_id, sequence, from_state, to_state, evidence_code, safe_detail, created_at
        FROM action_events_with_stream_sequence
        ORDER BY stream_sequence"""
    )
    op.drop_table("action_events_with_stream_sequence")
    with op.batch_alter_table("scan_checkpoints") as batch:
        batch.drop_column("max_messages")
        batch.drop_column("days")
