"""Add durable scan checkpoints.

Revision ID: 20260914_0002
Revises: 20260914_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260914_0002"
down_revision: str | None = "20260914_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scan_checkpoints",
        sa.Column("scan_id", sa.String(100), primary_key=True),
        sa.Column("next_page_token", sa.String(500), nullable=True),
        sa.Column("seen_message_ids_json", sa.Text(), nullable=False),
        sa.Column("completed", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("scan_checkpoints")

