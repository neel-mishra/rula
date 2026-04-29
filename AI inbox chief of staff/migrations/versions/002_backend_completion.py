"""Backend completion — pgvector columns, edit tracking, activation mode, style profiles.

Revision ID: 002
Revises: 001
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── pgvector embedding columns (raw SQL — Alembic lacks native Vector support) ──
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE memories ADD COLUMN IF NOT EXISTS embedding vector(1536)")
    op.execute("ALTER TABLE emails ADD COLUMN IF NOT EXISTS embedding vector(1536)")

    # ── Draft edit tracking ────────────────────────────────────────────
    op.add_column("drafts", sa.Column("user_edited_text", sa.Text(), nullable=True))
    op.add_column("drafts", sa.Column("edit_distance", sa.Float(), nullable=True))
    op.add_column("drafts", sa.Column("edits_tracked_at", sa.DateTime(timezone=True), nullable=True))

    # ── Mailbox activation mode ────────────────────────────────────────
    op.add_column(
        "mailboxes",
        sa.Column("activation_mode", sa.String(20), nullable=False, server_default="shadow"),
    )

    # ── Brief delivery_failed status ───────────────────────────────────
    op.execute("ALTER TYPE briefstatus ADD VALUE IF NOT EXISTS 'delivery_failed'")

    # ── Indexes for embedding similarity search ────────────────────────
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_memories_embedding ON memories "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_emails_embedding ON emails "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_emails_embedding")
    op.execute("DROP INDEX IF EXISTS ix_memories_embedding")
    op.drop_column("mailboxes", "activation_mode")
    op.drop_column("drafts", "edits_tracked_at")
    op.drop_column("drafts", "edit_distance")
    op.drop_column("drafts", "user_edited_text")
    op.execute("ALTER TABLE emails DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE memories DROP COLUMN IF EXISTS embedding")
