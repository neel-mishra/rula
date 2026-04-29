"""Initial schema — all core entities with mailbox_id isolation.

Revision ID: 001
Create Date: 2026-04-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # ── users ────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── mailboxes ────────────────────────────────────────────────────────────
    op.create_table(
        "mailboxes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("gmail_email", sa.String(255), nullable=False, index=True),
        sa.Column("gmail_user_id", sa.String(255), nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gmail_watch_expiration", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gmail_history_id", sa.String(50), nullable=True),
        sa.Column("gmail_watch_resource_id", sa.String(255), nullable=True),
        sa.Column("label_needs_attention", sa.String(100), nullable=True),
        sa.Column("label_next_brief", sa.String(100), nullable=True),
        sa.Column("label_cora_system", sa.String(100), nullable=True),
        sa.Column("feature_flags", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("brief_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("draft_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("auto_archive_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("brief_morning_hour", sa.Integer(), nullable=True),
        sa.Column("brief_afternoon_hour", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_connected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("backfill_completed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mailboxes_user_id_email", "mailboxes", ["user_id", "gmail_email"])

    # ── emails ───────────────────────────────────────────────────────────────
    op.create_table(
        "emails",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mailbox_id", UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gmail_message_id", sa.String(100), nullable=False),
        sa.Column("gmail_thread_id", sa.String(100), nullable=False),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("from_address", sa.String(500), nullable=True),
        sa.Column("from_name", sa.String(255), nullable=True),
        sa.Column("from_domain", sa.String(255), nullable=True, index=True),
        sa.Column("to_addresses", ARRAY(sa.Text), nullable=False, server_default=sa.text("ARRAY[]::text[]")),
        sa.Column("cc_addresses", ARRAY(sa.Text), nullable=False, server_default=sa.text("ARRAY[]::text[]")),
        sa.Column("reply_to", sa.String(500), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("gmail_labels", ARRAY(sa.Text), nullable=False, server_default=sa.text("ARRAY[]::text[]")),
        sa.Column("thread_message_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_thread_root", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("parent_message_id", sa.String(100), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("features", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_emails_mailbox_received", "emails", ["mailbox_id", "received_at"])
    op.create_index("ix_emails_mailbox_gmail_message", "emails", ["mailbox_id", "gmail_message_id"], unique=True)
    op.create_index("ix_emails_mailbox_thread", "emails", ["mailbox_id", "gmail_thread_id"])

    # ── triage_decisions ─────────────────────────────────────────────────────
    op.create_table(
        "triage_decisions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email_id", UUID(as_uuid=True), sa.ForeignKey("emails.id", ondelete="CASCADE"), nullable=False, unique=True, index=True),
        sa.Column("mailbox_id", UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("outcome", sa.String(50), nullable=False, index=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("method", sa.String(50), nullable=False),
        sa.Column("rule_matched", sa.String(255), nullable=True),
        sa.Column("model_id", sa.String(100), nullable=True),
        sa.Column("policy_version", sa.String(50), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=True),
        sa.Column("reason_trace", sa.Text(), nullable=True),
        sa.Column("extra", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("corrected_by_user", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("corrected_outcome", sa.String(50), nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_triage_mailbox_created", "triage_decisions", ["mailbox_id", "created_at"])
    op.create_index("ix_triage_outcome", "triage_decisions", ["mailbox_id", "outcome"])

    # ── drafts ───────────────────────────────────────────────────────────────
    op.create_table(
        "drafts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email_id", UUID(as_uuid=True), sa.ForeignKey("emails.id", ondelete="CASCADE"), nullable=False, unique=True, index=True),
        sa.Column("mailbox_id", UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gmail_draft_id", sa.String(100), nullable=True),
        sa.Column("draft_text", sa.Text(), nullable=False),
        sa.Column("subject_line", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("model_id", sa.String(100), nullable=False),
        sa.Column("policy_version", sa.String(50), nullable=False),
        sa.Column("style_profile_version", sa.String(50), nullable=True),
        sa.Column("grounding_score", sa.Float(), nullable=True),
        sa.Column("hallucination_flag", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("style_conformance_score", sa.Float(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default=sa.text("'generated'")),
        sa.Column("correlation_id", sa.String(100), nullable=False, index=True),
        sa.Column("extra", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_drafts_mailbox_created", "drafts", ["mailbox_id", "created_at"])

    # ── briefs ───────────────────────────────────────────────────────────────
    op.create_table(
        "briefs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mailbox_id", UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("window", sa.String(20), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("subject_line", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("delivery_email_id", sa.String(100), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("prompt_version", sa.String(50), nullable=True),
        sa.Column("policy_version", sa.String(50), nullable=False),
        sa.Column("correlation_id", sa.String(100), nullable=False, index=True),
        sa.Column("extra", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_briefs_mailbox_scheduled", "briefs", ["mailbox_id", "scheduled_at"])

    # ── brief_items ──────────────────────────────────────────────────────────
    op.create_table(
        "brief_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("brief_id", UUID(as_uuid=True), sa.ForeignKey("briefs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("email_id", UUID(as_uuid=True), sa.ForeignKey("emails.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mailbox_id", UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("key_points", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("gmail_open_url", sa.Text(), nullable=True),
        sa.Column("importance_score", sa.Float(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── feedback_events ──────────────────────────────────────────────────────
    op.create_table(
        "feedback_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("mailbox_id", UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("email_id", UUID(as_uuid=True), sa.ForeignKey("emails.id", ondelete="SET NULL"), nullable=True),
        sa.Column("feedback_type", sa.String(100), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("structured_intent", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("memory_id", UUID(as_uuid=True), nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_feedback_mailbox_created", "feedback_events", ["mailbox_id", "created_at"])
    op.create_index("ix_feedback_user_type", "feedback_events", ["user_id", "feedback_type"])

    # ── memories ─────────────────────────────────────────────────────────────
    op.create_table(
        "memories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("mailbox_id", UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("scope", sa.String(30), nullable=False, index=True),
        sa.Column("applies_to_all_mailboxes", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("memory_type", sa.String(20), nullable=False, index=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("structured_data", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("source_feedback_id", UUID(as_uuid=True), sa.ForeignKey("feedback_events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_reinforced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_memories_user_scope", "memories", ["user_id", "scope"])
    op.create_index("ix_memories_mailbox_type", "memories", ["mailbox_id", "memory_type"])
    op.create_index("ix_memories_active", "memories", ["user_id", "is_active"])

    # ── audit_events (immutable — no UPDATE trigger) ─────────────────────────
    op.create_table(
        "audit_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("mailbox_id", UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("severity", sa.String(20), nullable=False, server_default=sa.text("'info'")),
        sa.Column("correlation_id", sa.String(100), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_user_created", "audit_events", ["user_id", "created_at"])
    op.create_index("ix_audit_mailbox_created", "audit_events", ["mailbox_id", "created_at"])
    op.create_index("ix_audit_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_correlation", "audit_events", ["correlation_id"])

    # Immutability trigger — prevent UPDATE and DELETE on audit_events
    op.execute("""
        CREATE OR REPLACE FUNCTION audit_events_immutable()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events table is append-only; UPDATE and DELETE are not permitted';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER audit_events_no_update
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION audit_events_immutable();
    """)

    # ── mutation_ledger ──────────────────────────────────────────────────────
    op.create_table(
        "mutation_ledger",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email_id", UUID(as_uuid=True), sa.ForeignKey("emails.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("mailbox_id", UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mutation_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("prior_state", JSONB, nullable=False),
        sa.Column("new_state", JSONB, nullable=False),
        sa.Column("label_id", sa.String(100), nullable=True),
        sa.Column("reason_trace", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.String(50), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=True),
        sa.Column("triage_decision_id", UUID(as_uuid=True), sa.ForeignKey("triage_decisions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("undo_token", sa.String(100), nullable=False, unique=True),
        sa.Column("undo_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("within_undo_window", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("correlation_id", sa.String(100), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mutation_mailbox_created", "mutation_ledger", ["mailbox_id", "created_at"])
    op.create_index("ix_mutation_status", "mutation_ledger", ["status"])
    op.create_index("ix_mutation_undo_token", "mutation_ledger", ["undo_token"], unique=True)


def downgrade() -> None:
    op.drop_table("mutation_ledger")
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_update ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS audit_events_immutable()")
    op.drop_table("audit_events")
    op.drop_table("memories")
    op.drop_table("feedback_events")
    op.drop_table("brief_items")
    op.drop_table("briefs")
    op.drop_table("drafts")
    op.drop_table("triage_decisions")
    op.drop_table("emails")
    op.drop_table("mailboxes")
    op.drop_table("users")
