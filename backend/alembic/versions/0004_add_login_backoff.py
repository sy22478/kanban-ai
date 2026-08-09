"""add per-account login backoff

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-01

Per-account, not per-IP. OWASP: the failed-attempt counter "should be associated
with the account itself, rather than the source IP address", because an attacker
with a pool of addresses defeats a per-IP counter while still hammering one
account. The per-IP limit lives in slowapi and does a different job.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "failed_login_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    # Null means not locked. A nullable timestamp rather than a boolean plus a
    # timestamp, so there is only one place the answer can come from and the two
    # cannot disagree.
    op.add_column(
        "users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_count")
