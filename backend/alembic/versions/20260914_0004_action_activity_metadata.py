"""Add immutable display metadata for action activity.

Revision ID: 20260914_0004
Revises: 20260914_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260914_0004"
down_revision: str | None = "20260914_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("unsubscribe_actions") as batch:
        batch.add_column(
            sa.Column(
                "display_sender",
                sa.String(500),
                nullable=False,
                server_default="Unknown sender",
            )
        )
        batch.add_column(
            sa.Column(
                "display_subject",
                sa.Text(),
                nullable=False,
                server_default="(no subject)",
            )
        )
        batch.add_column(
            sa.Column(
                "target_display",
                sa.String(500),
                nullable=False,
                server_default="Unknown destination",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("unsubscribe_actions") as batch:
        batch.drop_column("target_display")
        batch.drop_column("display_subject")
        batch.drop_column("display_sender")
