"""create boards, columns and cards

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "boards",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_boards_owner_id", "boards", ["owner_id"])

    op.create_table(
        "columns",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("board_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["board_id"], ["boards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # Deferred so one transaction can renumber positions without the
        # constraint firing on an intermediate state.
        sa.UniqueConstraint(
            "board_id",
            "position",
            name="uq_columns_board_id_position",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    op.create_index("ix_columns_board_id", "columns", ["board_id"])

    op.create_table(
        "cards",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("column_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["column_id"], ["columns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "column_id",
            "position",
            name="uq_cards_column_id_position",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    op.create_index("ix_cards_column_id", "cards", ["column_id"])


def downgrade() -> None:
    op.drop_index("ix_cards_column_id", table_name="cards")
    op.drop_table("cards")
    op.drop_index("ix_columns_board_id", table_name="columns")
    op.drop_table("columns")
    op.drop_index("ix_boards_owner_id", table_name="boards")
    op.drop_table("boards")
