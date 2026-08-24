from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "20260616181215"
down_revision: Union[str, None] = "a283a1d31c28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ===== PHASE 1: CREATE PLACE Q&A SESSION SYSTEM =====

    # Create place_qa_sessions table
    op.create_table(
        "place_qa_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("place_id", sa.String(length=255), nullable=True),
        sa.Column(
            "title", sa.String(length=255), nullable=False, server_default="New Q&A"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_place_qa_sessions_id"), "place_qa_sessions", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_place_qa_sessions_user_id"),
        "place_qa_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_place_qa_sessions_place_id"),
        "place_qa_sessions",
        ["place_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_place_qa_sessions_last_message_at"),
        "place_qa_sessions",
        ["last_message_at"],
        unique=False,
    )

    # Create place_qa_messages table
    op.create_table(
        "place_qa_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"], ["place_qa_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_place_qa_messages_id"), "place_qa_messages", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_place_qa_messages_session_id"),
        "place_qa_messages",
        ["session_id"],
        unique=False,
    )

    # ===== PHASE 2: DROP AI CHAT SYSTEM =====

    # Drop ai_chat_messages table (has foreign key to ai_chat_sessions)
    op.drop_index("ix_ai_chat_messages_session_id", table_name="ai_chat_messages")
    op.drop_index("ix_ai_chat_messages_id", table_name="ai_chat_messages")
    op.drop_table("ai_chat_messages")

    # Drop ai_chat_sessions table
    op.drop_index("ix_ai_chat_sessions_user_id", table_name="ai_chat_sessions")
    op.drop_index("ix_ai_chat_sessions_id", table_name="ai_chat_sessions")
    op.drop_table("ai_chat_sessions")

    # ===== PHASE 3: ADD SESSION_ID TO AUDIT TABLES (OPTIONAL) =====

    # Add session_id to place_questions for linking (nullable for backward compat)
    op.add_column(
        "place_questions", sa.Column("session_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_place_questions_session_id",
        "place_questions",
        "place_qa_sessions",
        ["session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_place_questions_session_id"),
        "place_questions",
        ["session_id"],
        unique=False,
    )

    # Add session_id to place_answer_logs for linking (nullable)
    op.add_column(
        "place_answer_logs", sa.Column("session_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_place_answer_logs_session_id",
        "place_answer_logs",
        "place_qa_sessions",
        ["session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_place_answer_logs_session_id"),
        "place_answer_logs",
        ["session_id"],
        unique=False,
    )


def downgrade() -> None:
    """
    Reverse the migration:
    Phase 1: Remove session_id from audit tables
    Phase 2: Restore AI chat system
    Phase 3: Drop Place Q&A session system
    """
    # ===== PHASE 1: REMOVE SESSION_ID FROM AUDIT TABLES =====

    # Remove from place_answer_logs
    op.drop_index(
        op.f("ix_place_answer_logs_session_id"), table_name="place_answer_logs"
    )
    op.drop_constraint(
        "fk_place_answer_logs_session_id", "place_answer_logs", type_="foreignkey"
    )
    op.drop_column("place_answer_logs", "session_id")

    # Remove from place_questions
    op.drop_index(op.f("ix_place_questions_session_id"), table_name="place_questions")
    op.drop_constraint(
        "fk_place_questions_session_id", "place_questions", type_="foreignkey"
    )
    op.drop_column("place_questions", "session_id")

    # ===== PHASE 2: RESTORE AI CHAT SYSTEM =====

    # Recreate ai_chat_sessions table
    op.create_table(
        "ai_chat_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "title", sa.String(length=255), nullable=False, server_default="New Chat"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ai_chat_sessions_id"), "ai_chat_sessions", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_ai_chat_sessions_user_id"),
        "ai_chat_sessions",
        ["user_id"],
        unique=False,
    )

    # Recreate ai_chat_messages table
    op.create_table(
        "ai_chat_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["ai_chat_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ai_chat_messages_id"), "ai_chat_messages", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_ai_chat_messages_session_id"),
        "ai_chat_messages",
        ["session_id"],
        unique=False,
    )

    # ===== PHASE 3: DROP PLACE Q&A SESSION SYSTEM =====

    # Drop place_qa_messages table
    op.drop_index(
        op.f("ix_place_qa_messages_session_id"), table_name="place_qa_messages"
    )
    op.drop_index(op.f("ix_place_qa_messages_id"), table_name="place_qa_messages")
    op.drop_table("place_qa_messages")

    # Drop place_qa_sessions table
    op.drop_index(
        op.f("ix_place_qa_sessions_last_message_at"), table_name="place_qa_sessions"
    )
    op.drop_index(op.f("ix_place_qa_sessions_place_id"), table_name="place_qa_sessions")
    op.drop_index(op.f("ix_place_qa_sessions_user_id"), table_name="place_qa_sessions")
    op.drop_index(op.f("ix_place_qa_sessions_id"), table_name="place_qa_sessions")
    op.drop_table("place_qa_sessions")
