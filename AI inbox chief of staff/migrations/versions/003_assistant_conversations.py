"""Assistant conversations — multi-turn chat sessions.

Revision ID: 003
Revises: 002
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("mailbox_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("title", sa.String(200), nullable=False, server_default="New conversation"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_conv_user_updated", "assistant_conversations", ["user_id", "updated_at"])

    op.create_table(
        "assistant_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("response_data", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "feedback_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("feedback_events.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_msg_conversation_created", "assistant_messages", ["conversation_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_msg_conversation_created", table_name="assistant_messages")
    op.drop_table("assistant_messages")
    op.drop_index("ix_conv_user_updated", table_name="assistant_conversations")
    op.drop_table("assistant_conversations")
