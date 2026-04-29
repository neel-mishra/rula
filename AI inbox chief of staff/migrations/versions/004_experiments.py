"""Prompt experiments — A/B testing framework.

Revision ID: 004
Revises: 003
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    experiment_status = sa.Enum(
        "draft", "active", "paused", "completed",
        name="experimentstatus",
    )
    experiment_metric = sa.Enum(
        "triage_correction_rate",
        "draft_acceptance_rate",
        "avg_confidence",
        name="experimentmetric",
    )
    experiment_status.create(op.get_bind(), checkfirst=True)
    experiment_metric.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "experiments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("prompt_name", sa.String(100), nullable=False),
        sa.Column("primary_metric", experiment_metric, nullable=False),
        sa.Column("status", experiment_status, nullable=False, server_default="draft"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_experiments_status_prompt",
        "experiments",
        ["status", "prompt_name"],
    )

    op.create_table(
        "experiment_variants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "experiment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("experiments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(50), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("traffic_pct", sa.Integer, nullable=False),
        sa.Column("is_control", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("extra", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("traffic_pct >= 0 AND traffic_pct <= 100", name="ck_variant_traffic_pct"),
    )
    op.create_index(
        "ix_variant_experiment",
        "experiment_variants",
        ["experiment_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_variant_experiment", table_name="experiment_variants")
    op.drop_table("experiment_variants")
    op.drop_index("ix_experiments_status_prompt", table_name="experiments")
    op.drop_table("experiments")
    sa.Enum(name="experimentmetric").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="experimentstatus").drop(op.get_bind(), checkfirst=True)
