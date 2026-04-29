"""User password auth fields.

Revision ID: 008
Revises: 007
Create Date: 2026-04-29
"""

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("password_reset_token", sa.String(length=255), nullable=True))
    op.create_index("ix_users_password_reset_token", "users", ["password_reset_token"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_password_reset_token", table_name="users")
    op.drop_column("users", "password_reset_token")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "password_hash")
