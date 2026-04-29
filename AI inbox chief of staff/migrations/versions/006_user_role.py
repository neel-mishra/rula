"""User role column for admin RBAC.

Revision ID: 006
Revises: 005
Create Date: 2026-04-24
"""

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    user_role = sa.Enum("user", "admin", name="userrole")
    user_role.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "users",
        sa.Column("role", user_role, nullable=False, server_default="user"),
    )


def downgrade() -> None:
    op.drop_column("users", "role")
    sa.Enum(name="userrole").drop(op.get_bind(), checkfirst=True)
