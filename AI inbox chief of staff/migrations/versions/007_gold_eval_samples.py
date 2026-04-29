"""Gold-eval fixture tables (real-inbox-backed).

Revision ID: 007
Revises: 006
Create Date: 2026-04-25

Three tables back the gold-eval fixture pipeline:
- gold_samples: scrubbed-inbox samples per stratum, awaiting labels.
- gold_sample_labels: human-in-the-loop labels (multiple labels per sample).
- gold_dataset_versions: immutable snapshot tags consumed by nightly_eval.

The dataset itself is populated only after Gmail OAuth + connectors are
live in production. See workers/gold_sample_extraction.py for the
DEFERRED extraction code path.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    fixture_type = sa.Enum(
        "triage", "draft", "brief", "memory", "safety",
        name="goldfixturetype",
    )
    fixture_type.create(op.get_bind(), checkfirst=True)

    stratum = sa.Enum(
        "newsletter", "direct_reply", "update", "action_required",
        "calendar", "ambiguous",
        name="goldstratum",
    )
    stratum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "gold_samples",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "mailbox_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mailboxes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fixture_type", fixture_type, nullable=False),
        sa.Column("stratum", stratum, nullable=False),
        sa.Column("source_gmail_message_id", sa.String(100), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB, nullable=False),
        sa.Column("scrubbed_payload", postgresql.JSONB, nullable=False),
        sa.Column("scrub_version", sa.String(20), nullable=False, server_default="v1"),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Index("ix_gold_samples_mailbox_type", "mailbox_id", "fixture_type", "is_active"),
        sa.Index("ix_gold_samples_stratum", "fixture_type", "stratum", "is_active"),
    )

    op.create_table(
        "gold_sample_labels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "gold_sample_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gold_samples.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label_type", sa.String(40), nullable=False),
        sa.Column(
            "labeled_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("labels", postgresql.JSONB, nullable=False),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Index("ix_gold_sample_labels_sample_type", "gold_sample_id", "label_type"),
    )

    op.create_table(
        "gold_dataset_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tag", sa.String(40), nullable=False, unique=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_latest", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("sample_ids", postgresql.JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Enforce singleton "latest" per fixture_type via partial unique index.
    op.execute(
        "CREATE UNIQUE INDEX ix_gold_dataset_versions_one_latest "
        "ON gold_dataset_versions ((1)) WHERE is_latest = true"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_gold_dataset_versions_one_latest")
    op.drop_table("gold_dataset_versions")
    op.drop_table("gold_sample_labels")
    op.drop_table("gold_samples")
    sa.Enum(name="goldstratum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="goldfixturetype").drop(op.get_bind(), checkfirst=True)
