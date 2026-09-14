"""Create the V1 privacy-safe schema.

Revision ID: 20260914_0001
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260914_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("credential_ref", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "scan_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("query", sa.String(500), nullable=False),
        sa.Column("max_messages", sa.Integer(), nullable=False),
        sa.Column("next_page_token", sa.String(500), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("processed_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "messages",
        sa.Column("gmail_id", sa.String(255), primary_key=True),
        sa.Column("scan_id", sa.String(36), sa.ForeignKey("scan_jobs.id"), nullable=False),
        sa.Column("thread_id", sa.String(255), nullable=False),
        sa.Column("sender_address", sa.String(320), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("list_id", sa.String(500), nullable=True),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("safe_excerpt", sa.Text(), nullable=False),
    )
    op.create_table(
        "classifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("gmail_id", sa.String(255), sa.ForeignKey("messages.gmail_id"), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reason_evidence_json", sa.Text(), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
    )
    op.create_table(
        "subscription_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("grouping_key", sa.String(500), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("method", sa.String(40), nullable=False),
        sa.Column("sanitized_target", sa.Text(), nullable=False),
        sa.UniqueConstraint("grouping_key", "revision"),
    )
    op.create_table(
        "candidate_messages",
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("subscription_candidates.id"),
            primary_key=True,
        ),
        sa.Column(
            "gmail_id", sa.String(255), sa.ForeignKey("messages.gmail_id"), primary_key=True
        ),
    )
    op.create_table(
        "action_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("digest", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "unsubscribe_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("plan_id", sa.String(36), sa.ForeignKey("action_plans.id"), nullable=False),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("subscription_candidates.id"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        sa.Column("method", sa.String(40), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("encrypted_payload", sa.LargeBinary(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("outbound_message_id", sa.String(500), nullable=True),
        sa.Column("external_id", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "action_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "action_id", sa.String(36), sa.ForeignKey("unsubscribe_actions.id"), nullable=False
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("from_state", sa.String(40), nullable=True),
        sa.Column("to_state", sa.String(40), nullable=False),
        sa.Column("evidence_code", sa.String(100), nullable=True),
        sa.Column("safe_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("action_id", "sequence"),
    )


def downgrade() -> None:
    for table in (
        "action_events",
        "unsubscribe_actions",
        "action_plans",
        "candidate_messages",
        "subscription_candidates",
        "classifications",
        "messages",
        "scan_jobs",
        "accounts",
    ):
        op.drop_table(table)
