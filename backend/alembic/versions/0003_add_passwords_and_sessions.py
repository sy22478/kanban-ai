"""add password hashes and the sessions table

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-01

password_hash is added NOT NULL with no server default and no data statement, so
this migration is schema only. That is deliberate: DECISIONS.md, 2026-07-29, says
migration history is schema and fixtures are not, and carving a DELETE in here to
cope with pre-auth rows would be the exception that erodes it.

The consequence is that this migration fails loudly on any database still holding
users from before registration existed. That is the intended behaviour. A fresh
database has no such rows; a development database that does needs them removed by
hand first. Failing beats quietly rewriting user rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=False))

    op.create_table(
        "sessions",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        # bytea, not text: a sha256 digest is 32 raw bytes. Storing the digest
        # rather than the token means a database leak does not hand over live
        # sessions. One fast hash is correct here and is not the password
        # mistake: the token is 256 bits of CSPRNG output, so there is no
        # low-entropy guess to accelerate.
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Slides, and is what the idle timeout is measured against.
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Set once at login and never extended, so a stolen session dies on a
        # fixed date however much it is used.
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Unique and the lookup index in one: every request resolves a session by
    # this digest, and no two sessions may share one.
    op.create_index(
        "ix_sessions_token_hash", "sessions", ["token_hash"], unique=True
    )
    # For revoking every session a user has, and for sweeping expired rows.
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_index("ix_sessions_token_hash", table_name="sessions")
    op.drop_table("sessions")
    op.drop_column("users", "password_hash")
