"""Initial schema: all tables, enums, indexes, and pgvector extension.

Revision ID: 0001
Revises: None
Create Date: 2026-04-30 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID

# ---------------------------------------------------------------------------
# Revision metadata
# ---------------------------------------------------------------------------
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Extensions
    # ------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # ------------------------------------------------------------------
    # Enum types
    # ------------------------------------------------------------------
    mailbox_status = sa.Enum(
        "active", "inactive", "error",
        name="mailbox_status",
    )
    ingest_status = sa.Enum(
        "pending", "normalized", "failed",
        name="ingest_status",
    )
    workflow_state = sa.Enum(
        "ingested", "normalized", "triaged",
        "draft_queued", "brief_queued",
        "pending_review", "completed", "rejected",
        name="workflow_state",
    )
    triage_priority = sa.Enum(
        "urgent", "normal", "brief", "archive",
        name="triage_priority",
    )
    draft_status = sa.Enum(
        "pending", "accepted", "rejected", "edited",
        name="draft_status",
    )
    time_window = sa.Enum(
        "morning", "afternoon",
        name="time_window",
    )
    eval_sample_type = sa.Enum(
        "triage", "draft", "brief",
        name="eval_sample_type",
    )

    # ------------------------------------------------------------------
    # users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("google_refresh_token", sa.String(2048), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"])

    # ------------------------------------------------------------------
    # mailbox_connections
    # ------------------------------------------------------------------
    op.create_table(
        "mailbox_connections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gmail_address", sa.String(320), nullable=False),
        sa.Column("watch_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", mailbox_status, nullable=False, server_default="inactive"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "gmail_address", name="uq_mailbox_connections_user_gmail"),
    )
    op.create_index("ix_mailbox_connections_id", "mailbox_connections", ["id"])
    op.create_index("ix_mailbox_connections_user_id", "mailbox_connections", ["user_id"])

    # ------------------------------------------------------------------
    # messages
    # ------------------------------------------------------------------
    op.create_table(
        "messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gmail_message_id", sa.String(255), nullable=False),
        sa.Column("gmail_thread_id", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(998), nullable=False, server_default=""),
        sa.Column("sender_email", sa.String(320), nullable=False),
        sa.Column("sender_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("body_preview", sa.String(500), nullable=False, server_default=""),
        sa.Column("raw_payload_gcs_path", sa.String(1024), nullable=True),
        sa.Column("ingest_status", ingest_status, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "gmail_message_id", name="uq_messages_user_gmail_message"),
    )
    op.create_index("ix_messages_id", "messages", ["id"])
    op.create_index("ix_messages_user_id", "messages", ["user_id"])
    op.create_index("ix_messages_gmail_message_id", "messages", ["gmail_message_id"], unique=True)
    op.create_index("ix_messages_gmail_thread_id", "messages", ["gmail_thread_id"])
    op.create_index(
        "idx_messages_user_received",
        "messages",
        ["user_id", sa.text("received_at DESC")],
    )

    # ------------------------------------------------------------------
    # workflow_runs
    # ------------------------------------------------------------------
    op.create_table(
        "workflow_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("message_id", UUID(as_uuid=True), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("state", workflow_state, nullable=False, server_default="ingested"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
    )
    op.create_index("ix_workflow_runs_id", "workflow_runs", ["id"])
    op.create_index("ix_workflow_runs_message_id", "workflow_runs", ["message_id"])
    op.create_index("ix_workflow_runs_user_id", "workflow_runs", ["user_id"])
    op.create_index(
        "idx_workflow_runs_user_state",
        "workflow_runs",
        ["user_id", "state"],
        postgresql_where=sa.text("state = 'pending_review'"),
    )

    # ------------------------------------------------------------------
    # triage_results
    # ------------------------------------------------------------------
    op.create_table(
        "triage_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "workflow_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("priority", triage_priority, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("rationale", sa.Text, nullable=False, server_default=""),
        sa.Column("labels", JSON, nullable=False, server_default="[]"),
        sa.Column("model_version", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_triage_results_id", "triage_results", ["id"])
    op.create_index("ix_triage_results_workflow_run_id", "triage_results", ["workflow_run_id"], unique=True)
    op.create_index("idx_triage_results_priority", "triage_results", ["priority"])

    # ------------------------------------------------------------------
    # drafts
    # ------------------------------------------------------------------
    op.create_table(
        "drafts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "workflow_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("gmail_draft_id", sa.String(255), nullable=True),
        sa.Column("body", sa.Text, nullable=False, server_default=""),
        sa.Column("subject_line", sa.String(998), nullable=False, server_default=""),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("status", draft_status, nullable=False, server_default="pending"),
        sa.Column("user_feedback", sa.Text, nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_drafts_id", "drafts", ["id"])
    op.create_index("ix_drafts_workflow_run_id", "drafts", ["workflow_run_id"])

    # ------------------------------------------------------------------
    # briefs
    # ------------------------------------------------------------------
    op.create_table(
        "briefs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("time_window", time_window, nullable=False),
        sa.Column("summary_markdown", sa.Text, nullable=False, server_default=""),
        sa.Column("action_items", JSON, nullable=False, server_default="[]"),
        sa.Column("message_ids", JSON, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_briefs_id", "briefs", ["id"])
    op.create_index("ix_briefs_user_id", "briefs", ["user_id"])

    # ------------------------------------------------------------------
    # audit_events
    # ------------------------------------------------------------------
    op.create_table(
        "audit_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "workflow_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("agent_name", sa.String(128), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("outcome", sa.String(64), nullable=False),
        sa.Column("metadata", JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_events_id", "audit_events", ["id"])
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"])
    op.create_index("ix_audit_events_workflow_run_id", "audit_events", ["workflow_run_id"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index(
        "idx_audit_events_user_created",
        "audit_events",
        ["user_id", sa.text("created_at DESC")],
    )

    # ------------------------------------------------------------------
    # eval_samples
    # ------------------------------------------------------------------
    op.create_table(
        "eval_samples",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sample_type", eval_sample_type, nullable=False),
        sa.Column("input_hash", sa.Text, nullable=False),
        sa.Column("output_hash", sa.Text, nullable=False),
        sa.Column("human_label", sa.Text, nullable=True),
        sa.Column("model_output", JSON, nullable=False, server_default="{}"),
        sa.Column("score", sa.Numeric(4, 3), nullable=True),
        sa.Column("model_version", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_eval_samples_id", "eval_samples", ["id"])

    # ------------------------------------------------------------------
    # message_embeddings  (requires pgvector)
    # ------------------------------------------------------------------
    op.create_table(
        "message_embeddings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "message_id",
            UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # vector(1536) — text-embedding-3-small dimension
        sa.Column("embedding", sa.Text, nullable=False),  # stored via pgvector; type overridden below
        sa.Column("model_version", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("message_id", "model_version", name="uq_message_embeddings_message_model"),
    )
    # Replace TEXT column with the actual vector type after table creation
    op.execute("ALTER TABLE message_embeddings ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector(1536);")
    op.create_index("ix_message_embeddings_id", "message_embeddings", ["id"])
    op.create_index("ix_message_embeddings_message_id", "message_embeddings", ["message_id"])
    op.execute(
        "CREATE INDEX idx_message_embeddings_ann ON message_embeddings "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
    )


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.execute("DROP INDEX IF EXISTS idx_message_embeddings_ann;")
    op.drop_table("message_embeddings")
    op.drop_table("eval_samples")
    op.drop_table("audit_events")
    op.drop_table("briefs")
    op.drop_table("drafts")
    op.drop_table("triage_results")
    op.drop_table("workflow_runs")
    op.drop_table("messages")
    op.drop_table("mailbox_connections")
    op.drop_table("users")

    # Drop enum types
    sa.Enum(name="eval_sample_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="time_window").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="draft_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="triage_priority").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="workflow_state").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="ingest_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="mailbox_status").drop(op.get_bind(), checkfirst=True)

    # Drop extension last
    op.execute("DROP EXTENSION IF EXISTS vector;")
